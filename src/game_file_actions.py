"""Plain file-manager operations: rename, delete-to-backup, copy."""
from pathlib import Path, PurePosixPath
import itertools
import shutil
import tempfile
import uuid

import app_paths
import chd_io
import mtp_runtime as mtp
from safe_io import file_lock


def validate_op(payload):
    """Boundary and argument checks for plain file-manager operations."""
    action = payload.get('action')
    path, root = payload.get('path'), payload.get('root')
    if action not in {'rename', 'delete', 'copy'} or not isinstance(path, str) or not isinstance(root, str):
        raise ValueError('文件操作参数无效')
    remote = mtp.is_mtp(path)
    if remote:
        serial, _, parts = mtp.parse(path)
        if not parts or not mtp.is_mtp(root) or mtp.parse(root)[0] != serial:
            raise ValueError('请先打开此掌机的 RetroArch 游戏库')
    elif not Path(path).is_absolute() or mtp.is_mtp(root):
        raise ValueError('请选择本地文件')
    if action == 'rename':
        name = payload.get('name')
        if (not isinstance(name, str) or not name or name in {'.', '..'}
                or '/' in name or '\\' in name or '\x00' in name):
            raise ValueError('请输入有效文件名')
        return path, name, remote
    if action == 'copy':
        directory = payload.get('directory')
        if not isinstance(directory, str) or mtp.is_mtp(directory) != remote:
            raise ValueError('目标目录无效')
        if remote and mtp.parse(directory)[0] != mtp.parse(path)[0]:
            raise ValueError('目标目录必须属于同一台设备')
        if remote:
            if mtp.parse(directory)[2][:len(mtp.parse(path)[2])] == mtp.parse(path)[2]:
                raise ValueError('不能复制到自身或它的子目录')
        elif not Path(directory).is_dir():
            raise ValueError('目标目录不存在')
        elif Path(path).is_dir() and Path(directory).resolve().is_relative_to(Path(path).resolve()):
            raise ValueError('不能复制到自身或它的子目录')
        return path, directory, remote
    return path, None, remote


def _walk_remote(path):
    """All descendant files (with backup-relative names) and folder paths under an MTP path."""
    entry = mtp.stat_file(path)
    if entry is None:
        raise ValueError('文件已移动或不存在')
    if not entry['folder']:
        return [{'path': path, 'relative': PurePosixPath(path).name}], []
    files, folders, queue = [], [path], [(path, '')]
    while queue:
        current, rel_prefix = queue.pop(0)
        for child in mtp.listing(current):
            child_path = mtp.join(current, child['name'])
            relative = rel_prefix + '/' + child['name'] if rel_prefix else child['name']
            if child['folder']:
                folders.append(child_path)
                queue.append((child_path, relative))
            else:
                files.append({'path': child_path, 'relative': relative})
    return files, folders


def apply_rename(path, name, remote):
    if remote:
        return {'new_path': mtp.rename_object(path, name)}
    source = Path(path)
    if not source.exists():
        raise ValueError('文件已移动或不存在')
    target = source.with_name(name)
    if target.exists() or target.is_symlink():
        raise ValueError('已有同名文件')
    with file_lock(path):
        source.rename(target)
    return {'new_path': str(target)}


def _ensure_remote_dir(path):
    with mtp.session(path) as (handle, storage, parts):
        mtp.resolve(handle, storage, parts, create=True)


def apply_delete(path, remote, progress=lambda *args: None, cancelled=lambda: None):
    """Move a file or folder into a local backup folder; return the backup directory."""
    backup = app_paths.user_data_dir() / 'file-trash' / uuid.uuid4().hex
    if not remote:
        source = Path(path)
        if not source.exists():
            raise ValueError('文件已移动或不存在')
        backup.mkdir(parents=True)
        with file_lock(path):
            shutil.move(str(source), str(backup / source.name))
        return str(backup)
    files, folders = _walk_remote(path)
    root_name = PurePosixPath(path).name
    backup.mkdir(parents=True)
    for index, entry in enumerate(files):
        cancelled()
        progress(index, len(files), '备份：' + entry['path'])
        target = backup / root_name / entry['relative'] if folders else backup / entry['relative']
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = chd_io.copy_to(entry['path'], target, cancelled)
        chd_io.remove(entry['path'], digest, cancelled)
    for folder in sorted(folders, key=lambda f: len(mtp.parse(f)[2]), reverse=True):
        mtp.delete_object(folder)
    return str(backup)


def _unique_name(directory, name, remote):
    def exists(candidate):
        target = mtp.join(directory, candidate) if remote else str(Path(directory) / candidate)
        return mtp.stat_file(target) is not None if remote else Path(target).exists()
    if not exists(name):
        return name
    stem, dot, ext = name.rpartition('.')
    base, suffix = (stem, dot + ext) if dot and stem else (name, '')
    for index in itertools.count(1):
        candidate = base + ' 副本' + (f' {index}' if index > 1 else '') + suffix
        if not exists(candidate):
            return candidate


def apply_copy(path, directory, remote, progress=lambda *args: None, cancelled=lambda: None):
    """Copy a file or folder into a directory, auto-renaming on conflict; return the new path."""
    name = _unique_name(directory, PurePosixPath(path).name, remote)
    if not remote:
        source = Path(path)
        target = Path(directory) / name
        if not source.exists():
            raise ValueError('文件已移动或不存在')
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            with file_lock(path):
                shutil.copy2(source, target)
        return str(target)
    destination = mtp.join(directory, name)
    files, folders = _walk_remote(path)
    if folders:
        _ensure_remote_dir(destination)
        for folder in folders[1:]:
            _ensure_remote_dir(destination + folder[len(path):])
    for index, entry in enumerate(files):
        cancelled()
        progress(index, len(files), '复制：' + entry['path'])
        target = mtp.join(destination, entry['relative']) if folders else destination
        _remote_copy_file(entry['path'], target, cancelled)
    return destination


def _remote_copy_file(source, destination, cancelled):
    """Download to a temp file, then upload verified; cleans up a stray stage on failure."""
    with tempfile.TemporaryDirectory(prefix='plcn-copy-') as temporary:
        local = Path(temporary) / 'payload'
        expected = chd_io.copy_to(source, local, cancelled)
        stage = destination + '.plcn-' + uuid.uuid4().hex
        try:
            mtp.upload_file(destination, str(local), expected, stage, cancelled)
        except Exception:
            try:
                mtp.delete_object(stage)
            except Exception:
                pass
            raise
