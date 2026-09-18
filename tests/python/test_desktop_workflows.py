import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
import requests
from http.server import ThreadingHTTPServer

import app_paths
from app_runtime import InstanceLock
import plcn
import repair_history
import server
from safe_io import file_digest
from task_control import TaskCancelled
from thumbnail_downloader import ThumbnailDownloader


@pytest.fixture
def desktop_home(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'user'))
    return tmp_path / 'user'


def test_platform_paths_and_resource_independence(tmp_path, monkeypatch):
    assert app_paths.user_data_dir('win32', {'LOCALAPPDATA': str(tmp_path)}, tmp_path) == tmp_path / 'PLCN'
    assert app_paths.user_data_dir('darwin', {}, tmp_path) == tmp_path / 'Library/Application Support/PLCN'
    assert app_paths.user_data_dir('linux', {'XDG_DATA_HOME': str(tmp_path)}, tmp_path) == tmp_path / 'PLCN'
    root = app_paths.resource_root()
    monkeypatch.chdir(tmp_path)
    assert app_paths.resource_root() == root
    assert app_paths.default_source().is_dir()


def test_migration_preserves_originals_resolves_paths_and_is_idempotent(tmp_path, desktop_home):
    old = tmp_path / 'old'; old.mkdir()
    config = old / 'config.json'
    config.write_text(json.dumps({'playlist_path': 'lists/中文.lpl', 'rom_name_cn_path': 'missing/data', 'manual_overrides_path': 'manual_overrides.json'}), encoding='utf-8')
    (old / 'manual_overrides.json').write_text('[{"label":"中文"}]', encoding='utf-8')
    original = config.read_bytes()
    app_paths.initialize(old)
    migrated = json.loads(app_paths.config_path().read_text(encoding='utf-8'))
    assert migrated['playlist_path'] == str((old / 'lists/中文.lpl').resolve())
    assert 'rom_name_cn_path' not in migrated
    assert Path(migrated['manual_overrides_path']).read_text(encoding='utf-8') == '[{"label":"中文"}]'
    app_paths.config_path().write_text('{"user_changed":true}')
    app_paths.initialize(old)
    assert json.loads(app_paths.config_path().read_text()) == {'user_changed': True}
    assert config.read_bytes() == original


def test_existing_user_config_is_never_overwritten(tmp_path, desktop_home):
    desktop_home.mkdir()
    app_paths.config_path().write_text('{"mine":true}')
    old = tmp_path / 'old'; old.mkdir(); (old / 'config.json').write_text('{"mine":false}')
    app_paths.initialize(old)
    assert json.loads(app_paths.config_path().read_text())['mine'] is True


def test_single_instance_lock_releases_on_close(tmp_path):
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.publish('http://127.0.0.1:9999', 'test')
    first.close()
    assert not first.state_path.exists()
    assert second.acquire()
    second.close()


def test_local_server_owns_its_port_exclusively():
    # In particular, Windows must reject a second server using SO_REUSEADDR.
    with server.LocalHTTPServer(('127.0.0.1', 0), server.ConfigHandler) as first:
        with pytest.raises(OSError):
            with ThreadingHTTPServer(first.server_address, server.ConfigHandler):
                pytest.fail('Another process could bind the live instance port')


def fixture_playlist(tmp_path):
    path = tmp_path / '中文.lpl'
    path.write_text(json.dumps({'items': [{'path': '/roms/Game.zip', 'label': 'Original'}]}), encoding='utf-8')
    change = {'index': 0, 'path': '/roms/Game.zip', 'original_item_label': 'Original', 'new_label': '中文', 'system': 'NES', 'thumbnail_source': 'Game'}
    return path, change


def test_history_restore_and_refusal_after_external_edit(tmp_path, desktop_home):
    path, change = fixture_playlist(tmp_path)
    original = path.read_bytes()
    plcn.apply_changes(str(path), [change], str(tmp_path), download_thumbnails=False)
    entry = repair_history.list_history()[0]
    modified = path.read_bytes()
    path.write_bytes(b'{"items":[]}')
    with pytest.raises(ValueError, match='已发生变化'):
        repair_history.restore(entry['id'])
    assert path.read_bytes() == b'{"items":[]}'
    path.write_bytes(modified)
    restored = repair_history.restore(entry['id'])
    assert path.read_bytes() == original
    assert Path(restored['before_restore_backup']).read_bytes() == modified
    with pytest.raises(ValueError, match='已经恢复'):
        repair_history.restore(entry['id'])


def test_only_artwork_preserves_playlist_bytes_and_uses_existing_label(tmp_path, desktop_home, monkeypatch):
    path, change = fixture_playlist(tmp_path)
    before = file_digest(path)
    tasks = []
    def download(self, values, **kwargs):
        tasks.extend(values)
        return self.empty_summary(len(values))
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', download)
    plcn.apply_changes(str(path), [change], str(tmp_path), write_names=False)
    assert file_digest(path) == before
    assert tasks == [('NES', 'Game', 'Original')]
    assert not list(tmp_path.glob('*.bak*'))
    assert not repair_history.list_history()


