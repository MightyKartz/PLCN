"""Atomic local writes and cooperative cross-process file locking."""
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def file_lock(path):
    """Fail fast; never guess that another process's lock is stale."""
    lock = Path(str(Path(path).resolve()) + '.plcn-lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f'文件正在被 PLCN 使用：{path}。若程序曾异常退出，请确认没有运行任务后移除 {lock}') from exc
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def atomic_write_bytes(path, content, expected_digest=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            shutil.copymode(target, temporary)
        if expected_digest is not None and file_digest(target) != expected_digest:
            raise RuntimeError(f'文件在处理期间已改变，请重新预览：{path}')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_json(path, data, expected_digest=None):
    atomic_write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=4) + '\n').encode('utf-8'), expected_digest)
