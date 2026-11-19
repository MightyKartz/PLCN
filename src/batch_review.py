"""Read-only whole-library review and application of exactly that reviewed plan."""
import re

import mtp_runtime as mtp
from tempfile import TemporaryDirectory

import playlist_service
from playlist_browser import artwork_statuses, open_artwork_reader
from playlist_transport import apply_playlist
from retroarch_scanner import is_adb_uri, materialize_adb_file, scan_retroarch_target
from safe_io import file_digest
from task_control import TaskCancelled, checkpoint
from thumbnail_downloader import ThumbnailDownloader

HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]')


def prepare_review(directory, thumbnails, source, overrides, options, progress, cancel_check):
    scan = scan_retroarch_target(directory)
    playlists = scan['playlists']
    if not playlists:
        raise ValueError('没有找到可分析的游戏列表')
    plans, rows = [], []
    for index, entry in enumerate(playlists):
        checkpoint(cancel_check)
        system, path = entry['system'], entry['path']
        progress(index, len(playlists), '正在分析 ' + system)
        row = {'system': system, 'path': path, 'names': 0, 'artwork': 0, 'review': 0, 'error': None}
        try:
            with TemporaryDirectory(prefix='plcn-batch-review-') as staging:
                local = mtp.materialize(path, staging) if mtp.is_mtp(path) else materialize_adb_file(path, cache_dir=staging) if is_adb_uri(path) else path
                digest = file_digest(local)
                changes = playlist_service.analyze_playlist(local, system, source, thumbnails, manual_overrides_path=overrides, verify_artwork=options['download_thumbnails'], source_playlist_path=path)
                readers, selected = {}, []
                for change in changes:
                    current = change.get('original_item_label') or change.get('original_label') or ''
                    if not options['write_names']:
                        change['new_label'] = current
                        item_system = change.get('system') or system
                        if item_system not in readers:
                            readers[item_system] = open_artwork_reader(thumbnails, item_system)
                        resolver, lookups, image_error = readers[item_system]
                        if image_error:
                            raise RuntimeError(image_error)
                        change['artwork'] = artwork_statuses(current, change.get('path'), resolver, lookups, thumbnails, item_system)
                    label = (change.get('new_label') or '').strip()
                    artwork = change.get('artwork') or {}
                    missing = any(image['status'] != 'exists' for image in artwork.values()) if artwork else not change.get('cover_exists')
                    # Only games that still lack something count as manual work;
                    # complete games the matcher cannot verify are left alone.
                    needs_name = options['write_names'] and not HAN.search(current)
                    needs_artwork = options['download_thumbnails'] and missing
                    if change.get('identity', {}).get('requires_review') or not label:
                        row['review'] += int(needs_name or needs_artwork)
                        continue
                    artwork_missing = options['download_thumbnails'] and (
                        change.get('artwork_gallery_status') in {'unavailable', 'not_found'}
                        or not change.get('thumbnail_source'))
                    # A name the catalogue cannot translate is still manual work.
                    row['review'] += int((needs_name and not HAN.search(label))
                                         or (artwork_missing and needs_artwork))
                    if artwork_missing:
                        # The gallery could not verify this source; stripping it keeps
                        # the apply step from downloading artwork for the rename below.
                        change['thumbnail_source'] = None
                    rename = options['write_names'] and label != current.strip()
                    images = needs_artwork and not artwork_missing
                    if rename or images:
                        selected.append(change)
                        row['names'] += int(rename)
                        row['artwork'] += int(images)
                plans.append({'path': path, 'digest': digest, 'changes': selected, 'system': system})
        except (OSError, ValueError, RuntimeError) as error:
            row['error'] = str(error)
        rows.append(row)
    checkpoint(cancel_check)
    return {'plans': plans, 'rows': rows, 'thumbnails_dir': thumbnails, 'options': options}


def apply_review(review, progress, cancel_check, continue_on_error=True):
    summaries, errors, results = [], [], []
    for row in review['rows']:
        if row['error']:
            errors.append(row['system'] + ': ' + row['error'])
    if errors and not continue_on_error:
        raise ValueError('汇总包含读取失败的主机，请修正后重新分析')
    plans = [plan for plan in review['plans'] if plan['changes']]
    for index, plan in enumerate(plans):
        if cancel_check():
            break
        progress(index, len(plans), '正在应用 ' + plan['system'])
        try:
            result = apply_playlist(plan['path'], plan['changes'], review['thumbnails_dir'], options=review['options'],
                                    progress=lambda _a, _b, text: progress(index, len(plans), text),
                                    cancel_check=cancel_check, expected_digest=plan['digest'])
            results.append({'system': plan['system'], **result})
            summaries.append(result['download_summary'])
        except TaskCancelled:
            break
        except (OSError, ValueError, RuntimeError) as error:
            errors.append(plan['system'] + ': ' + str(error))
            if not continue_on_error:
                raise
    return {'processed_count': len(results), 'applied_count': sum(r['applied_count'] for r in results),
            'errors': errors, 'playlists': results, 'download_summary': ThumbnailDownloader.merge_summaries(summaries)}
