"""Library HTTP handlers; request transport is owned by server.py."""
import json
import os
from api_common import background, reply
import subprocess
import sys


def sources(handler, context, payload):
    config_path = context.CONFIG_FILE
    from library_sources import discover
    reply(handler, discover(config_path))


def game_file_storages(handler, context, query):
    # The file workspace works before any RetroArch directory or playlist exists.
    import mtp_runtime as mtp
    from pathlib import Path

    response = {'local': str(Path.home()), 'storages': []}
    try:
        response['storages'] = [
            {key: storage[key] for key in ('path', 'label', 'device_name')}
            for storage in mtp.devices()
        ]
    except (RuntimeError, OSError) as error:
        response['storage_error'] = str(error)
    reply(handler, response)


def game_file_directory(handler, context, query):
    from pathlib import Path

    import content_scan as scan
    import mtp_runtime as mtp

    path = query.get('path', [''])[0]
    if mtp.is_mtp(path):
        serial, storage, parts = mtp.parse(path)
        breadcrumbs = [{'name': '', 'path': mtp.uri(serial, storage)}] + [
            {'name': part, 'path': mtp.uri(serial, storage, '/'.join(parts[:index + 1]))}
            for index, part in enumerate(parts)
        ]
    else:
        local = Path(path)
        if not local.is_absolute():
            raise ValueError('请选择绝对目录路径')
        local = local.resolve()
        path = str(local)
        breadcrumbs = [
            {'name': folder.name or folder.anchor, 'path': str(folder)}
            for folder in (*reversed(local.parents), local)
        ]
    parent = breadcrumbs[-2]['path'] if len(breadcrumbs) > 1 else None
    entries = sorted(scan.folders(path), key=lambda entry: (not entry['folder'], entry['name'].casefold()))
    reply(handler, {'path': path, 'parent': parent, 'breadcrumbs': breadcrumbs, 'items': [
        {'name': entry['name'], 'directory': entry['folder'],
         'path': scan.join(path, entry['name'])}
        for entry in entries
    ]})


def change_game_file(handler, context, payload):
    import game_file_actions

    game_file_actions.apply(*game_file_actions.validate(payload))
    reply(handler, {'ok': True})


def preview_game_file_deletion(handler, context, payload):
    from game_file_deletion import preview, validate

    path, root = validate(payload)
    thumbnails = context.load_server_config().get('thumbnails_override') or ''

    def work(job_id):
        plan = preview(path, root, thumbnails)
        with context.job_manager.lock:
            context.job_manager.contexts[job_id] = {
                'file_deletion': (path, root, thumbnails, plan['signature'])
            }
        return plan['public']

    reply(handler, {'job_id': background(context.job_manager, '检查游戏文件引用', work)})


def apply_game_file_deletion(handler, context, payload):
    from game_file_deletion import apply
    from task_control import checkpoint

    ident, clean = payload.get('preview_job_id'), payload.get('clean_covers')
    if not isinstance(ident, str) or not isinstance(clean, bool):
        raise ValueError('请先预览删除方案')
    job = context.job_manager.get_job(ident)
    if not job or job['status'] != 'completed':
        raise ValueError('请先预览删除方案')
    manager = context.job_manager
    with manager.lock:
        args = manager.contexts.get(ident, {}).pop('file_deletion', None)
    if args is None:
        raise ValueError('删除方案已失效，请重新预览')
    reply(handler, {'job_id': background(manager, '删除游戏文件', lambda jid: apply(
        *args, clean, lambda current, total, msg: manager.update_job(jid, current, total, msg),
        lambda: checkpoint(lambda: manager.cancelled(jid))))})


def overview(handler, context, query):
    from workbench_library import overview as read_overview
    reply(handler, read_overview(query.get('root', [''])[0]))


def playlist_summary(handler, context, query):
    from retroarch_scanner import read_playlist_summary
    from workbench_library import playlist_overview

    path = query.get('path', [''])[0]
    if not path.lower().endswith('.lpl'):
        raise ValueError('请选择 .lpl 播放列表')
    summary = read_playlist_summary(path)
    if not summary['valid']:
        raise ValueError(summary.get('error') or '无法读取播放列表')
    response = {'summary': summary, 'directory': path.rsplit('/', 1)[0]
                if summary.get('transport') in {'mtp', 'adb'} else os.path.dirname(path)}
    if 'thumbnails' in query:
        response['overview'] = playlist_overview(summary, query['thumbnails'][0])
    reply(handler, response)


def recent(handler, context, payload):
    config_path = context.CONFIG_FILE
    from library_sources import remember
    reply(handler, remember(payload, config_path))


def list_files(handler, context, payload):
    path = payload.get('path', ['.'])[0]
    if not os.path.exists(path):
        path = '.'

    path = os.path.abspath(path)

    try:
        items = []
        # Add parent directory
        parent = os.path.dirname(path)
        items.append({"name": "..", "path": parent, "is_dir": True})

        with os.scandir(path) as it:
            for entry in it:
                items.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": entry.is_dir()
                })

        # Sort: directories first, then files
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        response = {
            "current_path": path,
            "items": items
        }

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(response).encode())
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())


def scan_device(handler, context, payload):
    target_path = payload.get('path', [''])[0]
    try:
        from retroarch_scanner import scan_retroarch_target
        scan = scan_retroarch_target(target_path or None)

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(scan, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))


def open_folder(handler, context, payload):
    try:
        data = payload
        target_path = data.get("path")
        if not target_path:
            handler.send_response(400)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Path is required"}).encode())
            return

        target_path = os.path.abspath(target_path)
        if not os.path.exists(target_path):
            handler.send_response(404)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Path does not exist"}).encode())
            return
        if not os.path.isdir(target_path):
            target_path = os.path.dirname(target_path)

        if sys.platform == "darwin":
            subprocess.Popen(["open", target_path])
        elif os.name == "nt":
            os.startfile(target_path)
        else:
            subprocess.Popen(["xdg-open", target_path])

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"status": "success", "path": target_path}).encode())
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
    return
