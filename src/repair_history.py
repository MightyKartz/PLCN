"""Local writeback receipts and guarded restoration of recorded backups."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid

import app_paths
from safe_io import atomic_write_bytes, atomic_write_json, file_digest, file_lock


def history_dir():
    return app_paths.user_data_dir() / 'history'


def record_write(playlist, backup, applied_count):
    if not backup or not applied_count:
        return None
    entry = {
        'id': uuid.uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat(),
        'playlist': str(Path(playlist).resolve()), 'backup': str(Path(backup).resolve()),
        'after_sha256': file_digest(playlist), 'backup_sha256': file_digest(backup),
        'applied_count': applied_count, 'restored_at': None,
    }
    atomic_write_json(history_dir() / (entry['id'] + '.json'), entry)
    return entry['id']


def list_history():
    entries = []
    for file in sorted(history_dir().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            entries.append(json.loads(file.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    return entries


def restore(entry_id):
    if not isinstance(entry_id, str) or len(entry_id) != 32 or any(c not in '0123456789abcdef' for c in entry_id):
        raise ValueError('无效的历史记录')
    receipt = history_dir() / (entry_id + '.json')
    with file_lock(receipt):
        entry = json.loads(receipt.read_text(encoding='utf-8'))
        if entry.get('restored_at'):
            raise ValueError('该记录已经恢复')
        target, backup = Path(entry['playlist']), Path(entry['backup'])
        with file_lock(target):
            if file_digest(target) != entry['after_sha256']:
                raise ValueError('游戏列表在修复后已发生变化，拒绝覆盖。请手动检查备份。')
            if file_digest(backup) != entry['backup_sha256']:
                raise ValueError('备份已发生变化，拒绝恢复')
            content = backup.read_bytes()
            original = json.loads(content.decode('utf-8-sig'))
            if not isinstance(original, dict) or not isinstance(original.get('items'), list):
                raise ValueError('备份不是有效游戏列表')
            before_restore = str(backup.parent / (backup.name + '.before-restore-' + uuid.uuid4().hex[:12] + '.bak'))
            shutil.copy2(target, before_restore)
            atomic_write_bytes(target, content, expected_digest=entry['after_sha256'])
            if file_digest(target) != entry['backup_sha256']:
                raise RuntimeError('恢复后验证失败；已保留恢复前备份')
            entry.update(restored_at=datetime.now(timezone.utc).isoformat(), before_restore_backup=before_restore)
            atomic_write_json(receipt, entry)
    return entry
