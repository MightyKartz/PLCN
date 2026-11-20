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


def game_file_ops(handler, context, payload):
    import game_file_actions
    from task_control import checkpoint

    if payload.get('action') == 'add':
        sources, directory, remote, overwrite = game_file_actions.validate_add(payload)
        manager = context.job_manager
        reply(handler, {'job_id': background(manager, '添加游戏文件', lambda jid: game_file_actions.apply_add(
            sources, directory, remote, overwrite,
            lambda current, total, msg: manager.update_job(jid, current, total, msg),
            lambda: checkpoint(lambda: manager.cancelled(jid))))})
        return
    path, argument, remote = game_file_actions.validate_op(payload)
    action = payload['action']
    if action == 'rename':
        reply(handler, game_file_actions.apply_rename(path, argument, remote))
        return
    manager = context.job_manager
    title = '删除文件' if action == 'delete' else '复制文件'
    work = (lambda jid: game_file_actions.apply_delete(
        path, remote, lambda current, total, msg: manager.update_job(jid, current, total, msg),
        lambda: checkpoint(lambda: manager.cancelled(jid)))) if action == 'delete' else (
        lambda jid: game_file_actions.apply_copy(
            path, argument, remote, lambda current, total, msg: manager.update_job(jid, current, total, msg),
            lambda: checkpoint(lambda: manager.cancelled(jid))))
    reply(handler, {'job_id': background(manager, title, work)})


def preview_game_file_sync(handler, context, payload):
    import game_file_sync

    root, changes = payload.get('root'), payload.get('changes')
    if not isinstance(root, str) or not root or not isinstance(changes, list):
        raise ValueError('请先打开游戏库')

    def work(job_id):
        plan = game_file_sync.preview(root, changes)
        with context.job_manager.lock:
            context.job_manager.contexts[job_id] = {'file_sync': (root, changes, plan['signature'])}
        return plan['public']

    reply(handler, {'job_id': background(context.job_manager, '核对文件改动', work)})


def apply_game_file_sync(handler, context, payload):
    import game_file_sync

    ident = payload.get('preview_job_id')
    job = context.job_manager.get_job(ident) if isinstance(ident, str) else None
    if not job or job['status'] != 'completed':
        raise ValueError('请先预览同步方案')
    manager = context.job_manager
    with manager.lock:
        args = manager.contexts.get(ident, {}).pop('file_sync', None)
    if args is None:
        raise ValueError('同步方案已失效，请重新预览')
    reply(handler, {'job_id': background(manager, '同步文件改动', lambda jid: game_file_sync.apply(*args))})


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
