"""Durable undo receipts for one-click playlist completion runs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import uuid

import app_paths
import mtp_runtime as mtp
import repair_history
from retroarch_scanner import is_adb_uri, parse_adb_uri
from safe_io import atomic_write_bytes, atomic_write_json, file_lock
from task_control import checkpoint

MAX_RECEIPTS = 20


def receipts_dir():
    return app_paths.user_data_dir() / 'completion-receipts'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate_id(receipt_id):
    if not isinstance(receipt_id, str) or len(receipt_id) != 32 or any(c not in '0123456789abcdef' for c in receipt_id):
        raise ValueError('无效的补全记录')
    return receipt_id


def _receipt_path(receipt_id):
    return receipts_dir() / (_validate_id(receipt_id) + '.json')


def _prune():
    files = sorted(receipts_dir().glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
    for file in files[MAX_RECEIPTS:]:
        file.unlink(missing_ok=True)


def create(results, label):
    """Persist a receipt for the undo targets recorded by apply_playlist."""
    if isinstance(results, dict):
        results = [results]
    playlists, images = [], []
    for result in results or []:
        undo = (result or {}).get('undo') or {}
        playlist = undo.get('playlist')
        if playlist and (playlist.get('backup') or playlist.get('history_id')):
            playlists.append(playlist)
        images.extend(image for image in undo.get('images') or []
                      if image.get('destination') and image.get('sha256'))
    if not playlists and not images:
        return None
    receipt = {
        'id': uuid.uuid4().hex,
        'created_at': _now(),
        'label': label,
        'status': 'applied',
        'playlists': playlists,
        'images': images,
        'outcome': None,
        'undone_at': None,
    }
    receipts_dir().mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipts_dir() / (receipt['id'] + '.json'), receipt)
    _prune()
    return receipt['id']


def list_receipts():
    entries = []
    for file in sorted(receipts_dir().glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        entries.append({
            'id': data.get('id'), 'created_at': data.get('created_at'), 'label': data.get('label'),
            'status': data.get('status'),
            'counts': {'playlists': len(data.get('playlists') or []), 'images': len(data.get('images') or [])},
        })
    return entries


def get(receipt_id):
    path = _receipt_path(receipt_id)
    if not path.is_file():
        raise ValueError('找不到这次补全记录')
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _read_target(target):
    if mtp.is_mtp(target):
        return mtp.read(target)
    if is_adb_uri(target):
        from single_artwork import read_target
        return read_target(target)
    path = Path(target)
    return path.read_bytes() if path.is_file() else None


def _write_target(target, content, expected_sha):
    from single_artwork import write_target
    return write_target(target, content, expected_sha)


def _remove_target(target, expected_sha):
    if mtp.is_mtp(target):
        return mtp.remove_verified(target, expected_sha)
    if is_adb_uri(target):
        from single_artwork import adb_command, read_target
        serial, remote = parse_adb_uri(target)
        adb_command(serial, 'rm -f ' + shlex.quote(remote))
        if read_target(target) is not None:
            raise RuntimeError('ADB 移除后核对失败：' + target)
        return
    Path(target).unlink()


def _image_step(image):
    """Undo one image write; returns (result, skip_reason)."""
    destination = image.get('destination')
    current = _read_target(destination)
    if current is None:
        return 'missing', 'missing'
    if _sha256(current) != image.get('sha256'):
        return 'changed', 'changed'
    backup = image.get('replaced_backup')
    if backup:
        backup_file = Path(backup)
        if not backup_file.is_file():
            return 'error', 'backup_missing'
        if is_adb_uri(destination) or mtp.is_mtp(destination):
            _write_target(destination, backup_file.read_bytes(), image['sha256'])
        else:
            atomic_write_bytes(destination, backup_file.read_bytes(), expected_digest=image['sha256'])
        return 'restored', None
    _remove_target(destination, image['sha256'])
    return 'removed', None


def _playlist_step(playlist):
    """Undo one playlist write; returns (result, skip_reason)."""
    path = playlist.get('path')
    current = _read_target(path)
    if current is None:
        return 'missing', 'missing'
    if _sha256(current) != playlist.get('after_sha256'):
        return 'changed', 'changed'
    if playlist.get('history_id'):
        repair_history.restore(playlist['history_id'])
        return 'restored', None
    backup = playlist.get('backup')
    if not backup:
        return 'backup_missing', 'backup_missing'
    backup_bytes = _read_target(backup)
    if backup_bytes is None:
        return 'error', 'backup_missing'
    if playlist.get('transport') == 'local':
        atomic_write_bytes(path, backup_bytes, expected_digest=playlist['after_sha256'])
    else:
        _write_target(path, backup_bytes, playlist['after_sha256'])
    return 'restored', None


def undo(receipt_id, progress=None, cancel_check=None):
    """Restore a recorded completion run, image targets first (reverse order)."""
    progress = progress or (lambda *args: None)
    path = _receipt_path(receipt_id)
    if not path.is_file():
        raise ValueError('找不到这次补全记录')
    with file_lock(path):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('status') != 'applied':
            raise ValueError('这次补全已撤销')
        images = receipt.get('images') or []
        playlists = receipt.get('playlists') or []
        steps = [('image', item) for item in reversed(images)] + [('playlist', item) for item in playlists]
        total = len(steps) or 1
        outcome = {'images': [], 'playlists': []}
        skipped = []
        restored_playlists = removed_images = restored_images = 0
        for index, (kind, item) in enumerate(steps):
            checkpoint(cancel_check)
            progress(index, total, '正在撤销补全…')
            target = item.get('destination' if kind == 'image' else 'path')
            try:
                result, reason = _image_step(item) if kind == 'image' else _playlist_step(item)
            except Exception as error:
                result, reason = 'error', str(error)
            record = {'target': target, 'result': result}
            if reason:
                record['reason'] = reason
            outcome[kind + 's'].append(record)
            if result == 'restored':
                if kind == 'image':
                    restored_images += 1
                else:
                    restored_playlists += 1
            elif result == 'removed':
                removed_images += 1
            else:
                skipped.append({'target': target, 'reason': reason or result})
        receipt['outcome'] = outcome
        receipt['status'] = 'undone' if not skipped else 'partially_undone'
        receipt['undone_at'] = _now()
        atomic_write_json(path, receipt)
    return {'restored_playlists': restored_playlists, 'removed_images': removed_images,
            'restored_images': restored_images, 'skipped': skipped}
