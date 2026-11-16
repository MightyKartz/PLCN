"""Serialized libmtp access. Device URIs contain serial, storage ID and a path."""
import atexit
import ctypes as C
import ctypes.util
from contextlib import contextmanager
import hashlib
import json
import re
from pathlib import Path
import tempfile
import sys
import threading
from urllib.parse import quote, unquote, urlsplit
import uuid

import app_paths


class Entry(C.Structure):
    _fields_ = [('vendor', C.c_char_p), ('vid', C.c_uint16), ('product', C.c_char_p), ('pid', C.c_uint16), ('flags', C.c_uint32)]


class Raw(C.Structure):
    _fields_ = [('entry', Entry), ('bus', C.c_uint32), ('number', C.c_uint8)]


class File(C.Structure):
    pass
File._fields_ = [('id', C.c_uint32), ('parent', C.c_uint32), ('storage', C.c_uint32), ('name', C.c_char_p),
                ('size', C.c_uint64), ('modified', C.c_long), ('type', C.c_int), ('next', C.POINTER(File))]


class Storage(C.Structure):
    pass
Storage._fields_ = [('id', C.c_uint32), ('type', C.c_uint16), ('filesystem', C.c_uint16), ('access', C.c_uint16),
                   ('capacity', C.c_uint64), ('free', C.c_uint64), ('objects', C.c_uint64),
                   ('name', C.c_char_p), ('volume', C.c_char_p), ('next', C.POINTER(Storage)), ('prev', C.POINTER(Storage))]


class Device(C.Structure):
    _fields_ = [('bits', C.c_uint8), ('params', C.c_void_p), ('usb', C.c_void_p), ('storage', C.POINTER(Storage))]


_lock = threading.RLock()
_sessions = {}
_lib = None
_libc = None
_device_list = []


def library():
    global _lib, _libc
    if _lib is not None:
        return _lib
    if sys.platform != 'darwin':
        raise RuntimeError('当前文件传输连接仅支持 macOS')
    _libc = C.CDLL(None)
    _libc.free.argtypes = [C.c_void_p]
    _libc.strdup.argtypes = [C.c_char_p]
    _libc.strdup.restype = C.c_void_p
    path = app_paths.resource_root() / 'libmtp.dylib'
    name = str(path) if path.exists() else ctypes.util.find_library('mtp')
    if not name:
        for candidate in ['/opt/homebrew/lib/libmtp.dylib', '/usr/local/lib/libmtp.dylib']:
            if Path(candidate).exists():
                name = candidate
                break
    if not name:
        raise RuntimeError('缺少 MTP 运行库 libmtp')
    lib = C.CDLL(name)
    signatures = {
        'Get_Errorstack': (C.c_void_p, [C.POINTER(Device)]),
        'Clear_Errorstack': (None, [C.POINTER(Device)]),
        'Init': (None, []), 'Detect_Raw_Devices': (C.c_int, [C.POINTER(C.POINTER(Raw)), C.POINTER(C.c_int)]),
        'Open_Raw_Device_Uncached': (C.POINTER(Device), [C.POINTER(Raw)]),
        'Release_Device': (None, [C.POINTER(Device)]), 'Get_Storage': (C.c_int, [C.POINTER(Device), C.c_int]),
        'Get_Serialnumber': (C.c_void_p, [C.POINTER(Device)]),
        'Get_Files_And_Folders': (C.POINTER(File), [C.POINTER(Device), C.c_uint32, C.c_uint32]),
        'destroy_file_t': (None, [C.POINTER(File)]), 'new_file_t': (C.POINTER(File), []),
        'Get_File_To_File': (C.c_int, [C.POINTER(Device), C.c_uint32, C.c_char_p, C.c_void_p, C.c_void_p]),
        'Send_File_From_File': (C.c_int, [C.POINTER(Device), C.c_char_p, C.POINTER(File), C.c_void_p, C.c_void_p]),
        'Set_File_Name': (C.c_int, [C.POINTER(Device), C.POINTER(File), C.c_char_p]),
        'Create_Folder': (C.c_uint32, [C.POINTER(Device), C.c_char_p, C.c_uint32, C.c_uint32]),
        'Delete_Object': (C.c_int, [C.POINTER(Device), C.c_uint32]),
    }
    for key, (result, args) in signatures.items():
        fn = getattr(lib, 'LIBMTP_' + key)
        fn.restype, fn.argtypes = result, args
    lib.LIBMTP_Init()
    _lib = lib
    return lib




