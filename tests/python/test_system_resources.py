import json

import pytest

from playlist_analysis import analyze_playlist
from playlist_browser import read_playlist
from retroarch_scanner import _read_playlist_summary, _read_adb_playlist_summary
from system_resources import is_system_resource


SYSTEM = 'FBNeo - Arcade Games'


def resource_items():
    return [{'path': '/roms/' + stem + '.zip', 'label': stem, 'db_name': SYSTEM + '.lpl'}
            for stem in ('neogeo', 'pgm', 'nmk004', 'skns')]


def test_bios_excluded_from_browsing_model_preview_and_counts_without_deleting(tmp_path, monkeypatch):
    items = resource_items()
    items.insert(1, {'path': '/roms/s1945.zip', 'label': '打击者1945', 'db_name': SYSTEM + '.lpl'})
    playlist = tmp_path / (SYSTEM + '.lpl')
    playlist.write_text(json.dumps({'items': items}))
    before = playlist.read_bytes()
    browser = read_playlist(str(playlist), SYSTEM)
    assert [r['index'] for r in browser['items']] == [1]
    assert len(browser['library_model']['games']) == 1
    assert len(browser['library_model']['entries']) == 5
    assert browser['library_model']['entries'][0]['game_id'] is None
    proposals = analyze_playlist(str(playlist), SYSTEM, 'data/rom-name-cn')
    assert [r['index'] for r in proposals] == [1]
    assert _read_playlist_summary(playlist)['item_count'] == 1
    monkeypatch.setattr('retroarch_scanner._adb_cat', lambda *args, **kwargs: before.decode())
    monkeypatch.setattr('retroarch_scanner._adb_stat_mtime', lambda *args, **kwargs: 0)
    assert _read_adb_playlist_summary('serial', '/playlists/FBNeo.lpl')['item_count'] == 1
    assert playlist.read_bytes() == before


@pytest.mark.parametrize('system', ['MAME', SYSTEM, 'Arcade - NEOGEO'])
def test_resource_identifiers_are_scoped_and_do_not_hide_bioship(system):
    for item in resource_items():
        item = dict(item, db_name=system + '.lpl', label='系统文件')
        assert is_system_resource(item, system)
    assert not is_system_resource({'path': '/roms/bioship.zip', 'label': 'Bio-ship Paladin'}, system)
    assert not is_system_resource({'path': '/roms/neogeo.sfc', 'label': 'neogeo'}, 'SNES')
    assert is_system_resource({'path': '/roms/support.zip', 'label': 'Example System BIOS'}, system)


def test_mtp_summary_counts_only_games(monkeypatch):
    import mtp_runtime as mtp
    root = mtp.uri('serial', 65537, 'RetroArch')
    monkeypatch.setattr(mtp, 'listing', lambda path: ([{'name': 'playlists', 'folder': True}]
        if path == root else [{'name': SYSTEM + '.lpl', 'folder': False}]))
    monkeypatch.setattr(mtp, 'read', lambda path: json.dumps({'items': resource_items() + [
        {'path': '/roms/s1945.zip', 'label': '1945', 'db_name': SYSTEM + '.lpl'}]}).encode())
    result = mtp.scan(root)
    assert result['playlists'][0]['item_count'] == 1
    assert result['totals']['items'] == 1
