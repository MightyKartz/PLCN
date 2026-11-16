"""Directory-based incremental playlist imports, independent of name/artwork repair."""
import copy
import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import uuid
import sys
import xml.etree.ElementTree as ET

import app_paths
import mtp_runtime as mtp
from safe_io import atomic_write_bytes, atomic_write_json, file_lock
from task_control import checkpoint
from system_resources import is_system_resource

# Defaults are product recommendations, not hardware performance guarantees.
SYSTEMS = {
    'Nintendo - Nintendo Entertainment System': ('nestopia', 'Nestopia UE', 'nes fds unf unif zip 7z'),
    'Nintendo - Super Nintendo Entertainment System': ('snes9x', 'Snes9x', 'sfc smc zip 7z'),
    'Nintendo - Game Boy': ('gambatte', 'Gambatte', 'gb zip 7z'),
    'Nintendo - Game Boy Color': ('gambatte', 'Gambatte', 'gb gbc zip 7z'),
    'Nintendo - Game Boy Advance': ('mgba', 'mGBA', 'gba zip 7z'),
    'Sega - Mega Drive - Genesis': ('genesis_plus_gx', 'Genesis Plus GX', 'md gen smd bin zip 7z'),
    'Sony - PlayStation': ('pcsx_rearmed', 'PCSX ReARMed', 'cue chd m3u pbp ccd'),
    'Sega - Saturn': ('mednafen_saturn', 'Beetle Saturn（需验证掌机性能）', 'cue chd m3u ccd toc'),
    'FBNeo - Arcade Games': ('fbneo', 'FinalBurn Neo（需匹配 ROM 集）', 'zip 7z'),
    'MAME': ('mame2003_plus', 'MAME 2003-Plus（仅适用于匹配的 ROM 集）', 'zip 7z'),
}
CORE_NAMES = {value[0]: value[1] for value in SYSTEMS.values()}
CORE_NAMES.update({'mesen': 'Mesen', 'fceumm': 'FCEUmm', 'sameboy': 'SameBoy',
                   'gpsp': 'gpSP', 'swanstation': 'SwanStation', 'yabause': 'Yabause',
                   'mamearcade': 'MAME（当前版，需匹配 ROM 集）', 'mame2010': 'MAME 2010'})
ALTERNATIVES = {
    'nestopia': ['nestopia', 'mesen', 'fceumm'], 'gambatte': ['gambatte', 'sameboy'],
    'mgba': ['mgba', 'gpsp'], 'pcsx_rearmed': ['pcsx_rearmed', 'swanstation'],
    'mednafen_saturn': ['mednafen_saturn', 'yabause'],
    'mame2003_plus': ['mame2003_plus', 'mame2010', 'mamearcade'],
}


def join(root, *parts):
    return mtp.join(root, *parts) if mtp.is_mtp(root) else str(Path(root).joinpath(*parts))


def read(path):
    if mtp.is_mtp(path):
        return mtp.read(path)
    target = Path(path)
    return target.read_bytes() if target.exists() else None


def folders(path):
    if mtp.is_mtp(path):
        with mtp.session(path) as (handle, storage, parts):
            entry = mtp.resolve(handle, storage, parts)
            if entry is None or not entry['folder']:
                raise ValueError('游戏目录不存在或不是目录')
            return mtp.children(handle, storage, entry['id'])
    return [{'name': p.name, 'folder': p.is_dir(), 'size': 0 if p.is_dir() else p.stat().st_size}
            for p in Path(path).iterdir() if not p.is_symlink()]


def browse(path):
    if mtp.is_mtp(path):
        serial, storage, parts = mtp.parse(path)
        parent = mtp.uri(serial, storage, '/'.join(parts[:-1]))
    else:
        path = str(Path(path).expanduser().resolve())
        parent = str(Path(path).parent)
    entries = folders(path)
    return {'path': path, 'parent': parent, 'directories': [
        {'name': entry['name'], 'path': join(path, entry['name'])}
        for entry in sorted(entries, key=lambda e: e['name'].casefold()) if entry['folder']]}


def profiles_path():
    return app_paths.user_data_dir() / 'scan_profiles.json'