def close():
    with _lock:
        for handle in _sessions.values():
            library().LIBMTP_Release_Device(handle)
        _sessions.clear()
        _device_list.clear()


atexit.register(close)


def uri(serial, storage, path=''):
    return 'mtp://' + quote(serial, safe='') + '/' + f'{storage:08x}' + '/' + quote(path.strip('/'), safe='/')


def parse(value):
    parsed = urlsplit(value)
    parts = unquote(parsed.path).strip('/').split('/')
    if parsed.scheme != 'mtp' or not parsed.netloc or not re.fullmatch(r'[0-9a-fA-F]{8}', parts[0]) or parsed.query or parsed.fragment or any(p in {'', '.', '..'} for p in parts[1:]):
        raise ValueError('MTP 路径无效')
    return unquote(parsed.netloc), int(parts[0], 16), parts[1:]


def is_mtp(value):
    return str(value or '').startswith('mtp://')


def join(root, *parts):
    serial, storage, path = parse(root)
    return uri(serial, storage, '/'.join(path + list(parts)))


def devices():
    with _lock:
        if _sessions:
            for handle in list(_sessions.values()):
                if library().LIBMTP_Get_Storage(handle, 0):
                    close()
                    break
            else:
                return list(_device_list)
        lib = library()
        raw, count = C.POINTER(Raw)(), C.c_int()
        result = lib.LIBMTP_Detect_Raw_Devices(C.byref(raw), C.byref(count))
        if result == 5:  # LIBMTP_ERROR_NO_DEVICE_ATTACHED
            return []
        if result:
            raise RuntimeError('MTP 设备枚举失败')
        found = []
        try:
            for index in range(count.value):
                handle = lib.LIBMTP_Open_Raw_Device_Uncached(C.byref(raw[index]))
                if not handle:
                    raise RuntimeError('无法打开 MTP 设备，请解锁掌机并关闭其它文件传输程序')
                serial_ptr = lib.LIBMTP_Get_Serialnumber(handle)
                serial = C.string_at(serial_ptr).decode() if serial_ptr else f'{raw[index].bus}-{raw[index].number}'
                if serial_ptr:
                    _libc.free(serial_ptr)
                if serial in _sessions:
                    lib.LIBMTP_Release_Device(handle)
                    handle = _sessions[serial]
                else:
                    _sessions[serial] = handle
                if lib.LIBMTP_Get_Storage(handle, 0):
                    close()
                    raise RuntimeError('无法读取掌机存储，请解锁并允许文件传输')
                storage = handle.contents.storage
                while storage:
                    info = storage.contents
                    found.append({'serial': serial, 'storage': info.id, 'label': (info.name or b'Android').decode(),
                                  'path': uri(serial, info.id), 'transport': 'mtp'})
                    storage = info.next
        finally:
            _libc.free(raw)
        _device_list[:] = found
        return found


@contextmanager
def session(value):
    with _lock:
        serial, storage, parts = parse(value)
        if serial not in _sessions:
            devices()
        if serial not in _sessions:
            raise RuntimeError('MTP 掌机未连接')
        yield _sessions[serial], storage, parts


def listing(value):
    with session(value) as (handle, storage, parts):
        parent = resolve(handle, storage, parts)
        if parent is None:
            return []
        return children(handle, storage, parent['id'])


