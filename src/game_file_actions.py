"""Mutate standalone cartridge files without breaking known playlist entries."""
from pathlib import Path, PurePosixPath
import json

import content_scan as scan
import mtp_runtime as mtp
from retroarch_scanner import scan_retroarch_target
from rom_paths import split_archive
from safe_io import file_lock

CARTRIDGE_SUFFIXES = {'.nes', '.fds', '.sfc', '.smc', '.gb', '.gbc', '.gba', '.md', '.gen', '.smd', '.sms', '.gg', '.n64', '.z64', '.v64'}


def validate(payload):
    path, root, name = (payload.get(key, '') for key in ('path', 'root', 'name'))
    action = payload.get('action')
    if action != 'rename' or not all(isinstance(value, str) for value in (path, root, name)):
        raise ValueError('文件操作参数无效')
    remote = mtp.is_mtp(path)
    if remote:
        serial, _, parts = mtp.parse(path)
        if not parts or not mtp.is_mtp(root) or mtp.parse(root)[0] != serial:
            raise ValueError('请先打开此掌机的 RetroArch 游戏库')
        filename = parts[-1]
    else:
        local = Path(path)
        if not local.is_absolute():
            raise ValueError('请选择绝对文件路径')
        filename = local.name
    suffix = PurePosixPath(filename).suffix
    if suffix.lower() not in CARTRIDGE_SUFFIXES:
        raise ValueError('目前只支持重命名和删除独立卡带游戏文件')
    if (not name or name in {'.', '..'} or '\\' in name or '/' in name
                               or '\x00' in name or PurePosixPath(name).suffix != suffix):
        raise ValueError('请输入有效文件名并保留原扩展名')
    return path, root, name, filename


def apply(path, root, name, filename):
    remote = mtp.is_mtp(path)
    if root and not root.startswith('adb://') and mtp.is_mtp(root) == remote:
        library = scan_retroarch_target(root)
        if not library['connected']:
            raise ValueError('无法读取 RetroArch 游戏库，无法核对播放列表')
        for playlist in library['playlists']:
            document = json.loads(scan.read(playlist['path']).decode('utf-8-sig'))
            for item in document['items']:
                launch = split_archive(item.get('path', ''))[0].replace('\\', '/')
                if PurePosixPath(launch).name.casefold() == filename.casefold():
                    raise ValueError('文件名出现在播放列表中，请先检查列表引用：' + playlist['name'])
    if remote:
        mtp.change_game_file(path, name)
    else:
        source = Path(path)
        with file_lock(path):
            if source.is_symlink() or not source.is_file():
                raise ValueError('游戏文件已移动或不存在')
            if name != filename:
                target = source.with_name(name)
                if target.exists() or target.is_symlink():
                    raise ValueError('已有同名文件')
                source.rename(target)
