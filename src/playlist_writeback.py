"""Locked playlist writeback, backups, readback verification and artwork tasks."""
from pathlib import Path
from datetime import datetime
import os
import time
from playlist_manager import PlaylistManager
from thumbnail_downloader import ThumbnailDownloader
from rom_paths import remove_disc_companions
from safe_io import file_lock, file_digest
import app_paths
from playlist_proposals import (
    normalize_value,
    proposal_matches_item,
)


def timestamped_backup_path(playlist_path):
    backup_dir = app_paths.user_data_dir() / 'playlist-backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    name = Path(playlist_path).name
    base_path = backup_dir / f"{name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    backup_path = str(base_path)
    suffix = 1
    while os.path.exists(backup_path):
        backup_path = f"{base_path}-{suffix}"
        suffix += 1
    return backup_path


def find_playlist_item_by_path(items, target_path):
    if not target_path:
        return None, None
    norm_target = normalize_value(target_path)
    for index, item in enumerate(items):
        item_path = item.get('path')
        if item_path and normalize_value(item_path) == norm_target:
            return index, item
    return None, None


def skipped_apply_detail(change, reason, item=None):
    detail = {
        "proposal_id": change.get("proposal_id", change.get("index")),
        "index": change.get("index"),
        "path": change.get("path"),
        "reason": reason,
    }
    if reason == "stale_proposal":
        detail["expected"] = {
            "label": change.get("original_item_label"),
            "db_name": change.get("original_db_name"),
        }
        detail["actual"] = {
            "label": (item or {}).get("label"),
            "db_name": (item or {}).get("db_name"),
        }
    return detail


def wrap_apply_result(download_summary, apply_summary):
    result = dict(download_summary or ThumbnailDownloader.empty_summary(0))
    result["download_summary"] = download_summary or ThumbnailDownloader.empty_summary(0)
    result["apply"] = apply_summary
    return result


def writeback_record(change, item=None, reason=None):
    proposal_path = change.get('path')
    item_path = (item or {}).get('path')
    record = {
        "proposal_id": change.get('proposal_id'),
        "index": change.get('index'),
        "path": proposal_path or item_path,
        "old_label": change.get('original_item_label') or change.get('original_label'),
        "new_label": change.get('new_label'),
    }
    if item_path and proposal_path and normalize_value(item_path) != normalize_value(proposal_path):
        record["actual_path"] = item_path
    if reason:
        record["reason"] = reason
    if reason == "stale_proposal":
        record["expected"] = {
            "label": change.get("original_item_label"),
            "db_name": change.get("original_db_name"),
        }
        record["actual"] = {
            "label": (item or {}).get("label"),
            "db_name": (item or {}).get("db_name"),
        }
    return record


def apply_summary_applied_record(record):
    return {
        "proposal_id": record.get("proposal_id"),
        "index": record.get("index"),
        "path": record.get("path"),
        "old_label": record.get("old_label"),
        "new_label": record.get("new_label"),
        "thumbnail_source": record.get("thumbnail_source"),
    }


def apply_summary_skipped_record(record):
    summary = {
        "proposal_id": record.get("proposal_id"),
        "index": record.get("index"),
        "path": record.get("path"),
        "reason": record.get("reason"),
    }
    if record.get("reason") == "stale_proposal":
        summary["expected"] = record.get("expected")
        summary["actual"] = record.get("actual")
    if record.get("actual_path"):
        summary["actual_path"] = record.get("actual_path")
    return summary


def attach_writeback_summary(summary, writeback):
    summary["writeback"] = writeback
    return summary


def applied_record_verified(record, items):
    target_path = normalize_value(record.get("path"))
    target_label = normalize_value(record.get("new_label"))
    if not target_path or not target_label:
        return False

    record_index = record.get("actual_index", record.get("index"))
    if isinstance(record_index, int) and 0 <= record_index < len(items):
        item = items[record_index]
        return (
            normalize_value(item.get("path")) == target_path
            and normalize_value(item.get("label")) == target_label
        )

    for item in items:
        if normalize_value(item.get("path")) == target_path and normalize_value(item.get("label")) == target_label:
            return True
    return False


def apply_changes(playlist_path, changes, thumbnails_dir, backup=True, progress_callback=None, download_thumbnails=True, cancel_check=None, write_names=True, record_history=True, expected_digest=None):
    from task_control import checkpoint
    checkpoint(cancel_check)
    if not isinstance(changes, list) or any(not isinstance(change, dict) for change in changes):
        raise ValueError('changes 必须是变更对象数组')
    with file_lock(playlist_path):
        if expected_digest is not None and file_digest(playlist_path) != expected_digest:
            raise ValueError('游戏列表在汇总后已改变，请重新生成汇总：' + str(playlist_path))
        return _apply_changes_locked(playlist_path, changes, thumbnails_dir, backup, progress_callback, download_thumbnails, cancel_check, write_names, record_history)