def children(handle, storage, parent):
    lib = library()
    lib.LIBMTP_Clear_Errorstack(handle)
    node = lib.LIBMTP_Get_Files_And_Folders(handle, storage, parent or 0xffffffff)
    if not node and lib.LIBMTP_Get_Errorstack(handle):
        raise RuntimeError('无法读取 MTP 目录，请确认掌机已解锁并选择文件传输')
    result = []
    while node:
        file = node.contents
        following = C.cast(file.next, C.c_void_p).value
        result.append({'id': file.id, 'name': file.name.decode(), 'size': file.size, 'folder': file.type == 0})
        lib.LIBMTP_destroy_file_t(node)
        node = C.cast(following, C.POINTER(File))
    return result


def resolve(handle, storage, parts, create=False):
    current = {'id': 0, 'folder': True}
    for name in parts:
        entry = next((x for x in children(handle, storage, current['id']) if x['name'] == name), None)
        if entry is None and create:
            ident = library().LIBMTP_Create_Folder(handle, name.encode(), current['id'], storage)
            if not ident:
                raise RuntimeError('无法创建 MTP 目录：' + name)
            entry = {'id': ident, 'folder': True}
        if entry is None:
            return None
        current = entry
    return current


def read(value):
    with session(value) as (handle, storage, parts):
        entry = resolve(handle, storage, parts)
        if entry is None:
            return None
        if entry['folder']:
            raise ValueError('目标是 MTP 目录')
        with tempfile.TemporaryDirectory(prefix='plcn-mtp-read-') as temporary:
            file = Path(temporary) / 'content'
            if library().LIBMTP_Get_File_To_File(handle, entry['id'], str(file).encode(), None, None):
                raise RuntimeError('MTP 文件读取失败')
            return file.read_bytes()


def upload(handle, storage, parent, name, content):
    lib = library()
    metadata = lib.LIBMTP_new_file_t()
    metadata.contents.name = C.cast(_libc.strdup(name.encode()), C.c_char_p)
    metadata.contents.parent, metadata.contents.storage = parent, storage
    metadata.contents.size, metadata.contents.type = len(content), 44  # unknown: device infers content type
    try:
        with tempfile.TemporaryDirectory(prefix='plcn-mtp-write-') as temporary:
            file = Path(temporary) / 'content'
            file.write_bytes(content)
            if lib.LIBMTP_Send_File_From_File(handle, str(file).encode(), metadata, None, None):
                raise RuntimeError('MTP 文件上传失败')
        return metadata.contents.id
    finally:
        lib.LIBMTP_destroy_file_t(metadata)


