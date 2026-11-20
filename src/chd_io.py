"""Bounded-memory local/MTP image I/O; all paths are owned by reviewed plans."""
from pathlib import Path
import shutil
import tempfile

import chd_cue
import mtp_runtime as mtp


def key(path):
    return mtp.uri(*mtp.parse(path)[:2],'/'.join(mtp.parse(path)[2])) if mtp.is_mtp(path) else Path(path).resolve().as_posix()


def copy_to(source,target,cancelled=lambda: None):
    target=Path(target)
    if mtp.is_mtp(source):
        mtp.download_file(source,target,cancelled)
    else:
        with Path(source).open('rb') as reader,target.open('xb') as writer:
            while True:
                cancelled();chunk=reader.read(1024*1024)
                if not chunk: break
                writer.write(chunk)
    return chd_cue.fingerprint(target,cancelled)


def digest(path,cancelled=lambda: None):
    if mtp.is_mtp(path):
        entry=mtp.stat_file(path)
        if not entry: return None
        if shutil.disk_usage(tempfile.gettempdir()).free<entry['size']+64*1024*1024:
            raise ValueError('电脑临时卷空间不足，无法回读校验')
        with tempfile.TemporaryDirectory(prefix='plcn-image-check-') as temporary:
            target=Path(temporary)/'image'
            return copy_to(path,target,cancelled)
    target=Path(path)
    if target.is_symlink(): raise ValueError('源或目标已变为符号链接，请先核对：'+str(path))
    return chd_cue.fingerprint(target,cancelled) if target.exists() else None


def volume(path):
    return ('mtp',*mtp.parse(path)[:2]) if mtp.is_mtp(path) else ('local',Path(path).parent.stat().st_dev)


def free_bytes(path):
    return mtp.free_bytes(path) if mtp.is_mtp(path) else shutil.disk_usage(Path(path).parent).free


def put_new(target,source,expected,stage,cancelled=lambda: None):
    if mtp.is_mtp(target): return mtp.upload_file(target,source,expected,stage,cancelled)
    existing=digest(target,cancelled)
    if existing is not None:
        if existing!=expected: raise ValueError('目标已有不同文件：'+target)
        return
    stage=Path(stage)
    if stage.exists():
        if chd_cue.fingerprint(stage,cancelled)!=expected: raise ValueError('暂存文件需要人工核对：'+str(stage))
    elif copy_to(source,stage,cancelled)!=expected:
        raise ValueError('复制校验失败')
    cancelled()
    if Path(target).exists(): raise ValueError('目标在复制期间出现：'+target)
    stage.rename(target)
    if digest(target,cancelled)!=expected: raise ValueError('目标回读校验失败：'+target)


class RemoveUnverified(RuntimeError):
    """The delete was issued but its outcome could not be verified.

    Callers must not silently re-list the path for automatic deletion: the file
    may already be gone, and a user-restored copy must never be re-removed."""


def object_id(path):
    """Device object id for identity-checked deletes; None when not applicable."""
    if not mtp.is_mtp(path): return None
    entry=mtp.stat_file(path)
    return entry['id'] if entry else None


def remove(path,expected,cancelled=lambda: None,object_id=None):
    if mtp.is_mtp(path):
        if object_id is None: return mtp.remove_file(path,expected,cancelled)
        return mtp.remove_file(path,expected,cancelled,object_id)
    if digest(path,cancelled)!=expected: raise ValueError('待移除文件已变化：'+path)
    Path(path).unlink()
