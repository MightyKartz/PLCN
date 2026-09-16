import json
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