def digest(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None


def write(value, content, expected, suffix=None):
    """Verify staging and backup before replacing the named object; return backup URI."""
    with session(value) as (handle, storage, parts):
        before = read(value)
        if digest(before) != expected:
            raise RuntimeError('设备文件已变化，请重新预览')
        parent = resolve(handle, storage, parts[:-1], create=True)['id']
        suffix = suffix or uuid.uuid4().hex
        stage_name = parts[-1] + '.plcn-' + suffix + '.tmp'
        ident = upload(handle, storage, parent, stage_name, content)
        stage_uri = uri(parse(value)[0], storage, '/'.join(parts[:-1] + [stage_name]))
        if read(stage_uri) != content:
            raise RuntimeError('MTP 暂存校验失败，原文件未替换')
        backup = None
        old = resolve(handle, storage, parts)
        def rename(ident, name):
            metadata = library().LIBMTP_new_file_t()
            metadata.contents.id = ident
            try:
                if library().LIBMTP_Set_File_Name(handle, metadata, name.encode()):
                    raise RuntimeError('MTP 重命名失败：' + name)
            finally:
                library().LIBMTP_destroy_file_t(metadata)
        if digest(read(value)) != expected:
            raise RuntimeError('设备文件在传输期间发生变化')
        if old:
            backup = value + '.bak-' + suffix
            rename(old['id'], parts[-1] + '.bak-' + suffix)
            if read(backup) != before:
                rename(old['id'], parts[-1])
                raise RuntimeError('MTP 原文件备份校验失败，已恢复原名称')
        try:
            rename(ident, parts[-1])
            if read(value) != content:
                raise RuntimeError('MTP 写回校验失败；备份：' + str(backup))
        except RuntimeError:
            if old and read(value) is None:
                rename(old['id'], parts[-1])
            raise
        return backup


def materialize(value, cache_dir=None):
    content = read(value)
    if content is None:
        raise FileNotFoundError(value)
    root = Path(cache_dir) if cache_dir else app_paths.cache_dir() / 'mtp'
    root.mkdir(parents=True, exist_ok=True)
    target = root / (hashlib.sha256(value.encode()).hexdigest() + '.lpl')
    target.write_bytes(content)
    return str(target)


def scan(value):
    entries = listing(value)
    names = {entry['name'].lower(): entry['name'] for entry in entries if entry['folder']}
    if 'retroarch' in names:
        value = join(value, names['retroarch'])
        entries = listing(value)
        names = {entry['name'].lower(): entry['name'] for entry in entries if entry['folder']}
    playlist_dir = value if any(entry['name'].lower().endswith('.lpl') for entry in entries) else join(value, names.get('playlists', 'playlists'))
    playlists = []
    for entry in listing(playlist_dir):
        if not entry['folder'] and entry['name'].lower().endswith('.lpl'):
            path = join(playlist_dir, entry['name'])
            try:
                data = json.loads(read(path).decode('utf-8-sig'))
                if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not all(isinstance(item, dict) for item in data['items']):
                    raise ValueError('游戏列表 items 必须为对象数组')
                items = data['items']
                system = next((str(item['db_name']).removesuffix('.lpl') for item in items if item.get('db_name')), entry['name'][:-4])
                playlists.append({'name': entry['name'], 'path': path, 'system': system, 'valid': True, 'item_count': len(items), 'transport': 'mtp'})
            except (ValueError, UnicodeError) as error:
                playlists.append({'name': entry['name'], 'path': path, 'system': entry['name'][:-4], 'valid': False, 'item_count': 0, 'error': str(error), 'transport': 'mtp'})
    return {'connected': True, 'root_path': value, 'target_path': value, 'transport': 'mtp',
            'status': 'ready' if playlists else 'no_playlists', 'message': '已通过文件传输读取掌机游戏库',
            'device': {'serial': parse(value)[0], 'model': 'Android MTP'},
            'directories': {'playlists': playlist_dir, 'thumbnails': join(value, names.get('thumbnails', 'thumbnails')),
                            'thumbnails_exists': 'thumbnails' in names, 'config': None},
            'playlists': playlists, 'totals': {'playlists': len(playlists), 'items': sum(p['item_count'] for p in playlists)}}


def push_directory(local, target, expected_hashes=None, include_files=None):
    for file in Path(local).rglob('*'):
        if file.is_file() and (include_files is None or str(file.relative_to(local)) in include_files):
            destination = join(target, *file.relative_to(local).parts)
            content = file.read_bytes()
            old = read(destination)
            if old != content:
                expected = expected_hashes[destination] if expected_hashes is not None and destination in expected_hashes else digest(old)
                write(destination, content, expected)


def remove_verified(value, expected):
    """Remove only an unchanged file created by a recorded, explicitly restored operation."""
    with session(value) as (handle, storage, parts):
        if digest(read(value)) != expected:
            raise ValueError('MTP 新建文件已变化，拒绝移除')
        entry = resolve(handle, storage, parts)
        if entry is None or entry['folder']:
            raise ValueError('MTP 恢复目标不是文件')
        if library().LIBMTP_Delete_Object(handle, entry['id']):
            raise RuntimeError('MTP 恢复时移除新建文件失败')
        if read(value) is not None:
            raise RuntimeError('MTP 移除后的核对失败')
