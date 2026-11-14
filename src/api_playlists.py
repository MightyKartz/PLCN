"""Playlists HTTP handlers; request transport is owned by server.py."""
import json
import os
import sys
import tempfile
import threading
import app_paths
from safe_io import file_lock
from task_control import TaskCancelled
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
        effective_playlist_path = materialize_adb_file(playlist_path) if is_adb_uri(playlist_path) else playlist_path

        import playlist_service as plcn
        changes = plcn.analyze_playlist(
            effective_playlist_path,
            system_name,
            rom_name_cn_path,
            thumbnails_dir,
            manual_overrides_path=manual_overrides_path,
        )

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "changes": changes,
            "source": {
                "playlist_path": playlist_path,
                "local_playlist_path": effective_playlist_path if is_adb_uri(playlist_path) else None,
                "transport": "adb" if is_adb_uri(playlist_path) else "local"
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
    try:
        data = payload
        playlist_path = data.get('playlist_path')
        changes = data.get('changes')
        thumbnails_dir = data.get('thumbnails_dir')
        options = data.get('options') or {}
        download_thumbnails = options.get('download_thumbnails', True)
        write_names = options.get('write_names', True)

        # Create Job
        job_id = context.job_manager.create_job()
        context.job_manager.contexts[job_id] = {'thumbnails_dir': thumbnails_dir}

        def run_job(jid, p_path, chgs, t_dir, should_download):
            from contextlib import ExitStack
            with ExitStack() as resources:
                return run_apply_job(resources, jid, p_path, chgs, t_dir, should_download)

        def run_apply_job(resources, jid, p_path, chgs, t_dir, should_download):
            try:
                import playlist_service as plcn
                from retroarch_scanner import (
                    verified_push_adb_playlist,
                    is_adb_uri,
                    materialize_adb_file,
                    push_adb_directory,
                )
                def progress_cb(curr, tot, msg):
                    context.job_manager.update_job(jid, curr, tot, msg)

                remote_playlist = is_adb_uri(p_path)
                remote_thumbnails = is_adb_uri(t_dir)
                effective_playlist_path = p_path
                effective_thumbnails_dir = t_dir

                if remote_playlist:
                    context.job_manager.update_job(jid, 0, len(chgs or []), "正在读取实机游戏列表...")
                    import hashlib
                    lock_name = hashlib.sha256(p_path.encode('utf-8')).hexdigest()
                    resources.enter_context(file_lock(app_paths.cache_dir() / 'locks' / lock_name))
                    staging_dir = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-'))
                    effective_playlist_path = materialize_adb_file(p_path, cache_dir=staging_dir)
                    with open(effective_playlist_path, encoding='utf-8-sig') as original:
                        expected_remote = json.load(original)

                if remote_playlist and remote_thumbnails:
                    effective_thumbnails_dir = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-thumbnails-'))

                apply_result = plcn.apply_changes(
                    effective_playlist_path,
                    chgs,
                    effective_thumbnails_dir,
                    progress_callback=progress_cb,
                    download_thumbnails=should_download, cancel_check=lambda: context.job_manager.cancelled(jid),
                    write_names=write_names, record_history=not remote_playlist
                )
                summary, apply_summary = context.split_plcn_apply_result(apply_result)

                remote_backup = None
                if remote_playlist and apply_summary and apply_summary.get('applied'):
                    context.job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在备份并验证实机游戏列表...")
                    remote_backup = verified_push_adb_playlist(effective_playlist_path, p_path, expected_remote)

                if remote_playlist and remote_thumbnails and should_download:
                    context.job_manager.update_job(jid, len(chgs or []), len(chgs or []), "正在推送缩略图到实机...")
                    push_adb_directory(effective_thumbnails_dir, t_dir)

                summary = context.annotate_download_summary_paths(
                    summary,
                    local_root=effective_thumbnails_dir,
                    final_root=t_dir,
                )

                context.job_manager.complete_job(jid, context.build_apply_job_result(
                    summary,
                    apply_summary=apply_summary,
                    changes=chgs,
                    transport="adb" if remote_playlist else "local",
                    remote_backup=remote_backup,
                ))
            except Exception as e:
                import traceback
                traceback.print_exc()
                context.job_manager.fail_job(jid, str(e))

        # Start background thread
        thread = threading.Thread(target=run_job, args=(job_id, playlist_path, changes, thumbnails_dir, download_thumbnails))
        thread.start()

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"job_id": job_id}).encode())
    except Exception as e:
        import traceback
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
    return


