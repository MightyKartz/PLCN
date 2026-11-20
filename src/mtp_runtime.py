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
    if not path.exists():
        path = app_paths.resource_root() / 'build/libmtp/lib/libmtp.dylib'
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
        'Get_Friendlyname': (C.c_void_p, [C.POINTER(Device)]),
        'Get_Modelname': (C.c_void_p, [C.POINTER(Device)]),
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
    probe = getattr(lib, 'LIBMTP_Probe_Storage', lib.LIBMTP_Get_Storage)
    probe.restype, probe.argtypes = C.c_int, [C.POINTER(Device), C.c_int]
    lib.probe_storage = probe
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
                if library().probe_storage(handle, 0):
                    close()
                    raise RuntimeError('掌机存储暂不可用，请解锁掌机后重试')
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
                if lib.probe_storage(handle, 0):
                    close()
                    raise RuntimeError('无法读取掌机存储，请解锁并允许文件传输')
                device_name = ''
                for getter in (lib.LIBMTP_Get_Friendlyname, lib.LIBMTP_Get_Modelname):
                    name_ptr = getter(handle)
                    if name_ptr:
                        device_name = C.string_at(name_ptr).decode('utf-8', errors='replace').strip()
                        _libc.free(name_ptr)
                    if device_name:
                        break
                storage = handle.contents.storage
                while storage:
                    info = storage.contents
                    found.append({'serial': serial, 'device_name': device_name, 'storage': info.id, 'label': (info.name or b'Android').decode(),
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
    """Stage, verify and atomically swap the named object in place.

    Returns the leftover `.plcn-*.old` URI when cleanup fails after the new
    content was verified, else None."""
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
        old_name = parts[-1] + '.plcn-' + suffix + '.old'
        if old:
            rename(old['id'], old_name)
        try:
            rename(ident, parts[-1])
            if read(value) != content:
                raise RuntimeError('MTP 写回校验失败')
        except RuntimeError:
            # `ident` still holds the stage name or already the target name;
            # removing it clears either the stray stage file or the bad write.
            library().LIBMTP_Delete_Object(handle, ident)
            if old and read(value) is None:
                rename(old['id'], parts[-1])
            raise
        if old:
            if library().LIBMTP_Delete_Object(handle, old['id']):
                # New content is verified and live; only the parked object remains.
                return uri(parse(value)[0], storage, '/'.join(parts[:-1] + [old_name]))


def materialize(value, cache_dir=None):
    content = read(value)
    if content is None:
        raise FileNotFoundError(value)
    root = Path(cache_dir) if cache_dir else app_paths.cache_dir() / 'mtp'
    root.mkdir(parents=True, exist_ok=True)
    target = root / (hashlib.sha256(value.encode()).hexdigest() + '.lpl')
    target.write_bytes(content)
    return str(target)


def read_playlist_summary(path):
    from system_resources import is_system_resource

    name = parse(path)[2][-1]
    base = {'name': name, 'path': path, 'system': name[:-4], 'valid': False,
            'item_count': 0, 'transport': 'mtp'}
    try:
        content = read(path)
        if content is None:
            raise ValueError('设备列表不存在')
        base['revision'] = digest(content)
        data = json.loads(content.decode('utf-8-sig'))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not all(isinstance(item, dict) for item in data['items']):
            raise ValueError('游戏列表 items 必须为对象数组')
        items = data['items']
        system = next((str(item['db_name']).removesuffix('.lpl') for item in items if item.get('db_name')), base['system'])
        base.update(system=system, valid=True, item_count=sum(not is_system_resource(item, system) for item in items))
    except ValueError as error:
        base['error'] = str(error)
    return base


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
            playlists.append(read_playlist_summary(join(playlist_dir, entry['name'])))
    return {'connected': True, 'root_path': value, 'target_path': value, 'transport': 'mtp',
            'status': 'ready' if playlists else 'no_playlists', 'message': '已通过文件传输读取掌机游戏库',
            'device': {'serial': parse(value)[0], 'model': next((device['device_name'] for device in _device_list
                       if device['serial'] == parse(value)[0] and device.get('device_name')), 'Android MTP')},
            'directories': {'playlists': playlist_dir, 'thumbnails': join(value, names.get('thumbnails', 'thumbnails')),
                            'thumbnails_exists': 'thumbnails' in names, 'config': None},
            'playlists': playlists, 'totals': {'playlists': len(playlists), 'items': sum(p['item_count'] for p in playlists)}}


def push_directory(local, target, expected_hashes=None, include_files=None):
    """Upload changed files; returns any verified-but-uncleaned old-object URIs."""
    leftovers = []
    for file in Path(local).rglob('*'):
        if file.is_file() and (include_files is None or str(file.relative_to(local)) in include_files):
            destination = join(target, *file.relative_to(local).parts)
            content = file.read_bytes()
            old = read(destination)
            if old != content:
                expected = expected_hashes[destination] if expected_hashes is not None and destination in expected_hashes else digest(old)
                leftover = write(destination, content, expected)
                if leftover:
                    leftovers.append(leftover)
    return leftovers


Progress = C.CFUNCTYPE(C.c_int, C.c_uint64, C.c_uint64, C.c_void_p)


def stat_file(value):
    with session(value) as (handle, storage, parts):
        return resolve(handle,storage,parts)


def free_bytes(value):
    with session(value) as (handle, storage, _):
        if library().LIBMTP_Get_Storage(handle,0): raise RuntimeError('无法刷新 MTP 可用空间')
        node=handle.contents.storage
        while node:
            if node.contents.id==storage: return node.contents.free
            node=node.contents.next
        raise ValueError('MTP 存储已变化')


def download_file(value,target,cancelled=lambda: None):
    """libmtp writes directly to a private computer file, never a Python ROM buffer."""
    cancelled();errors=[]
    @Progress
    def progress(sent,total,data):
        try: cancelled();return 0
        except Exception as error: errors.append(error);return 1
    with session(value) as (handle, storage, parts):
        entry=resolve(handle,storage,parts)
        if entry is None or entry['folder']: raise ValueError('MTP 源文件不存在：'+value)
        result=library().LIBMTP_Get_File_To_File(handle,entry['id'],str(target).encode(),C.cast(progress,C.c_void_p),None)
        if errors: raise errors[0]
        if result: raise RuntimeError('MTP 文件拉取失败：'+value)
        cancelled()
        if Path(target).stat().st_size!=entry['size']: raise ValueError('MTP 拉取大小不一致：'+value)


def upload_file(value,source,expected,stage,cancelled=lambda: None):
    """New files only: verified staging -> rename -> full readback. Unknown files stay untouched."""
    import chd_io
    cancelled()
    with session(value) as (handle, storage, parts):
        current=chd_io.digest(value,cancelled)
        if current is not None:
            if current!=expected: raise ValueError('MTP 目标已有不同内容：'+value)
            return
        old_stage=resolve(handle,storage,parse(stage)[2])
        if old_stage:
            if chd_io.digest(stage,cancelled)!=expected: raise ValueError('MTP 暂存文件需要人工核对：'+stage)
            ident=old_stage['id']
        else:
            parent=resolve(handle,storage,parts[:-1])
            if parent is None or not parent['folder']: raise ValueError('MTP 目标目录不存在')
            errors=[]
            @Progress
            def progress(sent,total,data):
                try: cancelled();return 0
                except Exception as error: errors.append(error);return 1
            metadata=library().LIBMTP_new_file_t()
            metadata.contents.name=C.cast(_libc.strdup(parse(stage)[2][-1].encode()),C.c_char_p)
            metadata.contents.parent,metadata.contents.storage=parent['id'],storage
            metadata.contents.size,metadata.contents.type=Path(source).stat().st_size,44
            try:
                result=library().LIBMTP_Send_File_From_File(handle,str(source).encode(),metadata,C.cast(progress,C.c_void_p),None)
                if errors: raise errors[0]
                if result: raise RuntimeError('MTP 上传失败；暂存保留：'+stage)
                ident=metadata.contents.id
            finally: library().LIBMTP_destroy_file_t(metadata)
            if chd_io.digest(stage,cancelled)!=expected: raise ValueError('MTP 暂存回读不一致')
        cancelled()
        if resolve(handle,storage,parts) is not None: raise ValueError('MTP 目标在上传期间出现')
        metadata=library().LIBMTP_new_file_t();metadata.contents.id=ident
        try:
            if library().LIBMTP_Set_File_Name(handle,metadata,parts[-1].encode()): raise RuntimeError('MTP 暂存重命名失败')
        finally: library().LIBMTP_destroy_file_t(metadata)
        if chd_io.digest(value,cancelled)!=expected: raise ValueError('MTP 目标回读校验失败')


def remove_file(value,expected,cancelled=lambda: None):
    """Delete one MTP file only when its content still matches the reviewed digest."""
    import chd_io
    with session(value) as (handle, storage, parts):
        if chd_io.digest(value,cancelled)!=expected: raise ValueError('MTP 待移除文件已变化：'+value)
        cancelled();entry=resolve(handle,storage,parts)
        if not entry or entry['folder']: raise ValueError('MTP 移除目标不是文件')
        try:
            if library().LIBMTP_Delete_Object(handle,entry['id']): raise RuntimeError('MTP 移除失败')
        except RuntimeError: raise
        except Exception as error: raise chd_io.RemoveUnverified('删除指令结果未知：'+value) from error
        try:
            still=resolve(handle,storage,parts)
        except Exception as error: raise chd_io.RemoveUnverified('删除已执行但无法核对：'+value) from error
        if still is not None: raise RuntimeError('MTP 移除核对失败')


def rename_object(value, name):
    """Rename any MTP object (file or folder); returns the new URI."""
    with session(value) as (handle, storage, parts):
        entry = resolve(handle, storage, parts)
        if entry is None:
            raise ValueError('文件已移动或不存在')
        if name == parts[-1]:
            return value
        target = parts[:-1] + [name]
        if resolve(handle, storage, target) is not None:
            raise ValueError('已有同名文件')
        lib = library()
        metadata = lib.LIBMTP_new_file_t()
        metadata.contents.id = entry['id']
        try:
            if lib.LIBMTP_Set_File_Name(handle, metadata, name.encode()):
                raise RuntimeError('MTP 重命名失败')
        finally:
            lib.LIBMTP_destroy_file_t(metadata)
        updated = resolve(handle, storage, target)
        if not updated or updated['id'] != entry['id']:
            raise RuntimeError('MTP 重命名未通过核对')
        return uri(parse(value)[0], storage, '/'.join(target))


def delete_object(value):
    """Delete one empty MTP folder object."""
    with session(value) as (handle, storage, parts):
        entry = resolve(handle, storage, parts)
        if entry is None:
            raise ValueError('对象不存在')
        if library().LIBMTP_Delete_Object(handle, entry['id']):
            raise RuntimeError('MTP 删除失败')
        if resolve(handle, storage, parts) is not None:
            raise RuntimeError('MTP 删除核对失败')
