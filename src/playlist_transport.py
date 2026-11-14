"""Apply a reviewed playlist using local files or the existing ADB write protocol."""
from contextlib import ExitStack
import hashlib
import json
import tempfile

import app_paths
from job_results import annotate_download_summary_paths, build_apply_job_result, split_plcn_apply_result
import playlist_service
from retroarch_scanner import is_adb_uri, materialize_adb_file, push_adb_directory, verified_push_adb_playlist
from safe_io import file_lock


def apply_playlist(path, changes, thumbnails, *, options, progress, cancel_check, expected_digest=None):
    remote = is_adb_uri(path)
    remote_images = is_adb_uri(thumbnails)
    download = options.get('download_thumbnails', True)
    with ExitStack() as resources:
        local_path, local_images = path, thumbnails
        if remote:
            progress(0, len(changes), '正在读取实机游戏列表...')
            lock_name = hashlib.sha256(path.encode('utf-8')).hexdigest()
            resources.enter_context(file_lock(app_paths.cache_dir() / 'locks' / lock_name))
            staging = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-'))
            local_path = materialize_adb_file(path, cache_dir=staging)
            with open(local_path, encoding='utf-8-sig') as original:
                expected_remote = json.load(original)
        if remote_images:
            local_images = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-adb-thumbnails-'))
        result = playlist_service.apply_changes(
            local_path, changes, local_images, backup=options.get('backup', True),
            progress_callback=progress, download_thumbnails=download, cancel_check=cancel_check,
            write_names=options.get('write_names', True), record_history=not remote,
            expected_digest=expected_digest,
        )
        summary, applied = split_plcn_apply_result(result)
        remote_backup = None
        if remote and options.get('write_names', True) and applied and applied.get('applied'):
            progress(len(changes), len(changes), '正在备份并验证实机游戏列表...')
            remote_backup = verified_push_adb_playlist(local_path, path, expected_remote)
        if remote_images and download:
            progress(len(changes), len(changes), '正在推送缩略图到实机...')
            push_adb_directory(local_images, thumbnails)
        annotate_download_summary_paths(summary, local_root=local_images, final_root=thumbnails)
        result = build_apply_job_result(summary, apply_summary=applied, changes=changes,
                                        transport='adb' if remote else 'local', remote_backup=remote_backup)
        if not options.get('write_names', True):
            result['applied_count'] = 0
        return result
