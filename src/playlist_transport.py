"""Apply a reviewed playlist using local files, ADB or verified MTP writes."""
from pathlib import Path
import mtp_runtime as mtp
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
    options = dict(options)
    if changes and all('original_item_label' in change and change.get('new_label') == change['original_item_label'] for change in changes):
        options['write_names'] = False
    remote = is_adb_uri(path) or mtp.is_mtp(path)
    remote_images = is_adb_uri(thumbnails) or mtp.is_mtp(thumbnails)
    download = options.get('download_thumbnails', True)
    with ExitStack() as resources:
        local_path, local_images = path, thumbnails
        if remote:
            progress(0, len(changes), '正在读取实机游戏列表...')
            lock_name = hashlib.sha256(path.encode('utf-8')).hexdigest()
            resources.enter_context(file_lock(app_paths.cache_dir() / 'locks' / lock_name))
            staging = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-remote-'))
            local_path = mtp.materialize(path, staging) if mtp.is_mtp(path) else materialize_adb_file(path, cache_dir=staging)
            original_digest = mtp.digest(Path(local_path).read_bytes())
            with open(local_path, encoding='utf-8-sig') as original:
                expected_remote = json.load(original)
        existing_mtp = set()
        mtp_digests = {}
        if remote_images:
            local_images = resources.enter_context(tempfile.TemporaryDirectory(prefix='plcn-remote-thumbnails-'))
        if mtp.is_mtp(thumbnails) and download:
            from artwork_resolver import THUMBNAIL_TYPES, sanitize_filename, valid_png, validate_system
            from single_artwork import read_target
            from rom_paths import rom_title
            from task_control import checkpoint
            for change in changes:
                label = change.get('new_label') if options.get('write_names', True) else change.get('original_item_label') or change.get('original_label')
                system = change.get('system')
                if not label or not system:
                    continue
                system = validate_system(system)
                for kind in THUMBNAIL_TYPES:
                    checkpoint(cancel_check)
                    relative = Path(system) / kind / (sanitize_filename(label) + '.png')
                    destination = mtp.join(thumbnails, *relative.parts)
                    content = read_target(destination)
                    mtp_digests[destination] = mtp.digest(content)
                    if content is not None and valid_png(content):
                        existing_mtp.add(str(relative))
                    else:
                        for alias in dict.fromkeys([change.get('thumbnail_source'), rom_title(change.get('path'))]):
                            if not alias or alias == label:
                                continue
                            candidate = read_target(mtp.join(thumbnails, system, kind, sanitize_filename(alias) + '.png'))
                            if candidate is not None and valid_png(candidate):
                                content = candidate
                                break
                    if content is not None and valid_png(content):
                        cached = Path(local_images) / relative
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        cached.write_bytes(content)
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
            if mtp.is_mtp(path):
                remote_backup = mtp.write(path, Path(local_path).read_bytes(), original_digest)
            else:
                remote_backup = verified_push_adb_playlist(local_path, path, expected_remote)
        if remote_images and download:
            progress(len(changes), len(changes), '正在推送缩略图到实机...')
            if mtp.is_mtp(thumbnails):
                reviewed_files = {str(Path(detail['path']).relative_to(local_images))
                    for detail in summary.get('details', []) if detail.get('path') and detail.get('status') in {'success', 'skipped'}}
                mtp.push_directory(local_images, thumbnails, expected_hashes=mtp_digests, include_files=reviewed_files - existing_mtp)
            else:
                push_adb_directory(local_images, thumbnails)
        annotate_download_summary_paths(summary, local_root=local_images, final_root=thumbnails)
        result = build_apply_job_result(summary, apply_summary=applied, changes=changes,
                                        transport='mtp' if mtp.is_mtp(path) else 'adb' if remote else 'local', remote_backup=remote_backup)
        # Remember explicit choices only after the verified write and image
        # publication. Use the real playlist URI and resulting label, not staging.
        if download and any(change.get('artwork_source_confirmed') for change in changes):
            from artwork_identity import remember
            for change in changes:
                if not change.get('artwork_source_confirmed'):
                    continue
                record = next((record for record in (applied or {}).get('applied', [])
                    if record['path'] == change.get('path') and record['index'] == change.get('index')), None)
                if not record:
                    continue
                for detail in summary.get('details', []):
                    if (detail.get('game') == record['new_label'] and detail.get('system') == change.get('system')
                            and detail.get('status') in {'success', 'skipped'} and detail.get('path')):
                        try:
                            remember({'system': change['system'], 'playlist_path': path,
                                      'rom_path': record['path'], 'label': record['new_label']},
                                     detail.get('gallery_source') or change['thumbnail_source'], detail['type'])
                        except (OSError, ValueError) as error:
                            result['memory_warning'] = '图片已完成，但图片源记忆未保存：' + str(error)
                            progress(len(changes), len(changes), result['memory_warning'])
        if not options.get('write_names', True):
            result['applied_count'] = 0
        return result
