"""Desktop workflow endpoints, kept separate from the legacy playlist handler."""
import json
from pathlib import Path
import threading
import urllib.request
import uuid

import app_paths
import data_pack
import repair_history
from task_control import checkpoint

POST_ROUTES = {
    '/api/desktop/pick', '/api/desktop/shutdown', '/api/jobs/cancel', '/api/jobs/retry',
    '/api/data/check', '/api/data/fetch', '/api/data/compare', '/api/data/activate', '/api/data/rollback',
    '/api/history/restore',
}


def reply(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def get(handler, path, jobs, config_path):
    if path == '/api/instance':
        reply(handler, {'instance_id': getattr(handler.server, 'instance_id', None)})
    elif path == '/api/desktop':
        reply(handler, {'data_dir': str(app_paths.user_data_dir()), 'cache_dir': str(app_paths.cache_dir()),
                        'config_path': str(config_path), 'resource_dir': str(app_paths.resource_root()),
                        'active_jobs': jobs.active(), 'history': repair_history.list_history(), 'jobs': jobs.snapshot()})
    elif path == '/api/data':
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
    else:
        return False
    return True


def background(jobs, title, work):
    job_id = jobs.create_job()
    def run():
        try:
            jobs.update_job(job_id, 0, 1, title)
            result = work(job_id)
            jobs.complete_job(job_id, result)
        except Exception as error:
            jobs.fail_job(job_id, error)
    threading.Thread(target=run, name='plcn-' + job_id, daemon=False).start()
    return job_id


def managed_pack(value):
    path = Path(value).resolve()
    root = (app_paths.user_data_dir() / 'packs').resolve()
    if path.parent != root:
        raise ValueError('请选择 PLCN 数据目录中已校验的数据包')
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


def post(handler, path, payload, jobs, config_path):
    if not isinstance(payload, dict):
        raise ValueError('请求必须是 JSON 对象')
    if path == '/api/desktop/pick':
        from native_dialog import pick
        selected = pick(payload.get('kind', 'directory'), payload.get('initial', ''))
        reply(handler, {'path': selected})
    elif path == '/api/desktop/shutdown':
        with jobs.lock:
            if any(job['status'] in ('pending', 'running') for job in jobs.jobs.values()):
                reply(handler, {'error': '仍有任务运行，请取消或等待完成后再退出'}, 409)
                return
            jobs.stopping = True
        reply(handler, {'stopped': True})
        threading.Thread(target=handler.server.shutdown, daemon=True).start()
    elif path == '/api/jobs/cancel':
        jobs.cancel(payload.get('job_id'))
        reply(handler, {'cancel_requested': True})
    elif path == '/api/jobs/retry':
        old_id = payload.get('job_id')
        job = jobs.get_job(old_id)
        if not job or job['status'] not in ('completed', 'cancelled', 'failed'):
            raise ValueError('请选择已结束的任务')
        target = jobs.contexts.get(old_id, {}).get('thumbnails_dir')
        if not target or str(target).startswith('adb://'):
            raise ValueError('此处仅重试本地图片；ADB 请重新预览后应用')
        details = (job.get('result') or {}).get('download_summary', {}).get('details', [])
        tasks = list(dict.fromkeys((r['system'], r['source'], r['game']) for r in details
                                  if (r.get('status') == 'failed' or r.get('reason') == 'cancelled')
                                  and r.get('reason') != 'filename_collision'))
        if not tasks:
            raise ValueError('没有可重试的图片任务；命名冲突请先修改名称')
        def retry(jid):
            from thumbnail_downloader import ThumbnailDownloader
            downloader = ThumbnailDownloader(target)
            downloader.cancel_check = lambda: jobs.cancelled(jid)
            jobs.contexts[jid] = {'thumbnails_dir': target}
            return {'download_summary': downloader.download_batch(tasks, lambda a, b, text: jobs.update_job(jid, a, b, text))}
        reply(handler, {'job_id': background(jobs, '重试未完成图片，不修改列表', retry)})
    elif path == '/api/data/check':
        def check(jid):
            request = urllib.request.Request('https://api.github.com/repos/yingw/rom-name-cn/commits/master', headers={'User-Agent': 'PLCN'})
            with urllib.request.urlopen(request, timeout=20) as response:
                commit = json.loads(response.read(2 * 1024 * 1024))
            checkpoint(lambda: jobs.cancelled(jid))
            return {'revision': commit['sha'], 'message': '已查询上游版本，尚未下载或启用'}
        reply(handler, {'job_id': background(jobs, '查询名称数据库版本', check)})
    elif path == '/api/data/fetch':
        def fetch(jid):
            root = app_paths.user_data_dir() / 'packs'
            output = root / ('upstream-' + uuid.uuid4().hex[:12])
            info = data_pack.fetch_pack(output)
            checkpoint(lambda: jobs.cancelled(jid))
            comparison = compare_active(output, config_path)
            return {'pack': str(output), 'revision': info['revision'], 'comparison': comparison,
                    'message': '下载与校验完成，查看差异后手动启用；记录变化不代表准确率变化'}
        reply(handler, {'job_id': background(jobs, '下载和校验名称数据库（不会自动启用）', fetch)})
    elif path == '/api/data/compare':
        pack = managed_pack(payload['pack'])
        def compare(jid):
            checkpoint(lambda: jobs.cancelled(jid))
            return {'pack': str(pack), 'comparison': compare_active(pack, config_path)}
        reply(handler, {'job_id': background(jobs, '比较所选包与当前数据源', compare)})
    elif path == '/api/data/activate':
        data_pack.activate_pack(managed_pack(payload['pack']), config_path)
        reply(handler, {'activated': True})
    elif path == '/api/data/rollback':
        reply(handler, data_pack.rollback_pack(config_path))
    elif path == '/api/history/restore':
        reply(handler, repair_history.restore(payload.get('id')))