def profiles():
    path = profiles_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def setup(root):
    if not isinstance(root, str) or not root or root.startswith('adb://'):
        raise ValueError('请选择本地或文件传输游戏库')
    if mtp.is_mtp(root):
        serial, storage, _ = mtp.parse(root)
        browse_root = mtp.uri(serial, storage)
    else:
        root = str(Path(root).expanduser().resolve())
        browse_root = str(Path(root).parent)
    configuration = read(join(root, 'retroarch.cfg'))
    cfg = dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"\n]*)"', configuration.decode('utf-8-sig') if configuration else '', re.M))
    return {'root': root, 'browse_root': browse_root, 'profiles': profiles().get(root, []),
            'core_directory': cfg.get('libretro_directory', ''),
            'systems': [{'name': system, 'extensions': ext, 'recommended': core,
                         'cores': [{'id': c, 'name': CORE_NAMES[c]} for c in ALTERNATIVES.get(core, [core])]}
                        for system, (core, name, ext) in SYSTEMS.items()],
            'android': mtp.is_mtp(root), 'core_suffix': '_android.so' if mtp.is_mtp(root) else '.dll' if sys.platform == 'win32' else '.dylib' if sys.platform == 'darwin' else '.so'}


def playlist_name(system, value=None):
    filename = value or system + '.lpl'
    if not isinstance(filename, str) or not filename.endswith('.lpl') or any(char in filename for char in '/\\\x00\n\r') or filename.startswith('.'):
        raise ValueError('目标列表必须是当前 playlists 目录中的 .lpl 文件名')
    return filename


def validate(payload):
    for key in ('dat_path', 'android_directory', 'abi', 'playlist_name'):
        if not isinstance(payload.get(key, ''), str):
            raise ValueError('扫描配置字段无效')
    fields = ['root', 'directory', 'system', 'core_id', 'core_path', 'extensions']
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in fields):
        raise ValueError('请指定游戏目录、主机、核心、核心路径及扫描格式')
    config = {key: payload[key].strip() for key in fields}
    if config['root'].startswith('adb://') or config['directory'].startswith('adb://'):
        raise ValueError('目录导入请使用文件传输连接或本地目录')
    if config['system'] not in SYSTEMS:
        raise ValueError('不支持的主机')
    filename = playlist_name(config['system'], payload.get('playlist_name'))
    config['playlist_name'] = filename
    default = SYSTEMS[config['system']][0]
    if config['core_id'] not in ALTERNATIVES.get(default, [default]):
        raise ValueError('核心不属于所选主机')
    config.update(abi=payload.get('abi', '').strip(), recursive=payload.get('recursive', True), dat_path=payload.get('dat_path', '').strip(),
                  dat_filter=payload.get('dat_filter', False), android_directory=payload.get('android_directory', '').strip())
    if not isinstance(config['recursive'], bool) or not isinstance(config['dat_filter'], bool):
        raise ValueError('扫描开关无效')
    extensions = config['extensions'].lower().split()
    if any(not re.fullmatch(r'[a-z0-9]+', ext) for ext in extensions):
        raise ValueError('文件格式请用空格分隔，不带点号')
    config['extensions'] = ' '.join(dict.fromkeys(extensions))
    remote = mtp.is_mtp(config['root'])
    if remote:
        serial, storage, _ = mtp.parse(config['root'])
        if mtp.parse(config['directory'])[0] != serial:
            raise ValueError('游戏目录必须属于当前掌机')
        if not config['android_directory'].startswith('/storage/') and not config['android_directory'].startswith('/sdcard/'):
            raise ValueError('请填写掌机中的实际游戏目录，例如 /storage/卡号/Roms/SS')
        if not config['core_path'].startswith('/') or not config['core_path'].endswith('.so'):
            raise ValueError('请填写掌机中已安装核心的完整 .so 路径')
        if config['dat_path'] and mtp.parse(config['dat_path'])[0] != serial:
            raise ValueError('DAT 必须属于当前掌机')
    else:
        for key in ('root', 'directory', 'core_path'):
            config[key] = str(Path(config[key]).expanduser().resolve())
        if not Path(config['core_path']).is_file():
            raise ValueError('所选核心文件不存在，请先安装核心')
    if Path(config['core_path']).name not in {config['core_id'] + '_libretro' + suffix
            for suffix in ('.so', '_android.so', '.dll', '.dylib')}:
        raise ValueError('核心文件名与所选核心不一致')
    if config['dat_filter'] and not config['dat_path']:
        raise ValueError('启用 DAT 过滤时必须选择 DAT 文件')
    if remote and any(part in {'.', '..'} for part in config['android_directory'].split('/')):
        raise ValueError('掌机启动目录不能包含相对路径')
    if config['system'] == 'MAME' and not config['dat_path']:
        raise ValueError('MAME 请指定与核心和 ROM 集匹配的 DAT 文件')
    return config


