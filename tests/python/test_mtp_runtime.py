"""MTP boundaries and reviewed writes, without claiming a real USB device."""
from contextlib import contextmanager
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import mtp_runtime as mtp

runtime_devices = mtp.devices


def test_uri_round_trip_and_traversal():
    root = mtp.uri('device #1', 65537, 'RetroArch')
    target = mtp.join(root, '中文 # %', 'A?.png')
    assert mtp.parse(target) == ('device #1', 65537, ['RetroArch', '中文 # %', 'A?.png'])
    for invalid in ['mtp://d/xyz/a', 'mtp://d/00010001/../a', 'mtp://d/00010001/%2e%2e/a', 'mtp://d/00010001/a#x']:
        with pytest.raises(ValueError):
            mtp.parse(invalid)


def test_read_only_scan_and_browser(monkeypatch):
    import playlist_browser
    import playlist_artwork
    root = mtp.uri('device', 65537)
    library = mtp.join(root, 'RetroArch')
    playlists = mtp.join(library, 'playlists')
    thumbnails = mtp.join(library, 'thumbnails')
    playlist = mtp.join(playlists, 'NES.lpl')
    content = json.dumps({'items': [{'path':'/Roms/A.zip', 'label':'中文 #', 'db_name':'NES.lpl'}]}).encode()
    def listing(path):
        names = ['RetroArch'] if path == root else ['playlists', 'thumbnails'] if path == library else ['NES.lpl', 'bad.lpl'] if path == playlists else ['A.png'] if path == mtp.join(thumbnails, 'NES', 'Named_Boxarts') else []
        return [{'name': name, 'folder': not name.endswith(('.lpl', '.png'))} for name in names]
    monkeypatch.setattr(mtp, 'listing', listing)
    monkeypatch.setattr(mtp, 'read', lambda path: content if path == playlist else b'[]')
    monkeypatch.setattr(mtp, 'write', lambda *a, **k: pytest.fail('read-only flow wrote to device'))
    scan = mtp.scan(root)
    assert scan['totals'] == {'playlists':2, 'items':1}
    assert scan['playlists'][1]['valid'] is False
    result = playlist_browser.read_playlist(playlist, 'NES', thumbnails)
    assert result['items'][0]['image_path'] == mtp.join(thumbnails, 'NES', 'Named_Boxarts', 'A.png')
    assert playlist_artwork.find_existing_boxart(thumbnails, 'NES', 'A')[0]


@pytest.fixture
def device_files(monkeypatch):
    root = mtp.uri('device', 65537, 'RetroArch')
    files = {}
    ids = {}
    @contextmanager
    def session(value):
        serial, storage, parts = mtp.parse(value)
        yield None, storage, parts
    def upload(handle, storage, parent, name, content):
        ident = len(ids) + 1
        path = mtp.join(root, name)
        ids[ident] = path
        files[path] = content
        return ident
    def resolve(handle, storage, parts, create=False):
        if parts == ['RetroArch']:
            return {'id':0, 'folder':True}
        path = mtp.uri('device', storage, '/'.join(parts))
        return {'id':next(i for i, p in ids.items() if p == path), 'folder':False,'size':len(files[path])} if path in files else None
    def rename(handle, metadata, name):
        ident = metadata.contents.id
        old = ids[ident]
        new = mtp.join(root, name.decode())
        files[new] = files.pop(old)
        ids[ident] = new
        return 0
    def delete(handle, ident):
        files.pop(ids.pop(ident), None)
        return 0
    lib = SimpleNamespace(LIBMTP_new_file_t=lambda: ctypes.pointer(mtp.File()), LIBMTP_destroy_file_t=lambda p: None,
                          LIBMTP_Set_File_Name=rename, LIBMTP_Delete_Object=delete)
    monkeypatch.setattr(mtp, 'session', session)
    monkeypatch.setattr(mtp, 'upload', upload)
    monkeypatch.setattr(mtp, 'resolve', resolve)
    monkeypatch.setattr(mtp, 'read', lambda path: files.get(path))
    monkeypatch.setattr(mtp, 'library', lambda: lib)
    return root, files, upload, lib


