"""Data HTTP handlers; request transport is owned by server.py."""
import glob
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.request
import uuid
import app_paths
import data_pack
from task_control import checkpoint
from api_common import reply, background


def managed_pack(value):
    path = Path(value).resolve()
    root = (app_paths.user_data_dir() / 'packs').resolve()
    if path.parent != root:
        raise ValueError('请选择 RetroArch 助手数据目录中已校验的数据包')
    return path


def compare_active(pack, config_path):
    config = json.loads(Path(config_path).read_text(encoding='utf-8')) if Path(config_path).exists() else {}
    source = config.get('rom_name_cn_path') or str(app_paths.default_source())
    if data_pack.catalog_path(source):
        before = Path(source).parent
    else:
        before = app_paths.user_data_dir() / 'packs' / ('baseline-' + data_pack.source_fingerprint(source)[:16])
        from safe_io import file_lock
        with file_lock(before):
            if not before.exists():
                data_pack.build_pack(source, before)
    return data_pack.compare_packs(before, pack)


def data(handler, context, payload):
    config_path = context.CONFIG_FILE
    config = json.loads(Path(config_path).read_text(encoding='utf-8')) if Path(config_path).exists() else {}
    source = Path(config.get('rom_name_cn_path') or app_paths.default_source())
    packs = []
    for manifest in sorted((app_paths.user_data_dir() / 'packs').glob('*/manifest.json')):
        try:
            info = data_pack.validate_pack(manifest.parent)
            packs.append({'path': str(manifest.parent), 'revision': info['revision'],
                          'records': sum(v['records'] for v in info['systems'].values()),
                          'untranslated': sum(v['untranslated'] for v in info['systems'].values()),
                          'active': source.resolve() == (manifest.parent / 'rom-name-cn').resolve()})
        except (OSError, ValueError, KeyError):
            continue
    active = None
    if data_pack.catalog_path(source):
        active = data_pack.validate_pack(source.parent)
    reply(handler, {'source': str(source), 'source_kind': 'bundled' if source.resolve() == app_paths.default_source().resolve() else 'custom', 'active': active, 'packs': packs,
                    'can_rollback': bool(config.get('previous_rom_name_cn_path'))})


def check(handler, context, payload):
    jobs = context.job_manager
    def check(jid):
        request = urllib.request.Request('https://api.github.com/repos/yingw/rom-name-cn/commits/master', headers={'User-Agent': 'PLCN'})
        with urllib.request.urlopen(request, timeout=20) as response:
            commit = json.loads(response.read(2 * 1024 * 1024))
        checkpoint(lambda: jobs.cancelled(jid))
        return {'revision': commit['sha'], 'message': '已查询上游版本，尚未下载或启用'}
    reply(handler, {'job_id': background(jobs, '查询名称数据库版本', check)})


def fetch(handler, context, payload):
    jobs = context.job_manager
    config_path = context.CONFIG_FILE
    def fetch(jid):
        root = app_paths.user_data_dir() / 'packs'
        output = root / ('upstream-' + uuid.uuid4().hex[:12])
        info = data_pack.fetch_pack(output)
        checkpoint(lambda: jobs.cancelled(jid))
        comparison = compare_active(output, config_path)
        return {'pack': str(output), 'revision': info['revision'], 'comparison': comparison,
                'message': '下载与校验完成，查看差异后手动启用；记录变化不代表准确率变化'}
    reply(handler, {'job_id': background(jobs, '下载和校验名称数据库（不会自动启用）', fetch)})


def compare(handler, context, payload):
    jobs = context.job_manager
    config_path = context.CONFIG_FILE
    pack = managed_pack(payload['pack'])
    def compare(jid):
        checkpoint(lambda: jobs.cancelled(jid))
        return {'pack': str(pack), 'comparison': compare_active(pack, config_path)}
    reply(handler, {'job_id': background(jobs, '比较所选包与当前数据源', compare)})


def activate(handler, context, payload):
    config_path = context.CONFIG_FILE
    data_pack.activate_pack(managed_pack(payload['pack']), config_path)
    reply(handler, {'activated': True})


def rollback(handler, context, payload):
    config_path = context.CONFIG_FILE
    reply(handler, data_pack.rollback_pack(config_path))


def get_stats(handler, context, payload):
    try:
        config = context.load_server_config()

        rom_db_path = config.get("rom_name_cn_path") or str(app_paths.default_source())
        if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
            rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)

        from data_pack import catalog_path, cache_path
        db_path = str(catalog_path(rom_db_path) or cache_path(rom_db_path))
        database_count = 0
        database_ready = os.path.exists(db_path)
        database_error = None
        if database_ready:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM translations")
                database_count = cursor.fetchone()[0]
                conn.close()
            except Exception as e:
                database_error = str(e)

        dat_dir = str(app_paths.dat_storage() / "libretro-db" / "dat")
        bundled_dat = app_paths.resource_root() / 'data' / 'libretro-db' / 'dat'
        dat_count = len({os.path.basename(file) for folder in (dat_dir, str(bundled_dat))
                         for file in glob.glob(os.path.join(folder, '*.dat'))})
        csv_count = len(glob.glob(os.path.join(rom_db_path, "*.csv"))) if os.path.exists(rom_db_path) else 0
        offline_available = (database_count > 0 or csv_count > 0) and dat_count > 0

        response = {
            "database_count": database_count,
            "database_ready": database_ready and not database_error,
            "database_error": database_error,
            "dat_count": dat_count,
            "csv_count": csv_count,
            "offline_available": offline_available,
            "paths": {
                "database": db_path,
                "dat_dir": dat_dir,
                "rom_name_cn": rom_db_path
            }
        }

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(response).encode())
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())


def list_systems(handler, context, payload):
    try:
        config = context.load_server_config()

        rom_db_path = config.get("rom_name_cn_path", str(app_paths.default_source()))
        if getattr(sys, 'frozen', False) and not os.path.isabs(rom_db_path):
            rom_db_path = os.path.join(sys._MEIPASS, rom_db_path)

        systems = []
        if os.path.exists(rom_db_path):
            # Look for CSV files
            files = glob.glob(os.path.join(rom_db_path, "*.csv"))
            for f in files:
                # Filename without extension is the system name
                name = os.path.splitext(os.path.basename(f))[0]
                name = re.sub(r'\s*\(\d{8}-\d{6}\).*$', '', name).strip()
                if name != 'missing_games' and name not in systems:
                    systems.append(name)

        # Add mapped systems from DatabaseManager
        from database import DatabaseManager
        for mapped_system in DatabaseManager.SYSTEM_MAPPINGS.keys():
            if mapped_system not in systems:
                systems.append(mapped_system)

        systems.sort()

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"systems": systems}).encode())
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
