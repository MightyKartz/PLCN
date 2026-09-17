import json
from pathlib import Path
import threading

import pytest
import requests
from PIL import Image

import server
from playlist_browser import read_playlist


def test_browsing_preserves_all_entries_and_only_reads_existing_artwork(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Browsing must not analyze, download, or save a playlist')
    import plcn
    from playlist_manager import PlaylistManager
    monkeypatch.setattr(plcn, 'analyze_playlist', unexpected)
    monkeypatch.setattr(PlaylistManager, 'save', unexpected)
    monkeypatch.setattr(requests.sessions.Session, 'request', unexpected)
    root = tmp_path / '图片'
    boxarts = root / 'GBA' / 'Named_Boxarts'
    boxarts.mkdir(parents=True)
    Image.new('RGB', (8, 8)).save(boxarts / '原名.png')
    (boxarts / '损坏.png').write_text('not an image')
    snaps = root / 'GBA' / 'Named_Snaps'
    snaps.mkdir()
    Image.new('RGB', (8, 8)).save(snaps / '截图.png')
    path = tmp_path / '自定义.lpl'
    path.write_text(json.dumps({'items': [
        {'label': '原名', 'path': r'C:\游戏\first.gba'},
        {'label': '原名', 'path': '/roms/duplicate.gba'},
        {'label': '损坏', 'path': '/roms/damaged.gba'},
        {'label': '截图', 'path': '/roms/snap.gba'},
        {'label': '', 'path': '/roms/unnamed.gba'},
    ]}), encoding='utf-8-sig')
    original = path.read_bytes()
    data = read_playlist(str(path), 'GBA', str(root))
    assert len(data['items']) == 5
    assert data['items'][0]['rom_name'] == 'first.gba'
    assert data['items'][0]['image_url'].startswith('/api/thumbnail/preview?path=')
    assert data['items'][0]['image_url'] != read_playlist(str(path), 'GBA', str(root))['items'][0]['image_url']
    assert data['items'][1]['label'] == '原名'
    assert data['items'][2]['image_url'] is None
    assert 'Named_Snaps' in data['items'][3]['image_url']
    assert data['items'][4]['label'] == ''
    assert 'new_label' not in data['items'][0]
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.bak'))


def test_browsing_adb_uses_materialized_playlist_and_batched_artwork_lookup(tmp_path, monkeypatch):
    import playlist_browser
    import single_artwork
    path = tmp_path / 'remote.lpl'
    path.write_text(json.dumps({'items': [{'label': '游戏', 'path': '/roms/game.gba'}]}))
    staging = []
    def materialize(value, cache_dir):
        staging.append(Path(cache_dir))
        assert Path(cache_dir).is_dir()
        return str(path)
    monkeypatch.setattr(playlist_browser, 'materialize_adb_file', materialize)
    calls = []
    def lookup(root, system, kind):
        calls.append(kind)
        return {'type': 'adb', 'serial': 'test', 'base_path': '/thumbs/GBA/' + kind,
                'filenames': {'游戏.png'} if kind == 'Named_Boxarts' else set()}
    monkeypatch.setattr(single_artwork, 'remote_inventory', lookup)
    data = read_playlist('adb://test/playlists/GBA.lpl', 'GBA', 'adb://test/thumbs')
    assert data['playlist_path'] == 'adb://test/playlists/GBA.lpl'
    assert 'adb%3A%2F%2Ftest' in data['items'][0]['image_url']
    assert len(calls) == 3
    assert not staging[0].exists()


def test_items_endpoint_handles_empty_invalid_missing_and_session_auth(tmp_path):
    path = tmp_path / 'empty.lpl'
    path.write_text('{"items": []}')
    bad = tmp_path / 'bad.lpl'
    bad.write_text('{"items": [null]}')
    httpd = server.LocalHTTPServer(('127.0.0.1', 0), server.ConfigHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{httpd.server_port}'
    try:
        with requests.Session() as client:
            client.trust_env = False
            assert client.get(url + '/api/playlist/items').status_code == 403
            client.get(url).raise_for_status()
            response = client.get(url + '/api/playlist/items', params={'path': str(path)})
            assert response.status_code == 200
            assert response.json()['items'] == []
            for value in ['', str(bad), str(tmp_path / 'missing.lpl')]:
                response = client.get(url + '/api/playlist/items', params={'path': value})
                assert response.status_code == 400
                assert response.json()['error']
            assert client.get(url + '/assets/library.js').status_code == 200
            image = tmp_path / 'mutable.png'
            Image.new('RGB', (8, 8), 'red').save(image)
            first = client.get(url + '/api/thumbnail/preview', params={'path': str(image)})
            assert first.headers['Cache-Control'] == 'no-store'
            Image.new('RGB', (8, 8), 'blue').save(image)
            second = client.get(url + '/api/thumbnail/preview', params={'path': str(image)})
            assert second.content != first.content
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(3)


def test_browser_shows_only_archive_member_but_preserves_full_path(tmp_path):
    path = tmp_path / 'PCE.lpl'
    rom = '/roms/仙魔大战 (日版).zip#Bikkuriman World (Japan).pce'
    path.write_text(json.dumps({'items': [{'label': '仙魔大战', 'path': rom}]}))
    item = read_playlist(str(path))['items'][0]
    assert item['rom_name'] == 'Bikkuriman World (Japan).pce'
    assert item['rom_path'] == rom


@pytest.mark.parametrize('remote', [False, True])
def test_browser_matches_retroarch_rom_filename_priority(tmp_path, monkeypatch, remote):
    import playlist_browser
    import single_artwork
    root = tmp_path / 'images'
    boxarts = root / 'SNES/Named_Boxarts'
    boxarts.mkdir(parents=True)
    for name in ['火焰之纹章4', '火焰之纹章 圣战之系谱']:
        Image.new('RGB', (8, 8)).save(boxarts / (name + '.png'))
    playlist = tmp_path / 'SNES.lpl'
    playlist.write_text(json.dumps({'items': [{'label': '火焰之纹章 圣战之系谱', 'path': '/roms/火焰之纹章4.sfc'}]}))
    if remote:
        monkeypatch.setattr(playlist_browser, 'materialize_adb_file', lambda *a, **kw: str(playlist))
        monkeypatch.setattr(single_artwork, 'remote_inventory', lambda r, s, k: {
            'type': 'adb', 'serial': 'device', 'base_path': '/images/SNES/' + k,
            'filenames': {p.name for p in boxarts.iterdir()} if k == 'Named_Boxarts' else set()})
    result = read_playlist('adb://device/SNES.lpl' if remote else str(playlist), 'SNES', 'adb://device/images' if remote else str(root))
    assert Path(result['items'][0]['image_path']).name == '火焰之纹章4.png'