def _apply_changes_locked(playlist_path, changes, thumbnails_dir, backup=True, progress_callback=None, download_thumbnails=True, cancel_check=None, write_names=True, record_history=True):
    """
    Applies the changes to the playlist and downloads thumbnails.
    """
    backup_path = None
    if backup and write_names:
        import shutil
        backup_path = timestamped_backup_path(playlist_path)
        shutil.copy2(playlist_path, backup_path)
        print(f"Backed up playlist to {backup_path}")

    writeback = {
        "backup_path": backup_path,
        "applied": [],
        "skipped": [],
        "failed": [],
    }

    playlist_manager = PlaylistManager(playlist_path)
    # Match against the full original playlist, including intentional duplicates.

    downloader = ThumbnailDownloader(thumbnails_dir)
    downloader.cancel_check = cancel_check
    candidate_applied = []

    for change in changes:
        index = change.get('index')
        new_label = change.get('new_label')
        target_path = change.get('path')

        if not isinstance(new_label, str) or not new_label.strip():
            writeback["skipped"].append(writeback_record(change, reason="missing_new_label"))
            continue

        target_item = None
        target_index = None
        path_was_found = False

        if target_path and isinstance(index, int) and 0 <= index < len(playlist_manager.items):
            norm_target = normalize_value(target_path)
            indexed_item = playlist_manager.items[index]
            if normalize_value(indexed_item.get('path')) == norm_target:
                path_was_found = True
                if not proposal_matches_item(change, indexed_item):
                    print(f"Warning: Proposal {change.get('proposal_id', index)} is stale for {os.path.basename(target_path)}. Skipping update.")
                    writeback["skipped"].append(writeback_record(change, indexed_item, "stale_proposal"))
                else:
                    target_item = indexed_item
                    target_index = index

            if path_was_found and target_item is None:
                continue

        if target_path and target_item is None:
            norm_target = normalize_value(target_path)
            for item_index, item in enumerate(playlist_manager.items):
                item_path = item.get('path')
                if item_path and normalize_value(item_path) == norm_target:
                    path_was_found = True
                    if proposal_matches_item(change, item):
                        target_item = item
                        target_index = item_index
                        break

            if path_was_found and target_item is None:
                print(f"Warning: Proposal {change.get('proposal_id', index)} is stale for {os.path.basename(target_path)}. Skipping update.")
                writeback["skipped"].append(writeback_record(change, reason="stale_proposal"))
                continue

        if target_item is None:
            if not isinstance(index, int) or not (0 <= index < len(playlist_manager.items)):
                print(f"Error: Index {index} out of bounds. Skipping update.")
                writeback["skipped"].append(writeback_record(change, reason="index_out_of_bounds"))
                continue

            current_item = playlist_manager.items[index]
            if target_path and normalize_value(current_item.get('path')) != normalize_value(target_path):
                print(f"Warning: Index {index} path mismatch. Expected {target_path}, got {current_item.get('path')}. Skipping update.")
                writeback["skipped"].append(writeback_record(change, current_item, "path_mismatch"))
                continue

            if not proposal_matches_item(change, current_item):
                print(f"Warning: Proposal {change.get('proposal_id', index)} no longer matches playlist item at index {index}. Skipping update.")
                writeback["skipped"].append(writeback_record(change, current_item, "stale_proposal"))
                continue

            target_item = current_item
            target_index = index

        if not write_names:
            new_label = target_item.get('label') or new_label
            change = dict(change, new_label=new_label)
        target_item['label'] = new_label
        record = writeback_record(change, target_item)
        record["actual_index"] = target_index
        record["thumbnail_source"] = change.get('thumbnail_source')
        record["system"] = change.get('system')
        candidate_applied.append(record)

        if target_path:
            print(f"Updated label for {os.path.basename(target_path)} to '{new_label}'")
        else:
            print(f"Updated label at index {target_index} to '{new_label}'")

    from task_control import checkpoint
    checkpoint(cancel_check)
    if candidate_applied and write_names:
        original_items = list(playlist_manager.items)
        playlist_manager.items, removed = remove_disc_companions(
            playlist_manager.items, [record['path'] for record in candidate_applied])
        writeback['removed_companions'] = removed
        retained = []
        for record in candidate_applied:
            original_item = original_items[record['actual_index']]
            new_index = next((i for i, item in enumerate(playlist_manager.items) if item is original_item), None)
            if new_index is None:
                writeback['skipped'].append(dict(record, reason='disc_companion_removed'))
            else:
                record['actual_index'] = new_index
                retained.append(record)
        candidate_applied = retained
        playlist_manager.save(playlist_path)
        print(f"Saved updated playlist to {playlist_path}")

        try:
            mtime = os.path.getmtime(playlist_path)
            print(f"File modification time: {time.ctime(mtime)}")
        except Exception as e:
            print(f"Verification failed: {e}")

    reloaded_manager = PlaylistManager(playlist_path)
    reloaded_items = reloaded_manager.get_items()
    for record in candidate_applied:
        if applied_record_verified(record, reloaded_items):
            writeback["applied"].append(record)
        else:
            failed_record = dict(record)
            failed_record["reason"] = "readback_mismatch"
            writeback["failed"].append(failed_record)

    if record_history and write_names and writeback['applied'] and backup_path:
        try:
            from repair_history import record_write
            writeback['history_id'] = record_write(playlist_path, backup_path, len(writeback['applied']))
        except Exception as error:
            writeback['history_warning'] = str(error)

    download_tasks = [
        (record.get("system"), record.get("thumbnail_source"), record.get("new_label"))
        for record in writeback["applied"]
        if record.get("system") and record.get("thumbnail_source") and record.get("new_label")
    ]
    for record in writeback['applied']:
        change = next(c for c in changes if c.get('proposal_id') == record.get('proposal_id')
                      and c.get('path') == record.get('path'))
        if change.get('replace_artwork_hashes'):
            downloader.replace_hashes[(record['system'], record['thumbnail_source'], record['new_label'])] = change['replace_artwork_hashes']
        if change.get('artwork_cover_fallback') == 'Named_Snaps' and not change.get('artwork_source_confirmed'):
            downloader.cover_fallbacks[(record['system'], record['thumbnail_source'], record['new_label'])] = 'Named_Snaps'
        if (change.get('chinese_title_sources') and not change.get('artwork_source_confirmed')
                and not any(e.get('resolved_name') and e.get('source') in {'playlist_crc32', 'local_zip_crc'}
                            for e in change.get('match_diagnostics', {}).get('evidence_chain', []))):
            downloader.artwork_constraints[(record['system'], record['thumbnail_source'], record['new_label'])] = change['chinese_title_constraints']

    verification = [
        {
            "proposal_id": record.get("proposal_id"),
            "index": record.get("actual_index", record.get("index")),
            "path": record.get("path"),
            "expected_label": record.get("new_label"),
            "actual_label": record.get("new_label"),
            "status": "passed",
        }
        for record in writeback["applied"]
    ] + [
        {
            "proposal_id": record.get("proposal_id"),
            "index": record.get("actual_index", record.get("index")),
            "path": record.get("path"),
            "expected_label": record.get("new_label"),
            "actual_label": None,
            "status": "failed",
            "error": record.get("reason"),
        }
        for record in writeback["failed"]
    ]
    apply_summary = {
        "requested_count": len(changes or []),
        "applied": [apply_summary_applied_record(record) for record in writeback["applied"]],
        "skipped": [apply_summary_skipped_record(record) for record in writeback["skipped"]],
        "verification": verification,
        "backup_path": backup_path,
    }

    def finalize(download_summary):
        attach_writeback_summary(download_summary, writeback)
        return wrap_apply_result(download_summary, apply_summary)

    # Publish existing artwork under the new playlist label after verified writes.
    # Old files are retained so a playlist backup remains usable.
    from artwork_resolver import artwork_path, valid_image_file, THUMBNAIL_TYPES
    from safe_io import atomic_write_bytes
    for record in writeback['applied']:
        if not thumbnails_dir or not record.get('system') or not record.get('old_label') or record['old_label'] == record['new_label']:
            continue
        for kind in THUMBNAIL_TYPES:
            old = artwork_path(thumbnails_dir, record['system'], record['old_label'], kind)
            target = artwork_path(thumbnails_dir, record['system'], record['new_label'], kind)
            if not valid_image_file(target) and valid_image_file(old):
                atomic_write_bytes(target, old.read_bytes())
    if not download_tasks:
        return finalize(downloader.empty_summary(0))
    if not download_thumbnails:
        return finalize(downloader.skipped_summary(download_tasks, "已按用户选项跳过下载"))
    download_summary = downloader.download_batch(download_tasks, progress_callback=progress_callback)
    return finalize(download_summary)
