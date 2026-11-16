"""Local identity migration preserves source data and never infers title equality."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import uuid

import pytest

import library_model as model
from playlist_browser import read_playlist


@pytest.fixture
def identity_home(tmp_path, monkeypatch):
    home = tmp_path / 'metadata'
    monkeypatch.setattr(model.app_paths, 'user_data_dir', lambda: home)
    return home


def ids(document):
    return {item['index']: (item['game_id'], item['content_id'], item['disc_id']) for item in document['entries']}


def test_labels_order_and_core_changes_preserve_ids_without_touching_playlist(identity_home, tmp_path):
    playlist = tmp_path / 'playlists' / 'SS.lpl'
    playlist.parent.mkdir()
    items = [{'path': '/Roms/SS/GulliverBoy Disc1.chd', 'label': '旧名', 'core_path': 'custom.so'},
             {'path': '/Roms/SS/GulliverBoy Disc2.chd', 'label': '旧名'}]
    playlist.write_text(json.dumps({'items': items}, ensure_ascii=False), encoding='utf-8')
    before = playlist.read_bytes()
    first = read_playlist(str(playlist), 'Sega - Saturn')
    assert playlist.read_bytes() == before
    original = ids(first['library_model'])
    for values in original.values():
        for value in values:
            assert str(uuid.UUID(value)) == value
    items[0]['label'] = '空想科学世界 (Disc 1)'
    items[0]['core_path'] = 'another.so'
    playlist.write_text(json.dumps({'items': list(reversed(items))}, ensure_ascii=False), encoding='utf-8')
    before = playlist.read_bytes()
    second = read_playlist(str(playlist), 'Sega - Saturn')
    assert ids(second['library_model']) == {0: original[1], 1: original[0]}
    assert second['items'][1]['game_id'] == original[0][0]
    assert second['library_model']['entries'][1]['core']['path'] == 'another.so'
    assert playlist.read_bytes() == before
    assert not list(tmp_path.rglob('*.bak*'))


def test_equal_names_never_merge_files_or_discs(identity_home):
    items = [{'path': '/Roms/Game (Disc 1).chd', 'label': '相同中文名'},
             {'path': '/Roms/Game (Disc 2).chd', 'label': '相同中文名'}]
    original = copy.deepcopy(items)
    result = model.build_library_model('mtp://handheld/00010001/RetroArch/playlists/SS.lpl', 'Sega - Saturn', items)
    assert len(result['games']) == len(result['contents']) == len(result['discs']) == 2
    assert [disc['number'] for disc in result['discs']] == [1, 2]
    assert all(disc['number_source'] == 'filename' for disc in result['discs'])
    assert items == original


def test_devices_and_platforms_do_not_share_game_ids(identity_home):
    items = [{'path': '/storage/card/Game.chd', 'label': 'Game'}]
    first = model.build_library_model('mtp://one/00010001/playlists/SS.lpl', 'Sega - Saturn', items)
    other = model.build_library_model('mtp://two/00010001/playlists/SS.lpl', 'Sega - Saturn', items)
    platform = model.build_library_model('mtp://one/00010001/playlists/PS1.lpl', 'Sony - PlayStation', items)
    assert first['games'][0]['id'] != other['games'][0]['id'] != platform['games'][0]['id']
    assert first['contents'][0]['id'] == platform['contents'][0]['id']
    assert first['contents'][0]['id'] != other['contents'][0]['id']


def test_model_does_not_invent_discs_from_labels_or_m3u_or_arcade_chd(identity_home):
    entries = [{'path': '/Roms/plain.chd', 'label': 'Disc 2'}, {'path': '/Roms/game.m3u', 'label': 'Game'},
               {'path': '/Roms/Track01.bin', 'label': 'Track'}, {'path': '', 'label': 'Missing'}]
    result = model.build_library_model('adb://device/playlists/SS.lpl', 'Sega - Saturn', entries)
    assert len(result['discs']) == 1
    assert result['discs'][0]['number'] is None
    assert result['discs'][0]['number_source'] == 'unknown'
    assert result['entries'][-1]['game_id'] is None
    arcade = model.build_library_model('adb://device/playlists/MAME.lpl', 'MAME', entries[:1])
    assert arcade['discs'] == []


def test_repeated_reads_reuse_index_without_rewriting_it(identity_home, monkeypatch):
    items = [{'path': '/Roms/game.zip', 'label': 'Name'}]
    first = model.build_library_model('/library/playlists/NES.lpl', 'NES', items)
    monkeypatch.setattr(model, 'atomic_write_json', lambda *args: pytest.fail('No new identity requires a write'))
    assert model.build_library_model('/library/playlists/NES.lpl', 'NES', items) == first


def test_parallel_reads_allocate_one_identity(identity_home):
    def read(_):
        return model.build_library_model('mtp://device/00010001/playlists/SS.lpl', 'Sega - Saturn',
                                         [{'path': '/Roms/Game.chd', 'label': '游戏'}])
    with ThreadPoolExecutor(max_workers=6) as pool:
        documents = list(pool.map(read, range(12)))
    assert all(document == documents[0] for document in documents)
    index = json.loads((identity_home / 'library-identities.json').read_text(encoding='utf-8'))
    assert len(index['content_ids']) == len(index['game_ids']) == len(index['disc_ids']) == 1


@pytest.mark.parametrize('content', ['{broken', '{"version":2}',
    '{"version":1,"content_ids":{"bad":"not-a-uuid"},"game_ids":{},"disc_ids":{}}'])
def test_corrupt_index_reports_error_without_replacing_ids(identity_home, content):
    identity_home.mkdir()
    index = identity_home / 'library-identities.json'
    index.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='标识'):
        model.build_library_model('/library/SS.lpl', 'Sega - Saturn', [{'path': '/Game.chd'}])
    assert index.read_text(encoding='utf-8') == content
