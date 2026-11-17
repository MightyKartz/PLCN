"""Completion receipts: durable undo across local / ADB / MTP completion runs."""
import hashlib
import io
import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

sys.path.append(os.path.join(os.getcwd(), 'src'))

import artwork_resolver
import completion_receipts
import mtp_runtime
import playlist_transport
import single_artwork
import app_paths
from retroarch_scanner import parse_adb_uri
import playlist_service as plcn

SYSTEM = 'Nintendo - Super Nintendo Entertainment System'
NEW_LABEL = '暗影狂奔'
FIXTURE = Path(__file__).parent.parent / 'fixtures' / 'playlists' / 'same_title_snes_shadowrun.lpl'


def png_bytes(color):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buffer, 'PNG')
    return buffer.getvalue()


BOXART_OLD = png_bytes((200, 10, 10))
SNAP_OLD = png_bytes((10, 200, 10))
NEW_IMAGE = png_bytes((10, 10, 200))
OTHER_OLD = png_bytes((128, 128, 0))


def filename(name):
    return artwork_resolver.sanitize_filename(name) + '.png'


def change_for(item):
    return {
        'proposal_id': plcn.build_proposal_id(SYSTEM, 0, item['path'], item['label'], item['db_name']),
        'index': 0,
        'original_label': item['label'],
        'original_item_label': item['label'],
        'original_db_name': item['db_name'],
        'path': item['path'],
        'new_label': NEW_LABEL,
        'thumbnail_source': item['label'],
        'system': SYSTEM,
        'replace_artwork_hashes': {'Named_Snaps': hashlib.sha256(SNAP_OLD).hexdigest()},
        'display_metadata': {'original_label': item['label'], 'original_item_label': item['label']},
    }


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    return tmp_path