def test_write_replaces_in_place_and_rejects_stale_preview(device_files):
    root, files, upload, lib = device_files
    target = mtp.join(root, '游戏.lpl')
    upload(None, 65537, 0, '游戏.lpl', b'original')
    before = dict(files)
    with pytest.raises(RuntimeError, match='重新预览'):
        mtp.write(target, b'new', mtp.digest(b'outdated'))
    assert files == before
    mtp.write(target, b'new', mtp.digest(b'original'), suffix='review')
    assert files[target] == b'new'
    assert not any('.bak' in path or '.plcn-' in path for path in files)


def test_failed_publish_restores_original_name(device_files):
    root, files, upload, lib = device_files
    target = mtp.join(root, 'games.lpl')
    upload(None, 65537, 0, 'games.lpl', b'original')
    rename = lib.LIBMTP_Set_File_Name
    lib.LIBMTP_Set_File_Name = lambda h, p, n: 1 if p.contents.id == 2 else rename(h, p, n)
    with pytest.raises(RuntimeError, match='重命名失败'):
        mtp.write(target, b'new', mtp.digest(b'original'))
    assert files[target] == b'original'


def test_push_directory_collects_verified_write_leftovers(device_files, tmp_path, monkeypatch):
    root, files, upload, lib = device_files
    target_dir = mtp.join(root, 'thumbs')
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'a.png').write_bytes(b'new a')
    (local / 'b.png').write_bytes(b'new b')
    upload(None, 65537, 0, 'thumbs', b'')
    def flaky(value, content, expected, suffix=None):
        files[value] = content
        return value + '.plcn-stuck.old' if value.endswith('a.png') else None
    monkeypatch.setattr(mtp, 'write', flaky)
    leftovers = mtp.push_directory(str(local), target_dir)
    assert leftovers == [target_dir + '/a.png.plcn-stuck.old']
    assert files[target_dir + '/a.png'] == b'new a' and files[target_dir + '/b.png'] == b'new b'


def test_cleanup_failure_reports_leftover_after_verified_write(device_files):
    root, files, upload, lib = device_files
    target = mtp.join(root, 'games.lpl')
    upload(None, 65537, 0, 'games.lpl', b'original')
    lib.LIBMTP_Delete_Object = lambda handle, ident: 1
    leftover = mtp.write(target, b'new', mtp.digest(b'original'))
    assert files[target] == b'new'
    assert leftover and '.plcn-' in leftover and leftover.endswith('.old')
    assert files[leftover] == b'original'


def test_reviewed_transport_uses_snapshot_digest_and_remote_results(tmp_path, monkeypatch):
    import playlist_transport
    root = mtp.uri('device', 65537, 'RetroArch')
    target = mtp.join(root, 'playlists', 'NES.lpl')
    images = mtp.join(root, 'thumbnails')
    content = b'{"items": []}'
    monkeypatch.setattr(mtp, 'read', lambda path: content)
    writes, pushes = [], []
    monkeypatch.setattr(mtp, 'write', lambda *args: writes.append(args))
    monkeypatch.setattr(mtp, 'push_directory', lambda *args, **kwargs: pushes.append((args, kwargs)) or [])
    def apply(path, changes, images, **kwargs):
        Path(path).write_bytes(b'{"items": [], "version": "1"}')
        return {'download_summary': {'details':[{'path':str(Path(images)/'NES/Named_Boxarts/A.png'), 'type':'Named_Boxarts', 'status':'success'}]}, 'apply':{'applied':[0]}}
    monkeypatch.setattr(playlist_transport.playlist_service, 'apply_changes', apply)
    result = playlist_transport.apply_playlist(target, [], images, options={}, progress=lambda *a: None, cancel_check=lambda:False)
    assert writes[0][2] == mtp.digest(content)
    assert result['transport'] == 'mtp'
    assert result['download_summary']['details'][0]['cover_path'] == mtp.join(images, 'NES', 'Named_Boxarts', 'A.png')
    writes.clear()
    playlist_transport.apply_playlist(target, [], images, options={'write_names':False}, progress=lambda *a: None, cancel_check=lambda:False)
    assert not writes
    assert len(pushes) == 2


