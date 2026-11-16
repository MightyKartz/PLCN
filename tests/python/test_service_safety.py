import json
import re
import shlex
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent / 'src'))
import server
from retroarch_scanner import verified_push_adb_playlist


@pytest.fixture
def service():
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.ConfigHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}'
    httpd.shutdown()
    httpd.server_close()
    thread.join(2)


def test_local_session_and_same_origin_required(service):
    assert requests.get(service + '/api/config', timeout=3).status_code == 403
    session = requests.Session()
    assert session.get(service, timeout=3).status_code == 200
    assert session.get(service + '/api/config', timeout=3).status_code == 200
    assert session.get(service + '/README.md', timeout=3).status_code == 404
    assert session.get(service + '/api/config', headers={'Origin': 'https://example.com'}, timeout=3).status_code == 403
    assert session.get(service, headers={'Host': 'evil.test'}, timeout=3).status_code == 403
    assert session.post(service + '/api/config', data='{}', timeout=3).status_code == 415
    assert session.head(service + '/README.md', timeout=3).status_code == 405


def test_page_assets_are_served_from_the_explicit_allowlist(service):
    with requests.Session() as session:
        page = session.get(service, timeout=3)
        page.raise_for_status()
        assets = re.findall(r'(?:src|href)="/assets/([^"/]+)"', page.text)
        assert set(assets) | {'workbench-icons.svg'} == set(server.UI_ASSETS)
        for name in server.UI_ASSETS:
            response = session.get(service + '/assets/' + name, timeout=3)
            assert response.status_code == 200
            assert response.content == (Path(server.TEMPLATE_DIR) / name).read_bytes()
            mime = 'image/svg+xml' if name.endswith('.svg') else ('text/javascript' if name.endswith('.js') else 'text/css') + '; charset=utf-8'
            assert response.headers['Content-Type'] == mime
        assert session.get(service + '/assets/server.py', timeout=3).status_code == 404


def test_active_pack_stats_and_clean_system_names(service, tmp_path, monkeypatch):
    from data_pack import build_pack
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'NES (20240622-035607) (1).csv').write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    (source / 'missing_games.csv').write_text('Name EN,Name CN\nOther,其他\n', encoding='utf-8')
    pack = tmp_path / 'pack'
    build_pack(source, pack)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'rom_name_cn_path': str(pack / 'rom-name-cn')}), encoding='utf-8')
    monkeypatch.setattr(server, 'CONFIG_FILE', str(config))
    with requests.Session() as session:
        session.get(service, timeout=3).raise_for_status()
        stats = session.get(service + '/api/stats', timeout=3).json()
        systems = session.get(service + '/api/systems', timeout=3).json()['systems']
    assert stats['database_count'] == 2
    assert stats['database_ready'] is True
    assert 'NES' in systems and 'missing_games' not in systems
    assert not any('(20240622' in value for value in systems)


def adb_files(tmp_path, corrupt_stage=False):
    old = {'items': [{'path': '/game.zip', 'label': 'Old'}]}
    new = {'items': [{'path': '/game.zip', 'label': '中文'}]}
    local = tmp_path / 'list.lpl'
    local.write_text(json.dumps(new), encoding='utf-8')
    files = {'/list.lpl': json.dumps(old)}
    def runner(args, timeout=10):
        if args[2:4] == ['exec-out', 'cat']:
            return files[args[4]]
        if args[2] == 'push':
            files[args[4]] = '{}' if corrupt_stage else Path(args[3]).read_text(encoding='utf-8')
        elif args[2] == 'shell':
            parts = shlex.split(args[3])
            if parts[0] in {'cp', 'mv'}:
                files[parts[2]] = files[parts[1]]
                if parts[0] == 'mv':
                    del files[parts[1]]
            elif parts[0] == 'rm':
                files.pop(parts[-1], None)
        return ''
    return local, files, old, new, runner


def test_adb_stages_backs_up_and_reads_back(tmp_path):
    local, files, old, new, runner = adb_files(tmp_path)
    backup = verified_push_adb_playlist(str(local), 'adb://device/list.lpl', old, runner)
    assert json.loads(files['/list.lpl']) == new
    assert json.loads(files[backup.removeprefix('adb://device')]) == old
    assert not any(path.endswith('.tmp') for path in files)


def test_adb_conflict_preserves_external_changes(tmp_path):
    local, files, old, new, runner = adb_files(tmp_path)
    files['/list.lpl'] = '{"items":[]}'
    with pytest.raises(RuntimeError, match='已改变'):
        verified_push_adb_playlist(str(local), 'adb://device/list.lpl', old, runner)
    assert files == {'/list.lpl': '{"items":[]}'}


def test_corrupt_adb_upload_does_not_replace_original(tmp_path):
    local, files, old, new, runner = adb_files(tmp_path, corrupt_stage=True)
    with pytest.raises(RuntimeError, match='暂存文件验证失败'):
        verified_push_adb_playlist(str(local), 'adb://device/list.lpl', old, runner)
    assert json.loads(files['/list.lpl']) == old
    assert len(files) == 1


