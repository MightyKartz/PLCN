"""Track app-downloaded image bytes separately from explicit user choices."""
import hashlib
import json
from pathlib import Path

import app_paths
from artwork_identity import title_key
from safe_io import atomic_write_json, file_lock


def save(records):
    path = app_paths.user_data_dir() / 'artwork-downloads.json'
    with file_lock(path):
        data = json.loads(path.read_text()) if path.exists() else {}
        data.update(records)
        atomic_write_json(path, data)


def mark_stale(row):
    path = app_paths.user_data_dir() / 'artwork-downloads.json'
    if not path.exists() or not row.get('thumbnail_source'):
        return
    from single_artwork import read_target
    data = json.loads(path.read_text())
    replace = {}
    current_titles = {title_key(name) for name in row.get('chinese_title_sources', []) + [row['thumbnail_source']]}
    for kind, image in row.get('artwork', {}).items():
        previous = data.get(image.get('path'))
        if (image['status'] != 'exists' or not previous or not previous.get('automatic')
                or title_key(previous['source']) in current_titles):
            continue
        try:
            content = read_target(image['path'])
        except (OSError, ValueError, RuntimeError) as error:
            row['artwork_message'] = '无法核对旧图片，已保留：' + str(error)
            continue
        if content is not None and hashlib.sha256(content).hexdigest() == previous['sha256']:
            replace[kind] = previous['sha256']
            image['status'] = 'stale'
    if replace:
        row['replace_artwork_hashes'] = replace
        row['match_reason'] += '；将备份并替换来自旧推荐的图片'
        if 'Named_Boxarts' in replace:
            row.update(cover_exists=False, thumbnail_exists=False, local_thumbnail_exists=False,
                       cover_path=None, cover_preview_url=None)