def test_discovery_detects_mtp_without_adb_and_skips_local_history(monkeypatch):
    import library_sources
    root = mtp.uri('device', 65537)
    monkeypatch.setattr(mtp, 'devices', lambda: [{'path':root, 'serial':'device', 'label':'内部存储', 'transport':'mtp'}])
    monkeypatch.setattr(mtp, 'scan', lambda path: {'playlists':[{}], 'root_path':mtp.join(root, 'RetroArch')})
    monkeypatch.setattr(library_sources.scanner, 'list_adb_devices', lambda **k: [])
    monkeypatch.setattr(library_sources, 'usb_android_devices', lambda: pytest.fail('ready MTP treated as USB-only'))
    monkeypatch.setattr(library_sources, 'read_history', lambda *a: [{'path':'/Users/test/Desktop/lpl'}])
    result = library_sources.discover()
    assert result['sources'][0]['status'] == 'ready'
    assert result['sources'][0]['transport'] == 'mtp'
    assert result['recent'] == []


def test_single_image_preview_and_confirm_never_write_playlist(tmp_path, monkeypatch):
    import base64
    import io
    from PIL import Image
    import single_artwork as art
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'runtime'))
    root = mtp.uri('device', 65537, 'RetroArch')
    playlist = mtp.join(root, 'playlists', 'NES.lpl')
    files = {playlist: json.dumps({'items':[{'label':'中文 #', 'path':'/roms/A.nes'}]}).encode()}
    image = io.BytesIO()
    Image.new('RGB', (12, 16), 'red').save(image, format='PNG')
    monkeypatch.setattr(mtp, 'read', lambda path: files.get(path))
    writes = []
    def write(path, content, expected, suffix=None):
        assert path != playlist
        assert mtp.digest(files.get(path)) == expected
        files[path] = content
        writes.append(path)
    monkeypatch.setattr(mtp, 'write', write)
    payload = {'playlist_path':playlist, 'system':'NES', 'thumbnails':mtp.join(root, 'thumbnails'),
               'index':0, 'label':'中文 #', 'rom_path':'/roms/A.nes', 'kind':'Named_Boxarts',
               'upload':base64.b64encode(image.getvalue()).decode(), 'filename':'local.png'}
    prepared = art.preview(payload)
    assert not writes
    assert '%23' in prepared['target']
    original = files[playlist]
    result = art.apply(prepared['token'])
    assert art.valid_png(files[result['target']])
    assert art.apply(prepared['token']) == result
    assert writes == [prepared['target']]
    assert files[playlist] == original


