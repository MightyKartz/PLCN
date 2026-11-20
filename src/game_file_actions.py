"""Plain file-manager operations: rename, delete, copy."""
from pathlib import Path, PurePosixPath
import itertools
import shutil
import tempfile
import uuid

import chd_io
import mtp_runtime as mtp
from safe_io import file_lock
from task_control import TaskCancelled


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
    elif not Path(path).is_absolute():
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


def validate_add(payload):
    """Local files/folders copied into the browsed directory (local or MTP)."""
    sources, directory, root = payload.get('sources'), payload.get('directory'), payload.get('root')
    if (not isinstance(sources, list) or not sources or len(sources) > 500
            or any(not isinstance(source, str) or mtp.is_mtp(source) for source in sources)
            or not isinstance(directory, str) or not isinstance(root, str)):
        raise ValueError('添加参数无效')
    remote = mtp.is_mtp(directory)
    if remote:
        if not mtp.is_mtp(root) or mtp.parse(root)[0] != mtp.parse(directory)[0]:
            raise ValueError('请先打开此掌机的 RetroArch 游戏库')
    elif not Path(directory).is_dir():
        raise ValueError('目标目录不存在')
    else:
        destination = Path(directory).resolve()
        if any(Path(source).resolve().is_dir() and destination.is_relative_to(Path(source).resolve())
               for source in sources):
            raise ValueError('不能把文件夹复制到自身内部')
    for source in sources:
        if not Path(source).is_absolute() or not Path(source).exists():
            raise ValueError('请选择电脑上存在的文件或文件夹')
    return [str(Path(source)) for source in sources], directory, remote, payload.get('overwrite') is True


def _walk_remote(path):
    """All descendant files (with relative names) and folder paths under an MTP path."""
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
    """Permanently delete a file or folder; return the deleted path."""
    if not remote:
        source = Path(path)
        if not source.exists() and not source.is_symlink():
            raise ValueError('文件已移动或不存在')
        with file_lock(path):
            if source.is_dir() and not source.is_symlink():
                shutil.rmtree(source)
            else:
                source.unlink()
        return path
    files, folders = _walk_remote(path)
    for index, entry in enumerate(files):
        cancelled()
        progress(index, len(files), '删除：' + entry['path'])
        mtp.delete_object(entry['path'])
    for folder in sorted(folders, key=lambda f: len(mtp.parse(f)[2]), reverse=True):
        cancelled()
        mtp.delete_object(folder)
    return path


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
        chd_io.copy_to(source, local, cancelled)
        _upload_local(local, destination, cancelled)


def _upload_local(source, destination, cancelled):
    expected = chd_io.digest(str(source), cancelled)
    stage = destination + '.plcn-' + uuid.uuid4().hex
    try:
        mtp.upload_file(destination, str(source), expected, stage, cancelled)
    except Exception:
        try:
            mtp.delete_object(stage)
        except Exception:
            pass
        raise


def _remove_destination(target, remote):
    """Best-effort cleanup of a partially copied destination."""
    try:
        if remote:
            files, folders = _walk_remote(target)
            for entry in files:
                mtp.delete_object(entry['path'])
            for folder in sorted(folders, key=lambda f: len(mtp.parse(f)[2]), reverse=True):
                mtp.delete_object(folder)
        else:
            target_path = Path(target)
            if target_path.is_dir() and not target_path.is_symlink():
                shutil.rmtree(target_path)
            else:
                target_path.unlink(missing_ok=True)
    except Exception:
        pass


def _write_item(item, target, remote, cancelled, on_file):
    """Write one source file/folder to an empty destination path."""
    is_dir = item['source'].is_dir()
    if remote:
        if is_dir:
            _ensure_remote_dir(target)
            for folder in item['folders']:
                _ensure_remote_dir(target + '/' + folder.relative_to(item['source']).as_posix())
        for entry in item['files']:
            cancelled()
            relative = entry.relative_to(item['source']).as_posix() if is_dir else item['name']
            _upload_local(entry, target + '/' + relative if is_dir else target, cancelled)
            on_file()
    elif is_dir:
        Path(target).mkdir()
        for folder in item['folders']:
            (Path(target) / folder.relative_to(item['source'])).mkdir(parents=True, exist_ok=True)
        for entry in item['files']:
            cancelled()
            (Path(target) / entry.relative_to(item['source'])).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, Path(target) / entry.relative_to(item['source']))
            on_file()
    else:
        cancelled()
        with file_lock(str(item['source'])):
            shutil.copy2(item['source'], target)
        on_file()


def _rename_into(target, staged, remote):
    if remote:
        mtp.rename_object(staged, mtp.parse(target)[2][-1])
    else:
        Path(staged).rename(target)


def apply_add(sources, directory, remote, overwrite=False, progress=lambda *args: None, cancelled=lambda: None):
    """Copy local sources into the browsed directory.

    Same-named top-level items are skipped, or — when overwrite is set — staged,
    the original is deleted, and the staged copy then takes its name. The report
    keeps copied/replaced/skipped/failed/remaining lists even after cancellation.
    """
    items = []
    for source in sources:
        path = Path(source)
        if path.is_dir():
            files = sorted(entry for entry in path.rglob('*') if entry.is_file())
            folders = sorted(entry for entry in path.rglob('*') if entry.is_dir())
        else:
            files, folders = [path], []
        items.append({'source': path, 'name': path.name, 'files': files, 'folders': folders})
    total = sum(len(item['files']) for item in items)
    result = {'copied': [], 'replaced': [], 'skipped': [], 'failed': [], 'remaining': [], 'destination': directory}
    done = 0
    for index, item in enumerate(items):
        name = item['name']
        target = mtp.join(directory, name) if remote else str(Path(directory) / name)
        exists = mtp.stat_file(target) is not None if remote else (Path(target).exists() or Path(target).is_symlink())
        if exists and not overwrite:
            result['skipped'].append(name)
            done += len(item['files'])
            continue
        staged = target + '.plcn-replace-' + uuid.uuid4().hex if exists else target

        def note_file():
            nonlocal done
            done += 1
            progress(done, total, '复制：' + name)

        try:
            _write_item(item, staged, remote, cancelled, note_file)
            if exists:
                cancelled()
                apply_delete(target, remote, cancelled=cancelled)
                _rename_into(target, staged, remote)
                result['replaced'].append(name)
            else:
                result['copied'].append(name)
        except TaskCancelled as error:
            _remove_destination(staged, remote)
            result['failed'].append({'name': name, 'error': str(error)})
            result['remaining'] = [pending['name'] for pending in items[index + 1:]]
            return result
        except Exception as error:
            _remove_destination(staged, remote)
            result['failed'].append({'name': name, 'error': str(error)})
            result['remaining'] = [pending['name'] for pending in items[index + 1:]]
            return result
    return result