@pytest.mark.parametrize('body', ['{', '[]', 'null'])
def test_json_boundary_rejects_invalid_payload_without_changing_config(service, tmp_path, monkeypatch, body):
    config = tmp_path / 'config.json'
    config.write_text('{"keep": true}', encoding='utf-8')
    monkeypatch.setattr(server, 'CONFIG_FILE', str(config))
    with requests.Session() as session:
        session.get(service, timeout=3).raise_for_status()
        response = session.post(service + '/api/config', data=body,
                                headers={'Content-Type': 'application/json'}, timeout=3)
    assert response.status_code == 400
    assert response.json()['error']
    assert config.read_text(encoding='utf-8') == '{"keep": true}'


@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
def test_playlist_routes_preview_write_and_report_progress(service, tmp_path, monkeypatch, batch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(server, 'job_manager', server.JobManager())
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'NES.csv').write_text('Name EN,Name CN\nGame,游戏\n', encoding='utf-8')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'rom_name_cn_path': str(source)}), encoding='utf-8')
    monkeypatch.setattr(server, 'CONFIG_FILE', str(config))
    playlists = tmp_path / 'playlists'
    playlists.mkdir()
    playlist = playlists / 'NES.lpl'
    original = {'items': [{'path': '/roms/Game.nes', 'label': 'Game', 'db_name': 'NES.lpl'}]}
    playlist.write_text(json.dumps(original), encoding='utf-8')
    with requests.Session() as session:
        session.get(service, timeout=3).raise_for_status()
        preview = session.post(service + '/api/playlist/preview', json={
            'playlist_path': str(playlist), 'system_name': 'NES', 'thumbnails_dir': str(tmp_path / 'images'),
        }, timeout=5)
        preview.raise_for_status()
        changes = preview.json()['changes']
        assert changes[0]['new_label'] == '游戏'
        assert json.loads(playlist.read_text(encoding='utf-8')) == original
        payload = {'thumbnails_dir': str(tmp_path / 'images'), 'options': {'download_thumbnails': False}}
        if batch:
            payload['batch_dir'] = str(playlists)
            started = session.post(service + '/api/batch/preview', json=payload, timeout=3)
            started.raise_for_status()
            review_id = started.json()['job_id']
            with session.get(service + '/api/progress', params={'job_id': review_id}, stream=True, timeout=5) as progress:
                for line in progress.iter_lines(chunk_size=1):
                    if line.startswith(b'data: '):
                        review = json.loads(line[6:])
                        if review['status'] in ('completed', 'failed', 'cancelled'):
                            break
            assert review['status'] == 'completed', review
            assert review['result']['rows'][0]['names'] == 1
            assert json.loads(playlist.read_text(encoding='utf-8')) == original
            payload = {'preview_job_id': review_id}
            endpoint = '/api/batch/apply'
        else:
            payload.update(playlist_path=str(playlist), changes=changes)
            endpoint = '/api/playlist/apply'
        response = session.post(service + endpoint, json=payload, timeout=3)
        response.raise_for_status()
        job_id = response.json()['job_id']
        with session.get(service + '/api/progress', params={'job_id': job_id}, stream=True, timeout=5) as progress:
            progress.raise_for_status()
            for line in progress.iter_lines(chunk_size=1):
                if line.startswith(b'data: '):
                    final = json.loads(line[6:])
                    if final['status'] in ('completed', 'failed', 'cancelled'):
                        break
    assert final['status'] == 'completed', final
    assert not server.job_manager.active()
    assert json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['label'] == '游戏'
    if batch:
        assert final['result']['processed_count'] == 1
    else:
        assert final['result']['applied_count'] == 1
        assert final['result']['apply']['backup_path']


def test_open_folder_route_reaches_platform_opener(service, tmp_path, monkeypatch):
    import api_library
    opened = []
    monkeypatch.setattr(api_library.subprocess, 'Popen', lambda args: opened.append(args[-1]))
    monkeypatch.setattr(api_library.os, 'startfile', lambda path: opened.append(path), raising=False)
    file = tmp_path / 'game.lpl'
    file.write_text('{}', encoding='utf-8')
    with requests.Session() as session:
        session.get(service, timeout=3).raise_for_status()
        response = session.post(service + '/api/fs/open', json={'path': str(file)}, timeout=3)
        response.raise_for_status()
        assert response.json() == {'status': 'success', 'path': str(tmp_path)}
    assert opened == [str(tmp_path)]


def test_batch_apply_requires_a_completed_review(service, monkeypatch):
    monkeypatch.setattr(server, 'job_manager', server.JobManager())
    with requests.Session() as session:
        session.get(service, timeout=3).raise_for_status()
        response = session.post(service + '/api/batch/apply', json={'batch_dir': '/unreviewed'}, timeout=3)
        assert response.status_code == 400
        assert '汇总' in response.json()['error']
        assert not server.job_manager.jobs