def test_mtp_image_retry_reuses_existing_images_and_does_not_push_playlist(tmp_path, monkeypatch):
    import io
    from PIL import Image
    from types import SimpleNamespace
    import playlist_transport
    from thumbnail_downloader import ThumbnailDownloader
    from artwork_resolver import THUMBNAIL_TYPES
    buffer = io.BytesIO(); Image.new('RGB', (12, 16), 'green').save(buffer, format='PNG'); png = buffer.getvalue()
    root = mtp.uri('device', 65537, 'RetroArch')
    path = mtp.join(root, 'playlists', 'Saturn.lpl'); images = mtp.join(root, 'thumbnails')
    item = {'path':'/Roms/Game.cue', 'label':'游戏', 'db_name':'Saturn.lpl'}
    playlist = json.dumps({'items':[item]}, ensure_ascii=False).encode()
    boxart = mtp.join(images, 'Saturn', 'Named_Boxarts', '游戏.png')
    files = {path:playlist, boxart:png}
    monkeypatch.setattr(mtp, 'read', lambda value: files.get(value))
    writes = []
    def write(value, content, expected):
        assert mtp.digest(files.get(value)) == expected
        writes.append(value); files[value] = content
    monkeypatch.setattr(mtp, 'write', write)
    requests = []
    def response(session, url, **kwargs):
        requests.append(url); return SimpleNamespace(status_code=200, content=png)
    monkeypatch.setattr(__import__('requests').Session, 'get', response)
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path/'runtime'))
    changes=[{'artwork_source_confirmed':True,'index':0,'path':item['path'],'original_item_label':'游戏','original_item_snapshot':item.copy(),
              'original_label':'Game','new_label':'游戏','system':'Saturn','thumbnail_source':'Game (Japan)'}]
    result = playlist_transport.apply_playlist(path, changes, images, options={'write_names':True}, progress=lambda *args:None, cancel_check=lambda:False)
    assert files[path] == playlist
    assert path not in writes and boxart not in writes
    assert len(writes) == 2 and len(requests) == 2
    assert all('Named_Boxarts' not in url for url in requests)
    assert result['download_summary']['total'] == {'success':2,'failed':0,'skipped':1}
    from artwork_identity import remembered
    assert len(remembered({'system':'Saturn','playlist_path':path,'rom_path':item['path'],'label':'游戏'})['sources']) == 3


def test_stale_playlist_cannot_publish_prefetched_alias_images(tmp_path, monkeypatch):
    import io
    from PIL import Image
    import playlist_transport
    buffer=io.BytesIO(); Image.new('RGB',(12,16),'red').save(buffer,format='PNG'); png=buffer.getvalue()
    root=mtp.uri('device',65537,'RetroArch'); path=mtp.join(root,'playlists','NES.lpl'); images=mtp.join(root,'thumbnails')
    current={'path':'/Roms/Game.nes','label':'Changed externally','db_name':'NES.lpl'}
    content=json.dumps({'items':[current]}).encode()
    def read(value):
        if value==path:return content
        if value.endswith('/Game.png'):return png
        return None
    monkeypatch.setattr(mtp,'read',read)
    monkeypatch.setattr(mtp,'write',lambda *a,**k:pytest.fail('Stale row published a file'))
    row={'index':0,'path':current['path'],'original_item_label':'Old label','original_item_snapshot':{**current,'label':'Old label'},
         'new_label':'新名称','thumbnail_source':'Game','system':'NES'}
    result=playlist_transport.apply_playlist(path,[row],images,options={'write_names':False},progress=lambda *a:None,cancel_check=lambda:False)
    assert not result['apply']['applied']
    assert result['apply']['skipped'][0]['reason']=='stale_proposal'


def test_service_releases_mtp_before_retiring_http_instance(monkeypatch):
    import server
    events = []
    class FakeServer:
        server_address = ('127.0.0.1', 7777)
        def __enter__(self):return self
        def __exit__(self, *args):events.append('http_closed')
        def serve_forever(self):events.append('served')
    monkeypatch.setattr(server, 'LocalHTTPServer', lambda *args:FakeServer())
    monkeypatch.setattr(mtp, 'close', lambda:events.append('mtp_closed'))
    import app_runtime
    instance = SimpleNamespace(acquire=lambda: True,
                               publish=lambda *args: events.append('published'),
                               close=lambda: events.append('unlocked'))
    monkeypatch.setattr(app_runtime, 'InstanceLock', lambda directory: instance)
    server.run_server()
    assert events == ['published', 'served', 'mtp_closed', 'http_closed', 'unlocked']


def test_import_on_windows_does_not_load_native_mtp_or_libc(monkeypatch):
    import runpy
    import sys
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'CDLL', lambda *a, **kw: pytest.fail('Import must not load a native library'))
    namespace = runpy.run_path(str(Path(mtp.__file__)))
    with pytest.raises(RuntimeError, match='仅支持 macOS'):
        namespace['library']()


