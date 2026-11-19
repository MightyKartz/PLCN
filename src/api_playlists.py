"""Playlists HTTP handlers; request transport is owned by server.py."""
import mtp_runtime as mtp
import json
import os
import sys
import app_paths
from api_common import reply


def detect_system(handler, context, payload):
    path = payload.get('path', [''])[0]
    if not path or not os.path.exists(path):
        handler.send_response(400)
        handler.end_headers()
        handler.wfile.write(b'{"error": "Invalid path"}')
        return

    try:
        system_name = ""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            items = data.get('items', [])
            if items:
                # Try to get db_name from the first item
                # Format is usually "System Name.lpl"
                db_name = items[0].get('db_name', '')
                if db_name:
                    system_name = os.path.splitext(db_name)[0]

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"system_name": system_name}).encode())
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())


def items(handler, context, payload):
    from playlist_browser import read_playlist
    try:
        result = read_playlist(payload.get('path', [''])[0],
                               payload.get('system', [''])[0],
                               payload.get('thumbnails', [''])[0])
        reply(handler, result)
    except (OSError, ValueError, RuntimeError) as error:
        reply(handler, {'error': str(error)}, 400)


def preview(handler, context, payload):
    try:
        data = payload
        playlist_path = data.get('playlist_path')
        system_name = data.get('system_name')
        thumbnails_dir = data.get('thumbnails_dir')

        config = context.load_server_config()
        rom_name_cn_path = config.get("rom_name_cn_path", str(app_paths.default_source()))
        manual_overrides_path = context.configured_overrides_path(config)
        if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
             rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

        from retroarch_scanner import is_adb_uri, materialize_adb_file
        effective_playlist_path = mtp.materialize(playlist_path) if mtp.is_mtp(playlist_path) else materialize_adb_file(playlist_path) if is_adb_uri(playlist_path) else playlist_path

        import playlist_service as plcn
        options = {key: bool((data.get('options') or {}).get(key, True))
                   for key in ('write_names', 'download_thumbnails')}
        changes = plcn.analyze_playlist(
            effective_playlist_path,
            system_name,
            rom_name_cn_path,
            thumbnails_dir,
            manual_overrides_path=manual_overrides_path, verify_artwork=options['download_thumbnails'], source_playlist_path=playlist_path,
        )
        # The direct-completion entries reuse the same per-game verdict as the
        # whole-library review: executable rename, executable artwork download
        # and remaining manual gaps.
        from batch_review import classify_change
        readers = {}
        for change in changes:
            change['completion'] = classify_change(change, options, thumbnails_dir, system_name, readers)

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "changes": changes,
            "source": {
                "playlist_path": playlist_path,
                "local_playlist_path": effective_playlist_path if is_adb_uri(playlist_path) or mtp.is_mtp(playlist_path) else None,
                "transport": "mtp" if mtp.is_mtp(playlist_path) else "adb" if is_adb_uri(playlist_path) else "local"
            }
        }).encode())
    except Exception as e:
        import traceback
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
    return


def apply(handler, context, payload):
    from api_common import background
    from playlist_transport import apply_playlist
    import completion_receipts
    options = payload.get('options') or {}
    def work(jid):
        context.job_manager.contexts[jid] = {'thumbnails_dir': payload.get('thumbnails_dir')}
        result = apply_playlist(payload.get('playlist_path'), payload.get('changes'), payload.get('thumbnails_dir'),
                                options=options, progress=lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                                cancel_check=lambda: context.job_manager.cancelled(jid))
        system = next((change.get('system') for change in payload.get('changes') or [] if change.get('system')), '')
        if not system:
            system = os.path.splitext(os.path.basename(str(payload.get('playlist_path') or '')))[0] or '游戏列表'
        result['receipt_id'] = completion_receipts.create([result], '补全 ' + system)
        return result
    reply(handler, {'job_id': background(context.job_manager, '应用游戏列表变更', work)})


def batch_preview(handler, context, payload):
    from api_common import background
    from batch_review import prepare_review
    directory = payload.get('batch_dir')
    if not isinstance(directory, str) or not directory:
        raise ValueError('请选择游戏列表目录')
    supplied = payload.get('options') or {}
    options = {key: supplied.get(key, True) for key in ('write_names', 'download_thumbnails')}
    if any(not isinstance(value, bool) for value in options.values()) or not any(options.values()):
        raise ValueError('至少选择修改名称或补全图片')
    thumbnails = payload.get('thumbnails_dir') or ''
    config = context.load_server_config()
    source = payload.get('rom_name_cn_path') or config.get('rom_name_cn_path') or str(app_paths.default_source())
    if getattr(sys, 'frozen', False) and not os.path.isabs(source):
        source = os.path.join(sys._MEIPASS, source)
    overrides = context.configured_overrides_path(config)
    def work(jid):
        review = prepare_review(directory, thumbnails, source, overrides, options,
                                lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                                lambda: context.job_manager.cancelled(jid))
        context.job_manager.contexts[jid] = {'batch_review': review}
        return {'rows': review['rows'], 'options': options,
                'can_apply': any(plan['changes'] for plan in review['plans'])
                             and (not options['download_thumbnails'] or bool(thumbnails))}
    reply(handler, {'job_id': background(context.job_manager, '分析全部主机（不会写入）', work)})


def batch_apply(handler, context, payload):
    from api_common import background
    from batch_review import apply_review
    preview_id = payload.get('preview_job_id')
    job = context.job_manager.get_job(preview_id)
    stored = context.job_manager.contexts.get(preview_id, {})
    review = stored.get('batch_review')
    if not job or job['status'] != 'completed' or not review or not job['result']['can_apply']:
        raise ValueError('请先生成有效的全部主机汇总，再确认应用')
    review = stored.pop('batch_review')
    import completion_receipts
    def work(jid):
        context.job_manager.contexts[jid] = {'thumbnails_dir': review['thumbnails_dir']}
        result = apply_review(review, lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                              lambda: context.job_manager.cancelled(jid), payload.get('continue_on_error', True))
        result['receipt_id'] = completion_receipts.create(result.get('playlists'), '补全全部主机')
        return result
    reply(handler, {'job_id': background(context.job_manager, '应用已确认的全部主机变更', work)})


def completion_receipts_list(handler, context, query):
    import completion_receipts
    reply(handler, {'receipts': completion_receipts.list_receipts()})


def completion_undo(handler, context, payload):
    from api_common import background
    import completion_receipts
    receipt_id = payload.get('id')
    if not isinstance(receipt_id, str):
        raise ValueError('缺少要撤销的补全记录')
    def work(jid):
        return completion_receipts.undo(receipt_id,
                                        progress=lambda a, b, text: context.job_manager.update_job(jid, a, b, text),
                                        cancel_check=lambda: context.job_manager.cancelled(jid))
    reply(handler, {'job_id': background(context.job_manager, '撤销补全', work)})


def batch_discard(handler, context, payload):
    stored = context.job_manager.contexts.get(payload.get('preview_job_id'), {})
    stored.pop('batch_review', None)
    reply(handler, {'discarded': True})


def discs(handler, context, query):
    from disc_inspection import inspect_discs
    reply(handler, inspect_discs(query.get('path', [''])[0], query.get('system', [''])[0]))