def batch_apply(handler, context, payload):
    try:
        data = payload
        batch_dir = data.get('batch_dir')
        thumbnails_dir = data.get('thumbnails_dir')
        rom_name_cn_path = data.get('rom_name_cn_path') or context.load_server_config().get('rom_name_cn_path') or str(app_paths.default_source())
        options = data.get('options') or {}
        backup = options.get('backup', True)
        continue_on_error = options.get('continue_on_error', True)
        download_thumbnails = options.get('download_thumbnails', True)
        write_names = options.get('write_names', True)

        # Handle PyInstaller path for rom_name_cn_path
        if getattr(sys, 'frozen', False) and not os.path.isabs(rom_name_cn_path):
             rom_name_cn_path = os.path.join(sys._MEIPASS, rom_name_cn_path)

        # Create Job
        job_id = context.job_manager.create_job()
        context.job_manager.contexts[job_id] = {'thumbnails_dir': thumbnails_dir}

        def run_batch_job(jid, b_dir, t_dir, r_path, use_backup, keep_going, should_download):
            try:
                import playlist_service as plcn
                import glob
                from thumbnail_downloader import ThumbnailDownloader

                # Find all .lpl files
                playlist_files = glob.glob(os.path.join(b_dir, "*.lpl"))
                total_files = len(playlist_files)

                if total_files == 0:
                    context.job_manager.fail_job(jid, "No .lpl files found in directory.")
                    return

                context.job_manager.update_job(jid, 0, total_files, f"Found {total_files} playlists.")

                summaries = []
                errors = []

                for i, playlist_path in enumerate(playlist_files):
                    if context.job_manager.cancelled(jid):
                        break
                    filename = os.path.basename(playlist_path)
                    context.job_manager.update_job(jid, i, total_files, f"Processing {filename}...")

                    system_name = os.path.splitext(filename)[0]

                    try:
                        # 1. Analyze
                        changes = plcn.analyze_playlist(playlist_path, system_name, r_path, t_dir, manual_overrides_path=context.configured_overrides_path())

                        # 2. Apply (with backup)
                        # We pass a dummy progress callback or None, as we track file-level progress here.
                        # Or we could aggregate progress? For simplicity, just file-level.
                        apply_result = plcn.apply_changes(
                            playlist_path,
                            changes,
                            t_dir,
                            backup=use_backup,
                            download_thumbnails=should_download, cancel_check=lambda: context.job_manager.cancelled(jid),
                            write_names=write_names
                        )
                        summary, _apply_summary = context.split_plcn_apply_result(apply_result)
                        summary = context.annotate_download_summary_paths(
                            summary,
                            local_root=t_dir,
                            final_root=t_dir,
                        )
                        summaries.append(summary)

                    except TaskCancelled:
                        break
                    except Exception as e:
                        print(f"Error processing {filename}: {e}")
                        errors.append(f"{filename}: {e}")
                        if not keep_going:
                            raise

                merged_summary = ThumbnailDownloader.merge_summaries(summaries)
                context.job_manager.complete_job(jid, {
                    "processed_count": len(summaries),
                    "errors": errors,
                    "download_summary": merged_summary
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                context.job_manager.fail_job(jid, str(e))

        # Start background thread
        thread = threading.Thread(
            target=run_batch_job,
            args=(job_id, batch_dir, thumbnails_dir, rom_name_cn_path, backup, continue_on_error, download_thumbnails)
        )
        thread.start()

        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"job_id": job_id}).encode())
    except Exception as e:
        import traceback
        traceback.print_exc()
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": str(e)}).encode())
    return