def run_local_apply(home, monkeypatch, seed_new_boxart=False):
    import shutil
    lists = home / 'playlists'
    thumbs = home / 'thumbnails'
    lists.mkdir()
    playlist = lists / f'{SYSTEM}.lpl'
    shutil.copyfile(FIXTURE, playlist)
    item = json.loads(playlist.read_text(encoding='utf-8'))['items'][0]

    def artwork(kind, name):
        path = thumbs / SYSTEM / kind / filename(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # relabel-copy source: art stored under the old label
    old_boxart = artwork('Named_Boxarts', item['label'])
    old_boxart.write_bytes(BOXART_OLD)
    new_boxart = artwork('Named_Boxarts', NEW_LABEL)
    if seed_new_boxart:
        new_boxart.write_bytes(OTHER_OLD)
    # overwrite target: art already stored under the new label
    snap = artwork('Named_Snaps', NEW_LABEL)
    snap.write_bytes(SNAP_OLD)

    import requests
    class StubSession:
        def mount(self, *args, **kwargs):
            pass
        def get(self, url, timeout=0, **_kw):
            response = requests.Response()
            response.status_code = 200
            response._content = NEW_IMAGE
            response.url = url
            return response
    monkeypatch.setattr(requests, 'Session', lambda: StubSession())

    original = playlist.read_bytes()
    result = playlist_transport.apply_playlist(
        str(playlist), [change_for(item)], str(thumbs),
        options={'write_names': True, 'download_thumbnails': True},
        progress=lambda *args: None, cancel_check=lambda: False)
    return {'playlist': playlist, 'original': original, 'thumbs': thumbs,
            'boxart': new_boxart, 'snap': snap,
            'title': artwork('Named_Titles', NEW_LABEL), 'old_boxart': old_boxart,
            'result': result}


@pytest.fixture
def local_apply(home, monkeypatch):
    return run_local_apply(home, monkeypatch)


def test_local_end_to_end_undo(local_apply):
    result = local_apply['result']
    undo = result['undo']
    playlist_entry = undo['playlist']
    assert playlist_entry['transport'] == 'local'
    assert playlist_entry['path'] == str(local_apply['playlist'])
    assert playlist_entry['after_sha256'] == hashlib.sha256(local_apply['playlist'].read_bytes()).hexdigest()
    assert playlist_entry['history_id']
    assert Path(playlist_entry['backup']).is_file()

    images = {entry['destination']: entry for entry in undo['images']}
    assert str(local_apply['title']) in images           # newly downloaded
    assert str(local_apply['boxart']) in images          # relabel copy
    assert str(local_apply['snap']) in images            # overwrite
    assert images[str(local_apply['title'])]['replaced_backup'] is None
    assert images[str(local_apply['boxart'])]['replaced_backup'] is None
    snap_backup = Path(images[str(local_apply['snap'])]['replaced_backup'])
    assert snap_backup.read_bytes() == SNAP_OLD

    receipt_id = completion_receipts.create([result], '补全 SNES')
    receipt = completion_receipts.get(receipt_id)
    assert receipt['status'] == 'applied' and receipt['label'] == '补全 SNES'
    assert len(receipt['playlists']) == 1 and len(receipt['images']) == 3

    summary = completion_receipts.undo(receipt_id)
    assert summary['restored_playlists'] == 1
    assert summary['restored_images'] == 1
    assert summary['removed_images'] == 2
    assert summary['skipped'] == []
    assert local_apply['playlist'].read_bytes() == local_apply['original']
    assert not local_apply['title'].exists()
    assert not local_apply['boxart'].exists()
    assert local_apply['old_boxart'].read_bytes() == BOXART_OLD   # relabel source kept
    assert local_apply['snap'].read_bytes() == SNAP_OLD           # overwrite restored
    assert not list(local_apply['thumbs'].rglob('*.bak-*'))       # no write_target leftovers
    assert completion_receipts.get(receipt_id)['status'] == 'undone'
    with pytest.raises(ValueError, match='这次补全已撤销'):
        completion_receipts.undo(receipt_id)


def test_undo_guards_changed_targets(local_apply):
    result = local_apply['result']
    receipt_id = completion_receipts.create([result], '补全 SNES')
    playlist_bytes = local_apply['playlist'].read_bytes()
    local_apply['playlist'].write_bytes(b'{"items": [], "tampered": true}')
    local_apply['title'].write_bytes(b'not-the-downloaded-bytes')

    summary = completion_receipts.undo(receipt_id)
    reasons = {item['reason'] for item in summary['skipped']}
    assert reasons == {'changed'}
    assert completion_receipts.get(receipt_id)['status'] == 'partially_undone'
    assert local_apply['playlist'].read_bytes() == b'{"items": [], "tampered": true}'
    assert local_apply['title'].read_bytes() == b'not-the-downloaded-bytes'
    assert local_apply['snap'].read_bytes() == SNAP_OLD
    assert not local_apply['boxart'].exists()


def test_undo_leaves_preexisting_new_label_image(home, monkeypatch):
    local_apply = run_local_apply(home, monkeypatch, seed_new_boxart=True)
    result = local_apply['result']
    destinations = {entry['destination'] for entry in result['undo']['images']}
    assert str(local_apply['boxart']) not in destinations          # already existed, not a copy
    assert str(local_apply['title']) in destinations
    assert str(local_apply['snap']) in destinations

    receipt_id = completion_receipts.create([result], '补全 SNES')
    summary = completion_receipts.undo(receipt_id)
    assert summary['skipped'] == []
    assert local_apply['boxart'].read_bytes() == OTHER_OLD         # untouched, byte-identical
    assert local_apply['playlist'].read_bytes() == local_apply['original']
    assert not local_apply['title'].exists()
    assert local_apply['snap'].read_bytes() == SNAP_OLD


def test_create_returns_none_without_undo_targets():
    assert completion_receipts.create([], '补全') is None
    assert completion_receipts.create({'apply': {'applied_count': 0}}, '补全') is None


def test_receipt_pruning_keeps_twenty(home):
    result = {'undo': {'playlist': None, 'images': [
        {'destination': str(home / f'img-{i}.png'), 'sha256': 'a' * 64, 'replaced_backup': None}
        for i in range(1)]}}
    ids = [completion_receipts.create([result], f'补全 {i}') for i in range(22)]
    files = sorted(completion_receipts.receipts_dir().glob('*.json'))
    assert len(files) == 20
    remaining = {file.stem for file in files}
    assert set(ids[-20:]) == remaining
    listed = completion_receipts.list_receipts()
    assert len(listed) == 20
    assert [entry['id'] for entry in listed] == ids[-1:-21:-1]
    assert listed[0]['counts'] == {'playlists': 0, 'images': 1}


def test_get_rejects_bad_ids():
    with pytest.raises(ValueError):
        completion_receipts.get('bad')
    with pytest.raises(ValueError):
        completion_receipts.get('a' * 32)


class FakeMtp:
    """In-memory MTP store shared by fake read/write/remove."""

    def __init__(self):
        self.files = {}
        self.reads = []
        self.writes = []
        self.removes = []

    def read(self, uri):
        self.reads.append(uri)
        return self.files.get(uri)

    def write(self, uri, content, expected, suffix=None):
        self.writes.append((uri, content, expected))
        current = self.files.get(uri)
        assert (hashlib.sha256(current).hexdigest() if current is not None else None) == expected
        backup = uri + '.bak-undo'
        if current is not None:
            self.files[backup] = current
        self.files[uri] = content
        return backup

    def remove_verified(self, uri, expected):
        self.removes.append((uri, expected))
        current = self.files.get(uri)
        assert current is not None and hashlib.sha256(current).hexdigest() == expected
        del self.files[uri]


def mtp_apply_result(home, monkeypatch):
    """Run apply_playlist against in-memory MTP fakes and return (result, store)."""
    store = FakeMtp()
    playlist_uri = 'mtp://device/00010001/sdcard/RetroArch/playlists/NES.lpl'
    original = json.dumps({'items': [{'label': 'Game', 'path': '/roms/Game.nes', 'db_name': 'NES.lpl'}]}).encode()
    store.files[playlist_uri] = original
    monkeypatch.setattr(mtp_runtime, 'read', store.read)
    monkeypatch.setattr(mtp_runtime, 'write', store.write)
    def materialize(uri, cache):
        local = Path(cache) / 'NES.lpl'
        local.write_bytes(store.read(uri))
        return str(local)
    monkeypatch.setattr(mtp_runtime, 'materialize', materialize)
    monkeypatch.setattr(mtp_runtime, 'push_directory', lambda local, uri, **kwargs: None)
    monkeypatch.setattr(mtp_runtime, 'remove_verified', store.remove_verified)
    monkeypatch.setattr(mtp_runtime, 'remove_file', lambda *a, **k: None)

    def fake_apply(playlist_path, changes, thumbnails_dir, **kwargs):
        staged = Path(thumbnails_dir) / 'NES' / 'Named_Boxarts' / '游戏.png'
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(NEW_IMAGE)
        item = json.loads(original)
        item['items'][0]['label'] = '游戏'
        Path(playlist_path).write_text(json.dumps(item), encoding='utf-8')
        writeback = {'applied': [{'new_label': '游戏', 'old_label': 'Game', 'system': 'NES', 'index': 0}],
                     'backup_path': None, 'history_id': None}
        return {'download_summary': {'details': [{'type': 'Named_Boxarts', 'status': 'success',
                                                 'path': str(staged), 'system': 'NES', 'game': '游戏',
                                                 'source': 'Game'}],
                                     'writeback': writeback},
                'apply': {'applied': writeback['applied'], 'skipped': []}}
    monkeypatch.setattr(playlist_transport.playlist_service, 'apply_changes', fake_apply)
    change = {'index': 0, 'new_label': '游戏', 'system': 'NES', 'path': '/roms/Game.nes',
              'original_item_label': 'Game', 'thumbnail_source': 'Game',
              'display_metadata': {'original_label': 'Game', 'original_item_label': 'Game'}}
    result = playlist_transport.apply_playlist(
        playlist_uri, [change], 'mtp://device/00010001/sdcard/RetroArch/thumbnails',
        options={'write_names': True, 'download_thumbnails': True},
        progress=lambda *args: None, cancel_check=lambda: False)
    return result, store, playlist_uri, original


def test_mtp_apply_records_undo(home, monkeypatch):
    result, store, playlist_uri, original = mtp_apply_result(home, monkeypatch)
    undo = result['undo']
    entry = undo['playlist']
    assert entry['transport'] == 'mtp'
    assert entry['path'] == playlist_uri
    assert entry['backup'] == playlist_uri + '.bak-undo'
    assert entry['after_sha256'] == hashlib.sha256(store.files[playlist_uri]).hexdigest()
    images = undo['images']
    expected_uri = mtp_runtime.join('mtp://device/00010001/sdcard/RetroArch/thumbnails',
                                    'NES', 'Named_Boxarts', '游戏.png')
    assert images == [{'destination': expected_uri,
                       'sha256': hashlib.sha256(NEW_IMAGE).hexdigest(), 'replaced_backup': None}]


def test_mtp_undo_uses_verified_remove_and_write(home, monkeypatch):
    result, store, playlist_uri, original = mtp_apply_result(home, monkeypatch)
    # simulate the pushed remote state
    remote_playlist = store.files[playlist_uri]
    image_uri = result['undo']['images'][0]['destination']
    store.files[image_uri] = NEW_IMAGE
    receipt_id = completion_receipts.create([result], '补全全部主机')

    summary = completion_receipts.undo(receipt_id)
    assert summary == {'restored_playlists': 1, 'removed_images': 1, 'restored_images': 0, 'skipped': []}
    assert store.removes == [(image_uri, hashlib.sha256(NEW_IMAGE).hexdigest())]
    restore_writes = [call for call in store.writes if call[0] == playlist_uri]
    assert len(restore_writes) == 2                            # apply + undo
    assert restore_writes[-1][2] == hashlib.sha256(remote_playlist).hexdigest()
    assert store.files[playlist_uri] == original


def test_adb_apply_records_undo_and_back_up_overwritten_image(home, monkeypatch):
    playlist_uri = 'adb://device/sdcard/RetroArch/playlists/NES.lpl'
    remote = {playlist_uri: json.dumps({'items': [{'label': 'Game', 'path': '/roms/Game.nes', 'db_name': 'NES.lpl'}]}).encode()}
    image_uri = 'adb://device/sdcard/RetroArch/thumbnails/NES/Named_Boxarts/游戏.png'
    remote[image_uri] = OTHER_OLD
    def materialize(uri, cache_dir=None, **_kw):
        local = Path(cache_dir) / 'NES.lpl'
        local.write_bytes(remote[uri])
        return str(local)
    monkeypatch.setattr(playlist_transport, 'materialize_adb_file', materialize)
    monkeypatch.setattr(playlist_transport, 'verified_push_adb_playlist',
                        lambda local, uri, expected: remote.__setitem__(uri, Path(local).read_bytes()) or uri + '.bak')
    pushed = []
    monkeypatch.setattr(playlist_transport, 'push_adb_directory', lambda local, uri: pushed.append((local, uri)))

    # pre-push read of the destination image via single_artwork.read_target
    def fake_read(target):
        return remote.get(target)
    monkeypatch.setattr(single_artwork, 'read_target', fake_read)
    staged_images = {}

    def fake_apply(playlist_path, changes, thumbnails_dir, **kwargs):
        staged = Path(thumbnails_dir) / 'NES' / 'Named_Boxarts' / '游戏.png'
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(NEW_IMAGE)
        staged_images['path'] = staged
        item = json.loads(Path(playlist_path).read_text(encoding='utf-8'))
        item['items'][0]['label'] = '游戏'
        Path(playlist_path).write_text(json.dumps(item), encoding='utf-8')
        writeback = {'applied': [{'new_label': '游戏', 'old_label': 'Game', 'system': 'NES', 'index': 0}],
                     'backup_path': None, 'history_id': None}
        return {'download_summary': {'details': [{'type': 'Named_Boxarts', 'status': 'success',
                                                 'path': str(staged), 'system': 'NES', 'game': '游戏',
                                                 'source': 'Game'}],
                                     'writeback': writeback},
                'apply': {'applied': writeback['applied'], 'skipped': []}}
    monkeypatch.setattr(playlist_transport.playlist_service, 'apply_changes', fake_apply)
    change = {'index': 0, 'new_label': '游戏', 'system': 'NES', 'path': '/roms/Game.nes',
              'original_item_label': 'Game', 'thumbnail_source': 'Game',
              'display_metadata': {'original_label': 'Game', 'original_item_label': 'Game'}}
    result = playlist_transport.apply_playlist(
        playlist_uri, [change], 'adb://device/sdcard/RetroArch/thumbnails',
        options={'write_names': True, 'download_thumbnails': True},
        progress=lambda *args: None, cancel_check=lambda: False)

    entry = result['undo']['playlist']
    assert entry['transport'] == 'adb' and entry['path'] == playlist_uri
    assert entry['backup'] == playlist_uri + '.bak'
    assert entry['after_sha256'] == hashlib.sha256(remote[playlist_uri]).hexdigest()
    images = result['undo']['images']
    assert images[0]['destination'] == image_uri
    backup = Path(images[0]['replaced_backup'])
    assert backup.read_bytes() == OTHER_OLD            # remote bytes backed up locally before push
    assert pushed


def test_adb_undo_removes_with_rm_after_digest_check(home, monkeypatch):
    image_uri = 'adb://device/sdcard/thumbnails/NES/Named_Boxarts/游戏.png'
    remote = {image_uri: NEW_IMAGE}
    receipt = {'id': 'a' * 32, 'created_at': '2026-01-01T00:00:00+00:00', 'label': '补全',
               'status': 'applied',
               'playlists': [],
               'images': [{'destination': image_uri, 'sha256': hashlib.sha256(NEW_IMAGE).hexdigest(),
                           'replaced_backup': None}],
               'outcome': None, 'undone_at': None}
    completion_receipts.receipts_dir().mkdir(parents=True, exist_ok=True)
    (completion_receipts.receipts_dir() / (receipt['id'] + '.json')).write_text(json.dumps(receipt), encoding='utf-8')

    removed = []
    def adb_command(serial, cmd):
        removed.append((serial, cmd))
        for uri in list(remote):
            if cmd.endswith(shlex.quote(parse_adb_uri(uri)[1])):
                remote.pop(uri)
    monkeypatch.setattr(single_artwork, 'read_target', lambda target: remote.get(target))
    monkeypatch.setattr(single_artwork, 'adb_command', adb_command)

    summary = completion_receipts.undo(receipt['id'])
    assert summary == {'restored_playlists': 0, 'removed_images': 1, 'restored_images': 0, 'skipped': []}
    assert removed == [('device', "rm -f '/sdcard/thumbnails/NES/Named_Boxarts/游戏.png'")]


def test_apply_api_result_includes_receipt_id(home, monkeypatch):
    from job_manager import JobManager
    import api_playlists

    class Handler:
        body = None
        def send_response(self, status):
            self.status = status
        def send_header(self, *args):
            pass
        def end_headers(self):
            pass
        wfile = io.BytesIO()
    class Context:
        job_manager = JobManager()
    context = Context()
    monkeypatch.setattr(playlist_transport, 'apply_playlist',
                        lambda *args, **kwargs: {'undo': {'playlist': None, 'images': [
                            {'destination': 'x', 'sha256': 'a' * 64, 'replaced_backup': None}]},
                                                 'transport': 'local'})
    handler = Handler()
    api_playlists.apply(handler, context, {'playlist_path': '/x/NES.lpl',
                                          'changes': [{'system': 'NES'}], 'options': {}})
    reply = json.loads(handler.wfile.getvalue())
    job_id = reply['job_id']
    for _ in range(100):
        job = context.job_manager.get_job(job_id)
        if job and job['status'] in ('completed', 'failed'):
            break
        time.sleep(0.05)
    assert job['status'] == 'completed', job
    assert job['result']['receipt_id'] == completion_receipts.list_receipts()[0]['id']
    assert job['result']['transport'] == 'local'


def test_undo_route_runs_summary(home, monkeypatch):
    from job_manager import JobManager
    import api_playlists

    receipt_id = completion_receipts.create([{'undo': {'playlist': None, 'images': [
        {'destination': str(home / 'missing.png'), 'sha256': 'a' * 64, 'replaced_backup': None}]}}], '补全 NES')
    assert receipt_id is not None

    class Handler:
        def send_response(self, status):
            pass
        def send_header(self, *args):
            pass
        def end_headers(self):
            pass
        wfile = io.BytesIO()
    class Context:
        job_manager = JobManager()
    context = Context()
    handler = Handler()
    api_playlists.completion_undo(handler, context, {'id': receipt_id})
    job_id = json.loads(handler.wfile.getvalue())['job_id']
    job = None
    for _ in range(100):
        job = context.job_manager.get_job(job_id)
        if job and job['status'] in ('completed', 'failed'):
            break
        time.sleep(0.05)
    assert job['status'] == 'completed', job
    assert set(job['result']) == {'restored_playlists', 'removed_images', 'restored_images', 'skipped'}
    assert completion_receipts.get(receipt_id)['status'] in ('partially_undone', 'undone')
