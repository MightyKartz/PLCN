"""Reconcile playlist entries with file-manager operations recorded in the session."""
import hashlib
import json
from pathlib import PurePosixPath

import content_scan as scan
import m3u_transaction as tx
import mtp_runtime as mtp
from retroarch_scanner import scan_retroarch_target
from rom_paths import split_archive


def preview(root, changes):
    """Match recorded file operations against playlist entries; returns plan + public summary."""
    if not isinstance(changes, list):
        raise ValueError('改动记录无效')
    library = scan_retroarch_target(root)
    if not library['connected']:
        raise ValueError('无法读取游戏库，请重新连接后再同步')
    mounts = scan.storage_mounts(root) if mtp.is_mtp(root) else {}

    def launch_path(path):
        if not isinstance(path, str) or not path:
            return None
        if not mtp.is_mtp(path):
            return path.replace('\\', '/')
        try:
            _, storage, parts = mtp.parse(path)
        except ValueError:
            return None
        mount = mounts.get(storage)
        return mount + '/' + '/'.join(parts) if mount else None

    rules = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        action, path, folder = change.get('action'), change.get('path'), bool(change.get('folder'))
        if action == 'rename' and isinstance(change.get('to'), str):
            rules.append({'kind': 'rename', 'old': launch_path(path), 'new': launch_path(change['to']),
                          'dir': folder, 'source': path})
        elif action == 'delete' and isinstance(path, str):
            rules.append({'kind': 'delete', 'old': launch_path(path), 'dir': folder, 'source': path})

    writes, dependencies, renamed, removed, matched = {}, [], [], [], set()
    for row in library['playlists']:
        raw = scan.read(row['path'])
        if raw is None:
            raise ValueError('播放列表已移除，请重新读取游戏库')
        data = json.loads(raw.decode('utf-8-sig'))
        dependencies.append({'path': row['path'], 'digest': mtp.digest(raw)})
        items, changed = [], False
        for item in data['items']:
            physical, inner = split_archive(item.get('path', ''))
            physical = physical.replace('\\', '/')
            rule = next((candidate for candidate in rules if candidate['old'] and
                         (physical == candidate['old'] or
                          (candidate['dir'] and physical.startswith(candidate['old'].rstrip('/') + '/')))), None)
            if rule is None:
                items.append(item)
                continue
            changed, _ = True, matched.add(id(rule))
            if rule['kind'] == 'rename' and rule['new']:
                updated = dict(item)
                updated['path'] = rule['new'] + physical[len(rule['old']):] + ('#' + inner if inner else '')
                renamed.append({'playlist': row['name'], 'label': item.get('label') or item['path'],
                                'old': item['path'], 'new': updated['path']})
                items.append(updated)
            else:
                removed.append({'playlist': row['name'], 'label': item.get('label') or item['path'],
                                'path': item['path']})
        if changed:
            writes[row['path']] = {'expected': next(entry['digest'] for entry in dependencies if entry['path'] == row['path']),
                                   'document': {**data, 'items': items}}
    unmatched = [rule['source'] for rule in rules if id(rule) not in matched]
    public = {'renamed': renamed, 'removed': removed, 'unmatched': unmatched}
    signature = hashlib.sha256(json.dumps({'public': public, 'dependencies': dependencies},
                                          sort_keys=True).encode()).hexdigest()
    return {'public': {**public, 'signature': signature}, 'signature': signature, 'dependencies': dependencies,
            'writes': [{'kind': 'playlist', 'path': path, 'expected': plan['expected'],
                        'content': (json.dumps(plan['document'], ensure_ascii=False, indent=2) + '\n').encode()}
                       for path, plan in writes.items()]}


def apply(root, changes, signature):
    plan = preview(root, changes)
    if plan['signature'] != signature:
        raise ValueError('文件或播放列表已变化，请重新同步')
    if not plan['writes']:
        return {'playlists': []}
    transaction = {'playlist': plan['writes'][0]['path'], 'label': '同步文件管理改动',
                   'mode': 'game_file_sync', 'can_apply': True,
                   'dependencies': plan['dependencies'], 'writes': plan['writes'], 'patches': []}
    result = tx.start(transaction)
    if result['status'] != 'applied':
        raise RuntimeError(result['error'] or '播放列表更新未完成')
    return {'playlists': [write['path'] for write in plan['writes']]}
