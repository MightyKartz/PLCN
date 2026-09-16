"""Versioned local translation packs. Fetching never activates a new pack."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
import zipfile
from contextlib import closing
from datetime import datetime, timezone

from safe_io import atomic_write_json, file_digest, file_lock

import app_paths

SCHEMA_VERSION = 2
UPSTREAM = 'yingw/rom-name-cn'


def source_files(source):
    root = Path(source)
    return sorted(p for p in root.iterdir() if p.is_file() and (
        p.suffix.lower() == '.csv' or p.name in {'README.md', 'README2.md', 'CONTRIBUTING.md', 'name_alias(Chinese).json'}
        or p.name.upper().startswith(('LICENSE', 'COPYING'))))


def source_fingerprint(source):
    return hashlib.sha256(json.dumps({p.name: file_digest(p) for p in source_files(source)}, sort_keys=True).encode()).hexdigest()


def catalog_path(source):
    root = Path(source).resolve().parent
    return root / 'catalog.sqlite3' if (root / 'manifest.json').is_file() and (root / 'catalog.sqlite3').is_file() else None


def cache_path(source, fingerprint=None):
    from database import DatabaseManager
    if not Path(source).is_dir():
        return Path(DatabaseManager.DB_FILE)
    # Different UI jobs may use different data sources concurrently. Keep their
    # catalogs separate so rebuilding one source cannot change another job's view.
    fingerprint = fingerprint or source_fingerprint(source)
    return Path(DatabaseManager.DB_FILE).parent / 'catalogs' / (fingerprint + '.sqlite3')


def open_database(source, db_path=None):
    from database import DatabaseManager
    packed = catalog_path(source) if db_path is None else None
    if packed:
        return DatabaseManager(str(packed), read_only=True)
    fingerprint = source_fingerprint(source) if Path(source).is_dir() else None
    db = DatabaseManager(db_path=str(db_path or cache_path(source, fingerprint)))
    if not Path(source).is_dir():
        return db
    conn = db.get_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS data_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.commit()
    previous = conn.execute("SELECT value FROM data_metadata WHERE key='source_fingerprint'").fetchone()
    if not previous or previous[0] != fingerprint:
        with file_lock(db.db_path):
            # CSVs are the source of truth; human corrections live outside this cache.
            try:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('DELETE FROM aliases')
                conn.execute('DELETE FROM translations')
                db.import_csvs(source, commit=False)
                conn.execute("INSERT OR REPLACE INTO data_metadata VALUES ('source_fingerprint', ?)", (fingerprint,))
                conn.commit()
            except Exception:
                conn.rollback()
                db.close()
                raise
    return db


def build_pack(source, output, revision=None):
    from database import DatabaseManager
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError(f'输出目录已存在，请使用新的版本目录：{output}')
    files = source_files(source)
    if not any(p.suffix.lower() == '.csv' for p in files):
        raise ValueError('数据源没有 CSV 文件')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plcn-pack-', dir=output.parent) as temporary:
        staging = Path(temporary).resolve() / 'pack'
        if not staging.is_relative_to(output.parent):
            raise ValueError('Invalid staging directory')
        names = staging / 'rom-name-cn'
        names.mkdir(parents=True)
        for file in files:
            shutil.copyfile(file, names / file.name)
        db = DatabaseManager(str(staging / 'catalog.sqlite3'))
        try:
            db.import_csvs(names)
            rows = db.get_connection().execute("SELECT system, COUNT(*), SUM(CASE WHEN chinese_name='' THEN 1 ELSE 0 END) FROM translations GROUP BY system").fetchall()
            counts = {r[0]: {'records': r[1], 'untranslated': r[2]} for r in rows}
            if not counts:
                raise ValueError('数据包没有可用记录')
        finally:
            db.close()
        manifest = {
            'schema_version': SCHEMA_VERSION,
            'upstream': UPSTREAM,
            'revision': revision or 'local-snapshot',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'source_fingerprint': source_fingerprint(names),
            'systems': counts,
            'catalog_sha256': file_digest(staging / 'catalog.sqlite3'),
            'files': {p.name: file_digest(p) for p in source_files(names)},
        }
        atomic_write_json(staging / 'manifest.json', manifest)
        validate_pack(staging)
        os.rename(staging, output)
    return manifest


def validate_pack(pack):
    root = Path(pack).resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('不支持的数据包 schema')
    if file_digest(root / 'catalog.sqlite3') != manifest['catalog_sha256']:
        raise ValueError('数据库校验失败')
    if source_fingerprint(root / 'rom-name-cn') != manifest['source_fingerprint']:
        raise ValueError('数据源文件校验失败')
    with closing(sqlite3.connect((root / 'catalog.sqlite3').as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('数据库完整性检查失败')
        if not conn.execute('SELECT COUNT(*) FROM translations').fetchone()[0]:
            raise ValueError('空数据库')
    return manifest


def compare_packs(before, after):
    def records(pack):
        validate_pack(pack)
        with closing(sqlite3.connect(str(Path(pack) / 'catalog.sqlite3'))) as conn:
            return {(s, e): c for s, e, c in conn.execute('SELECT system, english_name, chinese_name FROM translations')}
    old, new = records(before), records(after)
    return {'added': len(new.keys() - old.keys()), 'removed': len(old.keys() - new.keys()),
            'changed': sum(old[k] != new[k] for k in old.keys() & new.keys()),
            'untranslated': sum(not value for value in new.values())}


def activate_pack(pack, config_path=None):
    config_path = config_path or app_paths.config_path()
    manifest = validate_pack(pack)
    with file_lock(config_path):
        config = json.loads(Path(config_path).read_text(encoding='utf-8')) if Path(config_path).exists() else {}
        source = str(Path(pack).resolve() / 'rom-name-cn')
        if config.get('rom_name_cn_path') != source:
            config['previous_rom_name_cn_path'] = config.get('rom_name_cn_path') or str(app_paths.default_source())
            config['rom_name_cn_path'] = source
            atomic_write_json(config_path, config)
    return manifest


def rollback_pack(config_path=None):
    config_path = config_path or app_paths.config_path()
    with file_lock(config_path):
        config = json.loads(Path(config_path).read_text(encoding='utf-8'))
        previous = config.get('previous_rom_name_cn_path')
        if not previous or not Path(previous).is_dir():
            raise ValueError('没有可恢复的数据源')
        if catalog_path(previous):
            validate_pack(Path(previous).parent)
        config['rom_name_cn_path'], config['previous_rom_name_cn_path'] = previous, config.get('rom_name_cn_path')
        atomic_write_json(config_path, config)
    return {'rom_name_cn_path': previous}


def fetch_pack(output, ref='master'):
    def request(url, maximum):
        req = urllib.request.Request(url, headers={'User-Agent': 'PLCN-data-pack'})
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValueError('上游数据超过下载大小限制')
        return body
    commit = json.loads(request(f'https://api.github.com/repos/{UPSTREAM}/commits/{urllib.parse.quote(ref, safe="")}', 2 * 1024 * 1024))['sha']
    archive = request(f'https://codeload.github.com/{UPSTREAM}/zip/{commit}', 128 * 1024 * 1024)
    with tempfile.TemporaryDirectory(prefix='plcn-source-') as temporary:
        source = Path(temporary).resolve()
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            total = 0
            for info in zipped.infolist():
                parts = info.filename.split('/')
                if len(parts) != 2 or not parts[1]:
                    continue
                name = parts[1]
                if '\\' in name or name in {'.', '..'}:
                    raise ValueError('上游文件路径无效')
                if not (name.endswith('.csv') or name in {'README.md', 'README2.md', 'CONTRIBUTING.md', 'name_alias(Chinese).json'} or name.upper().startswith(('LICENSE', 'COPYING'))):
                    continue
                total += info.file_size
                if total > 64 * 1024 * 1024:
                    raise ValueError('数据源展开大小超过限制')
                target = (source / name).resolve()
                if target.parent != source:
                    raise ValueError('上游文件路径越界')
                target.write_bytes(zipped.read(info))
        return build_pack(source, output, revision=commit)


def main(argv=None):
    parser = argparse.ArgumentParser(description='PLCN translation data packs')
    parser.add_argument('--config', default=str(app_paths.config_path()))
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--source', required=True)
    build.add_argument('--output', required=True)
    fetch = commands.add_parser('fetch')
    fetch.add_argument('--output', required=True)
    fetch.add_argument('--ref', default='master')
    for name in ['inspect', 'activate']:
        commands.add_parser(name).add_argument('--pack', required=True)
    compare = commands.add_parser('compare')
    compare.add_argument('--before', required=True)
    compare.add_argument('--after', required=True)
    commands.add_parser('rollback')
    args = parser.parse_args(argv)
    if args.command == 'build':
        result = build_pack(args.source, args.output)
    elif args.command == 'fetch':
        result = fetch_pack(args.output, args.ref)
    elif args.command == 'inspect':
        result = validate_pack(args.pack)
    elif args.command == 'activate':
        result = activate_pack(args.pack, args.config)
    elif args.command == 'compare':
        result = compare_packs(args.before, args.after)
    else:
        result = rollback_pack(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
