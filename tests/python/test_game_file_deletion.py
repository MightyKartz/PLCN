import json

import pytest

from game_file_deletion import apply, preview, validate


def write_list(path, *items):
    path.write_text(json.dumps({'items': items, 'default_core_name': 'Beetle Saturn'}))


def test_delete_syncs_two_lists_preserves_shared_track_and_saves(tmp_path):
    root = tmp_path / 'RetroArch'
    directory = root / 'playlists'
    directory.mkdir(parents=True)
    roms = root / 'roms'
    roms.mkdir()
    cue = roms / 'Game.cue'
    other = roms / 'Other.cue'
    shared = roms / 'shared.bin'
    unique = roms / 'unique.bin'
    shared.write_bytes(b'shared')
    unique.write_bytes(b'unique')
    cue.write_text('FILE "shared.bin" BINARY\nFILE "unique.bin" BINARY\n')
    other.write_text('FILE "shared.bin" BINARY\n')
    save = roms / 'Game.srm'
    save.write_bytes(b'save')
    system = 'Sega - Saturn'
    first, second = directory / 'Saturn.lpl', directory / 'Custom.lpl'
    entry = {'path': str(cue), 'label': 'Game', 'db_name': system + '.lpl'}
    survivor = {'path': str(other), 'label': 'Other', 'db_name': system + '.lpl'}
    write_list(first, entry, survivor)
    write_list(second, entry)
    covers = root / 'thumbnails' / system / 'Named_Boxarts'
    covers.mkdir(parents=True)
    cover = covers / 'Game.png'
    cover.write_bytes(b'cover')
    plan = preview(str(cue), str(root))
    assert set(plan['public']['files']) == {str(cue), str(unique)}
    assert plan['public']['shared'] == [str(shared)]
    assert plan['public']['covers'] == [str(cover)]
    result = apply(str(cue), str(root), '', plan['signature'], False, lambda *_: None, lambda: None)
    assert set(result['playlists']) == {str(first), str(second)}
    assert json.loads(first.read_text())['items'] == [survivor]
    assert json.loads(second.read_text()) == {'items': [], 'default_core_name': 'Beetle Saturn'}
    assert not cue.exists() and not unique.exists()
    assert all(path.exists() for path in (other, shared, save, cover))
    cue.write_text('FILE "Game.srm" BINARY\n')
    with pytest.raises(ValueError, match='不是可确认的光盘或音轨'):
        preview(str(cue), str(root))
    assert save.read_bytes() == b'save'


def test_cover_cleanup_rechecks_surviving_entries_and_requires_opt_in(tmp_path):
    library = tmp_path / 'RetroArch'
    playlists = library / 'playlists'
    playlists.mkdir(parents=True)
    target = tmp_path / 'Game.gba'
    other = tmp_path / 'Other.gba'
    target.touch()
    other.touch()
    system = 'Nintendo - Game Boy Advance'
    playlist = playlists / (system + '.lpl')
    item = {'path': str(target), 'label': 'Same'}
    survivor = {'path': str(other), 'label': 'Same'}
    write_list(playlist, item)
    cover_dir = library / 'thumbnails' / system / 'Named_Boxarts'
    cover_dir.mkdir(parents=True)
    cover = cover_dir / 'Same.png'
    cover.write_bytes(b'cover')
    path, root = validate({'path': str(target), 'root': str(library)})
    plan = preview(path, root)
    assert plan['public']['covers'] == [str(cover)]
    write_list(playlist, item, survivor)
    with pytest.raises(ValueError, match='变化'):
        apply(path, root, '', plan['signature'], True, lambda *_: None, lambda: None)
    assert target.exists() and cover.exists()
    assert preview(path, root)['public']['covers'] == []
    write_list(playlist, item)
    plan = preview(path, root)
    apply(path, root, '', plan['signature'], True, lambda *_: None, lambda: None)
    assert not target.exists() and not cover.exists() and other.exists()