def test_streamed_image_upload_uses_private_stage_and_full_readback(device_files,tmp_path,monkeypatch):
    import chd_cue
    import chd_io
    root,files,old_upload,lib=device_files
    buffers=[]
    def strdup(value):
        buffer=ctypes.create_string_buffer(value);buffers.append(buffer);return ctypes.addressof(buffer)
    monkeypatch.setattr(mtp,'_libc',SimpleNamespace(strdup=strdup))
    def send(handle,source,metadata,callback,data):
        value=Path(source.decode()).read_bytes();name=metadata.contents.name.decode()
        progress=ctypes.cast(callback,mtp.Progress)
        if progress(len(value),len(value),None):return 1
        ident=old_upload(handle,65537,0,name,value);metadata.contents.id=ident;return 0
    def receive(handle,ident,target,callback,data):
        # fixture object IDs are assigned in insertion order.
        value=list(files.values())[ident-1] if len(files)==1 else next(value for key,value in files.items() if key.endswith(('.tmp','.chd')))
        if ctypes.cast(callback,mtp.Progress)(len(value),len(value),None):return 1
        Path(target.decode()).write_bytes(value);return 0
    lib.LIBMTP_Send_File_From_File=send;lib.LIBMTP_Get_File_To_File=receive
    # Runtime stat_file resolves the same fake object tree used by staged metadata writes.
    source=tmp_path/'image.chd';source.write_bytes(b'large image fixture'*10000)
    target=mtp.join(root,'image.chd');stage=target+'.tmp';expected=chd_cue.fingerprint(source)
    mtp.upload_file(target,source,expected,stage)
    assert files[target]==source.read_bytes() and stage not in files
    mtp.upload_file(target,source,expected,stage)  # Already verified: no overwrite or new object.
    assert list(files)==[target]


def test_download_progress_callback_propagates_cancellation(device_files,tmp_path):
    from task_control import TaskCancelled
    root,files,upload,lib=device_files;value=mtp.join(root,'image.chd');upload(None,65537,0,'image.chd',b'image')
    def receive(handle,ident,target,callback,data):
        return ctypes.cast(callback,mtp.Progress)(1,5,None)
    lib.LIBMTP_Get_File_To_File=receive
    calls=[0]
    def cancelled():
        calls[0]+=1
        if calls[0]>1:raise TaskCancelled('cancel native transfer')
    with pytest.raises(TaskCancelled,match='cancel native'):mtp.download_file(value,tmp_path/'partial',cancelled)
    assert files[value]==b'image'


def test_mtp_replaces_only_reviewed_old_artwork_hashes_and_keeps_playlist(tmp_path, monkeypatch):
    import hashlib
    import io
    from PIL import Image
    import playlist_transport
    from artwork_resolver import THUMBNAIL_TYPES
    import app_paths
    def picture(color):
        data = io.BytesIO();Image.new('RGB', (2, 2), color).save(data, format='PNG');return data.getvalue()
    old, new = picture('red'), picture('green')
    digest = hashlib.sha256(old).hexdigest()
    root = mtp.uri('device', 65537, 'RetroArch');path = mtp.join(root, 'playlists', 'MAME.lpl');images = mtp.join(root, 'thumbnails')
    item = {'path': '/roms/游戏.zip', 'label': '游戏'}
    playlist = json.dumps({'items': [item]}).encode()
    files = {path: playlist, **{mtp.join(images, 'MAME', kind, '游戏.png'): old for kind in THUMBNAIL_TYPES}}
    monkeypatch.setattr(mtp, 'read', lambda value: files.get(value))
    writes = []
    def write(value, content, expected):
        assert expected == mtp.digest(files.get(value))
        files[value] = content;writes.append(value)
    monkeypatch.setattr(mtp, 'write', write)
    monkeypatch.setattr(__import__('requests').Session, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=new))
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'runtime'))
    row = {'index': 0, 'path': item['path'], 'original_item_label': '游戏', 'original_item_snapshot': item,
           'original_label': '游戏', 'new_label': '游戏', 'system': 'MAME', 'thumbnail_source': 'Correct Game',
           'replace_artwork_hashes': {kind: digest for kind in THUMBNAIL_TYPES}}
    result = playlist_transport.apply_playlist(path, [row], images, options={'write_names': False}, progress=lambda *a: None, cancel_check=lambda: False)
    assert len(writes) == 3 and path not in writes
    assert files[path] == playlist
    assert all(files[mtp.join(images, 'MAME', kind, '游戏.png')] == new for kind in THUMBNAIL_TYPES)
    assert result['download_summary']['total']['success'] == 3
    assert not (app_paths.user_data_dir() / 'artwork-backups').exists()


