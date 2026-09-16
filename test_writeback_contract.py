import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / 'src'))
import plcn
from playlist_manager import PlaylistManager
from manual_overrides import find_override, normalize_crc
from safe_io import file_lock


def playlist(tmp_path):
    path = tmp_path / 'list.lpl'
    items = [{'path': '/a/game-us.zip', 'label': 'Same', 'crc32': '11111111|crc'},
             {'path': '/b/game-jp.zip', 'label': 'Same', 'crc32': '22222222|crc'}]
    path.write_text(json.dumps({'items': items, 'custom': 'preserved'}), encoding='utf-8')
    return path, items


def test_rename_does_not_delete_unselected_same_label_rom(tmp_path):
    path, items = playlist(tmp_path)
    change = {'index': 1, 'path': items[1]['path'], 'original_item_label': 'Same', 'new_label': '日版'}
    plcn.apply_changes(str(path), [change], str(tmp_path), download_thumbnails=False)
    result = json.loads(path.read_text(encoding='utf-8'))
    assert result['items'][0] == items[0]
    assert len(result['items']) == 2
    assert result['items'][1]['label'] == '日版'
    assert result['custom'] == 'preserved'


def test_review_requires_explicit_confirmation(tmp_path):
    path, items = playlist(tmp_path)
    change = {'index': 0, 'path': items[0]['path'], 'new_label': '中文', 'needs_review': True}
    result = plcn.apply_changes(str(path), [change], str(tmp_path), download_thumbnails=False)
    assert result['apply']['skipped'][0]['reason'] == 'review_required'
    assert json.loads(path.read_text())['items'] == items
    change['review_confirmed'] = True
    result = plcn.apply_changes(str(path), [change], str(tmp_path), download_thumbnails=False)
    assert len(result['apply']['applied']) == 1


def test_atomic_save_failure_preserves_original(tmp_path, monkeypatch):
    path, _ = playlist(tmp_path)
    old = path.read_bytes()
    manager = PlaylistManager(path)
    manager.items[0]['label'] = 'changed'
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr('safe_io.os.replace', fail)
    with pytest.raises(OSError):
        manager.save()
    assert path.read_bytes() == old
    assert not list(tmp_path.glob('*.tmp'))


def test_save_rejects_external_changes(tmp_path):
    path, _ = playlist(tmp_path)
    manager = PlaylistManager(path)
    external = b'{"items":[],"changed_by":"RetroArch"}'
    path.write_bytes(external)
    with pytest.raises(RuntimeError, match='重新预览'):
        manager.save()
    assert path.read_bytes() == external


def test_second_writer_is_rejected_and_lock_released(tmp_path):
    path, _ = playlist(tmp_path)
    with file_lock(path):
        with pytest.raises(RuntimeError, match='正在被'):
            plcn.apply_changes(str(path), [], str(tmp_path), download_thumbnails=False)
    with file_lock(path):
        pass


def test_crc_conflict_cannot_fall_back_to_filename():
    entry = {'system': 'NES', 'rom_filename': 'game.zip', 'crc32': '11111111'}
    assert find_override([entry], 'NES', {'path': r'C:\roms\game.zip', 'crc32': '22222222'}) is None
    assert find_override([entry], 'NES', {'path': r'C:\roms\game.zip', 'crc32': 'DETECT'}) == entry
    assert normalize_crc('oops-1234abcd') == ''


def test_crc_change_invalidates_proposal():
    assert not plcn.proposal_matches_item({'crc32': '11111111'}, {'crc32': '22222222'})