def test_cancel_before_write_preserves_file(tmp_path, desktop_home):
    path, change = fixture_playlist(tmp_path)
    before = path.read_bytes()
    with pytest.raises(TaskCancelled):
        plcn.apply_changes(str(path), [change], str(tmp_path), cancel_check=lambda: True)
    assert path.read_bytes() == before
    assert not repair_history.list_history()


def test_cancel_images_keeps_completed_work(tmp_path):
    event = threading.Event()
    downloader = ThumbnailDownloader(str(tmp_path))
    downloader.cancel_check = event.is_set
    calls = []
    def get(*args, **kwargs):
        calls.append(args)
        event.set()
        return SimpleNamespace(status_code=404)
    downloader.session.get = get
    results = downloader.download_thumbnail('NES', 'Game', '中文')
    assert len(calls) == 1
    assert [row.get('reason') for row in results] == ['not_found', 'cancelled', 'cancelled']


def test_desktop_endpoints_and_shutdown_refuses_active_work(tmp_path, desktop_home, monkeypatch):
    import native_dialog
    monkeypatch.setattr(native_dialog, 'pick', lambda kind, initial: str(tmp_path / '选择目录'))
    jobs = server.JobManager()
    monkeypatch.setattr(server, 'job_manager', jobs)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.ConfigHandler)
    httpd.instance_id = 'test-instance'
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{httpd.server_port}'
    try:
        with requests.Session() as client:
            client.get(url, timeout=3).raise_for_status()
            assert client.get(url + '/api/instance', timeout=3).json()['instance_id'] == 'test-instance'
            assert client.get(url + '/assets/desktop.js', timeout=3).status_code == 200
            assert client.get(url + '/assets/workflow.js', timeout=3).status_code == 200
            assert client.get(url + '/api/data', timeout=3).json()['source_kind'] == 'bundled'
            picked = client.post(url + '/api/desktop/pick', json={'kind': 'directory'}, timeout=3).json()
            assert picked['path'].endswith('选择目录')
            job = jobs.create_job()
            assert client.post(url + '/api/desktop/shutdown', json={}, timeout=3).status_code == 409
            assert client.post(url + '/api/jobs/cancel', json={'job_id': job}, timeout=3).status_code == 200
            jobs.complete_job(job, {'partial': True})
            assert jobs.get_job(job)['status'] == 'cancelled'
            assert client.get(url + '/api/desktop', timeout=3).json()['jobs'][0]['result']['partial']
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(3)


def test_compare_installed_pack_keeps_active_config_and_reuses_baseline(tmp_path, desktop_home):
    import data_pack
    from desktop_api import compare_active, managed_pack
    source = tmp_path / 'source'; source.mkdir()
    csv = source / 'NES.csv'
    csv.write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    pack = desktop_home / 'packs' / 'test'
    data_pack.build_pack(source, pack)
    csv.write_text('Name EN,Name CN\nGame,新版\nAnother,另一个\n', encoding='utf-8')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'rom_name_cn_path': str(source), 'manual_overrides_path': 'keep.json'}), encoding='utf-8')
    before = config.read_bytes()
    result = compare_active(pack, config)
    assert result == {'added': 0, 'removed': 1, 'changed': 1, 'untranslated': 0}
    assert compare_active(pack, config) == result
    assert len(list((desktop_home / 'packs').glob('baseline-*'))) == 1
    assert config.read_bytes() == before
    assert managed_pack(str(pack)) == pack.resolve()
    with pytest.raises(ValueError, match='数据目录'):
        managed_pack(str(tmp_path / 'unmanaged'))


def test_desktop_launcher_restores_streams_after_service_exit(desktop_home, monkeypatch):
    import desktop
    import sys
    stdout, stderr = sys.stdout, sys.stderr
    monkeypatch.setattr(sys, 'argv', ['desktop.py'])
    monkeypatch.setattr(server, 'run_server', lambda **kwargs: print('service completed'))
    desktop.main()
    assert sys.stdout is stdout and sys.stderr is stderr
    assert 'service completed' in (desktop_home / 'logs/desktop.log').read_text(encoding='utf-8')


def test_retry_keeps_adb_thumbnail_target(tmp_path, desktop_home, monkeypatch):
    jobs = server.JobManager()
    monkeypatch.setattr(server, 'job_manager', jobs)
    old = jobs.create_job()
    jobs.contexts[old] = {'thumbnails_dir': 'adb://device/sdcard/RetroArch/thumbnails'}
    jobs.complete_job(old, {'download_summary': {'details': [{'system': 'Sony - PlayStation', 'source': 'Game (USA)', 'game': '中文', 'type': 'Named_Boxarts', 'status': 'failed', 'reason': 'not_found'}]}})

    import desktop_api
    handler = SimpleNamespace(replies=[])
    def reply(_handler, data, status=200):
        handler.replies.append((status, data))
    monkeypatch.setattr(desktop_api, 'reply', reply)
    desktop_api.post(handler, '/api/jobs/retry', {'job_id': old}, jobs, str(tmp_path / 'config.json'))
    assert handler.replies[0][1]['job_id']
    assert jobs.contexts[handler.replies[0][1]['job_id']]['thumbnails_dir'].startswith('adb://')