def test_locked_cached_session_is_released_and_unlock_can_open_a_new_session(monkeypatch):
    locked = [True]
    released = []
    name = ctypes.create_string_buffer(b'Retroid Pocket Nova')
    storage = mtp.Storage(id=65537, name=b'Internal')
    device = mtp.Device(storage=ctypes.pointer(storage))
    handle = ctypes.pointer(device)
    raw_devices = (mtp.Raw * 1)()
    raw_devices[0].bus, raw_devices[0].number = 1, 2
    def detect(raw, count):
        ctypes.cast(raw, ctypes.POINTER(ctypes.POINTER(mtp.Raw)))[0] = ctypes.cast(raw_devices, ctypes.POINTER(mtp.Raw))
        count._obj.value = 1
        return 0
    lib = SimpleNamespace(probe_storage=lambda *args: -1 if locked[0] else 0,
                          LIBMTP_Release_Device=lambda value: released.append(value),
                          LIBMTP_Detect_Raw_Devices=detect,
                          LIBMTP_Open_Raw_Device_Uncached=lambda raw: handle,
                          LIBMTP_Get_Friendlyname=lambda handle: ctypes.addressof(name),
                          LIBMTP_Get_Modelname=lambda handle: None,
                          LIBMTP_Get_Serialnumber=lambda value: None)
    sessions = {'1-2': handle}
    monkeypatch.setattr(mtp, '_sessions', sessions)
    monkeypatch.setattr(mtp, '_device_list', [{'serial': '1-2'}])
    monkeypatch.setattr(mtp, '_libc', SimpleNamespace(free=lambda value: None))
    monkeypatch.setattr(mtp, 'library', lambda: lib)
    with pytest.raises(RuntimeError, match='解锁'):
        runtime_devices()
    assert sessions == {} and len(released) == 1
    locked[0] = False
    found = runtime_devices()
    assert found[0]['path'] == 'mtp://1-2/00010001/'
    assert found[0]['label'] == 'Internal'
    assert found[0]['device_name'] == 'Retroid Pocket Nova'


def _stub_chd_digest(monkeypatch, files):
    import chd_io
    monkeypatch.setattr(chd_io, 'digest', lambda path, *a, **k: mtp.digest(files[path]) if path in files else None)
    return chd_io


def test_remove_nonzero_status_but_object_gone_counts_as_removed(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'gone.cue'); upload(None, 65537, 0, 'gone.cue', b'cue bytes')
    lib.LIBMTP_Delete_Object = lambda handle, ident: (files.pop(target, None), 1)[1]
    mtp.remove_file(target, chd_io.digest(target))
    assert target not in files


def test_remove_nonzero_status_but_object_present_stays_retryable(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'stays.cue'); upload(None, 65537, 0, 'stays.cue', b'cue bytes')
    lib.LIBMTP_Delete_Object = lambda handle, ident: 1
    with pytest.raises(RuntimeError, match='移除失败'):
        mtp.remove_file(target, chd_io.digest(target))
    assert target in files