def preview(config, progress=lambda *args: None, cancel_check=None):
    system = config['system']
    target = join(config['root'], 'playlists', config['playlist_name'])
    original = read(target)
    document = json.loads(original.decode('utf-8-sig')) if original else {'version': '1.5', 'items': []}
    if not isinstance(document, dict) or not isinstance(document.get('items'), list):
        raise ValueError('现有列表不是有效的 JSON 游戏列表，原文件保持不变')
    items = document['items']
    if any(not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in items):
        raise ValueError('现有列表含无效游戏条目，原文件保持不变')
    existing = {str(item.get('path', '')).replace('\\', '/') for item in items}
    if not mtp.is_mtp(target):
        existing = {str(Path(path.split('#', 1)[0]).resolve()) + ('#' + path.split('#', 1)[1] if '#' in path else '') for path in existing}
    dat = {}
    if config['dat_path']:
        data = read(config['dat_path'])
        if not data:
            raise ValueError('DAT 文件不存在或为空')
        xml = ET.fromstring(data)
        for game in list(xml.findall('game')) + list(xml.findall('machine')):
            if game.get('isbios') != 'yes' and game.get('isdevice') != 'yes':
                dat[game.get('name', '')] = game.findtext('description') or game.get('name')
        if not dat:
            raise ValueError('DAT 中没有游戏条目，需要 Logiqx 或 MAME XML')
    files = []
    def walk(directory, relative=''):
        checkpoint(cancel_check)
        progress(0, 0, '扫描目录：' + (relative or directory))
        for entry in folders(directory):
            path = join(directory, entry['name'])
            rel = posixpath.join(relative, entry['name'])
            if entry['folder']:
                if config['recursive']: walk(path, rel)
            else:
                files.append((rel, path))
    walk(config['directory'])
    extensions = set(config['extensions'].split())
    ignored = set()
    for rel, path in files:
        if PurePosixPath(rel).suffix.lower() == '.m3u' and 'm3u' in extensions:
            data = read(path)
            for line in (data or b'').decode('utf-8-sig').splitlines():
                if line.strip() and not line.lstrip().startswith('#'):
                    ignored.add(posixpath.normpath(posixpath.join(posixpath.dirname(rel), line.strip().replace('\\', '/'))))
    additions, skipped = [], 0
    for index, (rel, path) in enumerate(sorted(files)):
        checkpoint(cancel_check)
        progress(index + 1, len(files), '检查：' + rel)
        if PurePosixPath(rel).suffix.lower().lstrip('.') not in extensions:
            skipped += 1
            continue
        android_path = posixpath.join(config['android_directory'].rstrip('/'), rel) if mtp.is_mtp(target) else path
        if android_path in existing or rel in ignored:
            continue
        stem = PurePosixPath(rel).stem
        if is_system_resource({'path': path, 'label': dat.get(stem, stem)}, system):
            skipped += 1
            continue
        if config['dat_filter'] and stem not in dat:
            skipped += 1
            continue
        additions.append({'path': android_path, 'label': dat.get(stem, stem), 'core_path': 'DETECT',
                          'core_name': 'DETECT', 'crc32': 'DETECT', 'db_name': system + '.lpl'})
        existing.add(android_path)
    # Existing per-game overrides and custom metadata are retained verbatim.
    output = copy.deepcopy(document)
    output['items'].extend(additions)
    output['default_core_path'] = config['core_path']
    output['default_core_name'] = CORE_NAMES[config['core_id']].split('（')[0]
    # Portable content paths still refer to Android, never MTP.
    scan_dat = config['dat_path']
    if scan_dat and mtp.is_mtp(target):
        directory_parts = mtp.parse(config['directory'])[2]
        tail = '/' + '/'.join(directory_parts)
        android = config['android_directory'].rstrip('/')
        scan_dat = posixpath.join(android[:-len(tail)], *mtp.parse(scan_dat)[2]) if directory_parts and android.endswith(tail) and mtp.parse(scan_dat)[:2] == mtp.parse(config['directory'])[:2] else ''
    output.update(scan_dat_file_path=scan_dat, scan_filter_dat_content=config['dat_filter'],
                  scan_content_dir=config['android_directory'] if mtp.is_mtp(target) else config['directory'],
                  scan_file_exts=config['extensions'], scan_search_recursively=config['recursive'],
                  scan_search_archives=False, scan_overwrite_playlist=False)
    metadata_changed = output != document
    return {'config': config, 'target': target, 'expected': mtp.digest(original), 'document': output,
            'added': additions, 'retained': len(items), 'skipped': skipped,
            'can_apply': metadata_changed, 'core_status': '安装状态未知（MTP 无法验证私有目录）' if mtp.is_mtp(target) else '核心文件已存在',
            'note': '保留所有现有条目；不删除失效项。压缩包作为单个游戏入口，不读取包内内容。'
                    + ('DAT 路径仅保存在 RetroArch 助手配置中，RetroArch 端刷新前需重新指定 DAT。' if config['dat_path'] and not scan_dat else '')}


def apply(plan):
    target = plan['target']
    content = (json.dumps(plan['document'], ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if mtp.is_mtp(target):
        backup = mtp.write(target, content, plan['expected'])
    else:
        with file_lock(target):
            before = read(target)
            if mtp.digest(before) != plan['expected']:
                raise RuntimeError('列表已变化，请重新扫描预览')
            backup = target + '.bak-' + uuid.uuid4().hex if before is not None else None
            if backup: atomic_write_bytes(backup, before)
            atomic_write_bytes(target, content, expected_digest=plan['expected'])
    result = {'playlist_path': target, 'added': len(plan['added']), 'retained': plan['retained'], 'backup': backup}
    path = profiles_path()
    try:
        with file_lock(path):
            saved = profiles()
            entries = saved.setdefault(plan['config']['root'], [])
            entries[:] = [entry for entry in entries if (entry['directory'], entry['system']) !=
                         (plan['config']['directory'], plan['config']['system'])]
            entries.append(plan['config'])
            atomic_write_json(path, saved)
    except (OSError, ValueError, RuntimeError) as error:
        result['warning'] = '列表已更新，但扫描配置未保存：' + str(error)
    return result



def hints(root, system, directory, filename=None):
    if system not in SYSTEMS or not isinstance(directory, str) or not directory:
        raise ValueError('请选择主机和目录')
    if mtp.is_mtp(root):
        if mtp.parse(root)[0] != mtp.parse(directory)[0]:
            raise ValueError('目录不属于当前掌机')
    else:
        root = str(Path(root).expanduser().resolve())
    content = read(join(root, 'playlists', playlist_name(system, filename)))
    document = json.loads(content.decode('utf-8-sig')) if content else {}
    result = {'core_path': document.get('default_core_path', ''), 'android_directory': ''}
    if result['core_path'] in ('', 'DETECT'):
        result['core_path'] = next((item.get('core_path') for item in document.get('items', [])
                                   if item.get('core_path') not in (None, '', 'DETECT')), '')
    if mtp.is_mtp(root):
        if mtp.parse(root)[1] != mtp.parse(directory)[1]:
            saved = next((profile for profile in profiles().get(root, [])
                          if profile['directory'] == directory and profile['system'] == system), None)
            result['android_directory'] = saved['android_directory'] if saved else ''
            return result
        parts = mtp.parse(directory)[2]
        paths = [str(item.get('path', '')).replace('\\', '/') for item in document.get('items', [])]
        for size in range(len(parts), 0, -1):
            suffix = '/' + '/'.join(parts[-size:]) + '/'
            candidates = {path.split(suffix, 1)[0] + suffix[:-1] for path in paths
                          if path.startswith(('/storage/', '/sdcard/')) and path.count(suffix) == 1}
            if len(candidates) == 1:
                result['android_directory'] = candidates.pop()
                break
    return result


def core_status(root, core_path):
    """Installation evidence available to this connection, without loading a core."""
    if not isinstance(root, str) or not root or root.startswith('adb://') or not isinstance(core_path, str):
        raise ValueError('请选择本地或文件传输游戏库及有效核心路径')
    remote = mtp.is_mtp(root)
    if remote:
        mtp.parse(root)
    path = core_path.strip()
    if not path or path == 'DETECT':
        return {'state': 'unconfigured', 'message': '待指定核心路径', 'detail': '请在扫描设置中指定核心文件，或按官方下载引导安装。'}
    if remote:
        return {'state': 'unknown', 'message': '安装状态未知',
                'detail': '文件传输无法验证掌机的核心安装状态；请在 RetroArch 中确认。下载和传输不代表安装完成。'}
    if Path(path).expanduser().is_file():
        return {'state': 'available', 'message': '核心文件已找到', 'detail': '已确认本地文件存在，尚未验证核心能否实际加载运行。'}
    return {'state': 'missing', 'message': '核心文件未找到', 'detail': '请更正核心路径，或先安装所选核心。'}