def test_remove_delete_command_transport_error_is_unverified(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'lost.cue'); upload(None, 65537, 0, 'lost.cue', b'cue bytes')
    lib.LIBMTP_Delete_Object = lambda handle, ident: (_ for _ in ()).throw(OSError('link dead'))
    with pytest.raises(chd_io.RemoveUnverified, match='结果未知'):
        mtp.remove_file(target, chd_io.digest(target))


def test_remove_presence_check_failure_is_unverified(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'grey.cue'); upload(None, 65537, 0, 'grey.cue', b'cue bytes')
    real = mtp.resolve; calls = [0]
    def flaky(handle, storage, parts, create=False):
        calls[0] += 1
        if calls[0] == 2: raise OSError('link dead')
        return real(handle, storage, parts, create)
    monkeypatch.setattr(mtp, 'resolve', flaky)
    with pytest.raises(chd_io.RemoveUnverified, match='无法核对|无法确认'):
        mtp.remove_file(target, chd_io.digest(target))


def test_remove_flags_same_named_replacement_object_as_unverified(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'restored.cue'); upload(None, 65537, 0, 'restored.cue', b'cue bytes')
    deleted_ids = []
    def flaky_delete(handle, ident):
        deleted_ids.append(ident)
        files.pop(target, None)
        files[target] = b'cue bytes'   # A same-named object appears before read-back.
        return 1
    lib.LIBMTP_Delete_Object = flaky_delete
    real_resolve = mtp.resolve; calls = [0]
    def resolve(handle, storage, parts, create=False):
        calls[0] += 1
        entry = real_resolve(handle, storage, parts, create)
        if calls[0] == 3 and entry: entry = dict(entry, id=entry['id'] + 5496)
        return entry
    monkeypatch.setattr(mtp, 'resolve', resolve)
    with pytest.raises(chd_io.RemoveUnverified, match='新对象'):
        mtp.remove_file(target, chd_io.digest(target))
    assert files[target] == b'cue bytes'
    assert len(deleted_ids) == 1


def test_remove_rejects_when_object_id_changed(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'swapped.cue'); upload(None, 65537, 0, 'swapped.cue', b'cue bytes')
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    with pytest.raises(chd_io.RemoveUnverified, match='对象已变化'):
        mtp.remove_file(target, chd_io.digest(target), expected_id=approved + 77)
    assert not deleted_ids and files[target] == b'cue bytes'


def test_remove_proceeds_when_object_id_matches(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'same.cue'); upload(None, 65537, 0, 'same.cue', b'cue bytes')
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    mtp.remove_file(target, chd_io.digest(target), expected_id=approved)
    assert target not in files


def test_remove_identity_change_wins_over_digest_mismatch(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'swapped2.cue'); upload(None, 65537, 0, 'swapped2.cue', b'new bytes')
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    # Both the device object id and the content differ from what was approved.
    with pytest.raises(chd_io.RemoveUnverified, match='对象已变化'):
        mtp.remove_file(target, 'approved-sha', expected_id=999)
    assert not deleted_ids and files[target] == b'new bytes'


def test_remove_digest_guard_still_blocks_same_id_content_change(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'mutated.cue'); upload(None, 65537, 0, 'mutated.cue', b'mutated')
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    with pytest.raises(ValueError, match='已变化'):
        mtp.remove_file(target, 'approved-sha', expected_id=approved)
    assert not deleted_ids and files[target] == b'mutated'


def test_remove_never_deletes_after_path_moved_mid_readback(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'data.bin'); upload(None, 65537, 0, 'data.bin', b'track')
    saved = mtp.join(root, 'saved.bin')
    real_resolve = mtp.resolve; calls = [0]
    def resolve(handle, storage, parts, create=False):
        calls[0] += 1
        if calls[0] == 2:
            files[saved] = files.pop(target)   # renamed during the read-back
            return None
        return real_resolve(handle, storage, parts, create)
    monkeypatch.setattr(mtp, 'resolve', resolve)
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    calls[0] = 0
    with pytest.raises(chd_io.RemoveUnverified, match='移动|变化'):
        mtp.remove_file(target, chd_io.digest(target), expected_id=approved)
    assert not deleted_ids and files[saved] == b'track'


def test_remove_never_deletes_after_new_object_mid_readback(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'data2.bin'); upload(None, 65537, 0, 'data2.bin', b'track')
    real_resolve = mtp.resolve; calls = [0]
    def resolve(handle, storage, parts, create=False):
        calls[0] += 1
        entry = real_resolve(handle, storage, parts, create)
        if calls[0] == 2 and entry: entry = dict(entry, id=entry['id'] + 9000)
        return entry
    monkeypatch.setattr(mtp, 'resolve', resolve)
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    calls[0] = 0
    with pytest.raises(chd_io.RemoveUnverified, match='移动|变化'):
        mtp.remove_file(target, chd_io.digest(target), expected_id=approved)
    assert not deleted_ids and files[target] == b'track'


def test_remove_honors_cancellation_before_issuing_delete(device_files, monkeypatch):
    from task_control import TaskCancelled
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'halt.bin'); upload(None, 65537, 0, 'halt.bin', b'track')
    hits = [0]
    def cancelled():
        hits[0] += 1
        if hits[0] >= 2: raise TaskCancelled('stop')
    deleted_ids = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted_ids.append(ident) or 1
    with pytest.raises(TaskCancelled):
        mtp.remove_file(target, chd_io.digest(target), cancelled)
    assert not deleted_ids and files[target] == b'track'


def test_remove_cancels_during_final_lookup(device_files, monkeypatch):
    from task_control import TaskCancelled
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'victim.bin'); upload(None, 65537, 0, 'victim.bin', b'track')
    real_resolve = mtp.resolve; calls = [0]; stop = [False]
    def resolve(handle, storage, parts, create=False):
        calls[0] += 1
        if calls[0] == 2: stop[0] = True   # cancellation lands during the final lookup
        return real_resolve(handle, storage, parts, create)
    monkeypatch.setattr(mtp, 'resolve', resolve)
    def cancelled():
        if stop[0]: raise TaskCancelled('stop')
    deleted = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted.append(ident) or 1
    with pytest.raises(TaskCancelled):
        mtp.remove_file(target, chd_io.digest(target), cancelled)
    assert not deleted and files[target] == b'track'


def test_remove_flags_object_whose_readback_failed_after_rename(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'data3.bin'); upload(None, 65537, 0, 'data3.bin', b'track')
    saved = mtp.join(root, 'saved3.bin')
    def digest(path, *args, **kwargs):
        files[saved] = files.pop(target); raise RuntimeError('download error')
    monkeypatch.setattr(chd_io, 'digest', digest)
    deleted = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted.append(ident) or 1
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    with pytest.raises(chd_io.RemoveUnverified, match='变化'):
        mtp.remove_file(target, b'sha', expected_id=approved)
    assert not deleted and files[saved] == b'track'


def test_remove_stays_retryable_when_identity_confirmed_after_readback_error(device_files, monkeypatch):
    root, files, upload, lib = device_files
    chd_io = _stub_chd_digest(monkeypatch, files)
    target = mtp.join(root, 'flaky.bin'); upload(None, 65537, 0, 'flaky.bin', b'track')
    monkeypatch.setattr(chd_io, 'digest', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('download error')))
    deleted = []
    lib.LIBMTP_Delete_Object = lambda handle, ident: deleted.append(ident) or 1
    approved = mtp.resolve(None, 65537, mtp.parse(target)[2])['id']
    with pytest.raises(RuntimeError, match='download error'):
        mtp.remove_file(target, b'sha', expected_id=approved)
    assert not deleted and files[target] == b'track'
