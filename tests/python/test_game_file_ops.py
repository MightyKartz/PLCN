import json
from pathlib import Path

import pytest

import game_file_actions as ops
import game_file_sync as sync


def library(tmp_path, items):
    root = tmp_path / 'RetroArch'
    playlists = root / 'playlists'
    playlists.mkdir(parents=True)
    target = playlists / 'GBA.lpl'
    target.write_text(json.dumps({'items': items}), encoding='utf-8')
    return root, target


def test_rename_copy_and_trash_work_on_any_local_file_and_folder(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    root = tmp_path / 'RetroArch'
    directory = tmp_path / 'Roms'
    directory.mkdir()
    backup_file = directory / 'game.md.bak'
    backup_file.write_bytes(b'backup')
    folder = directory / 'Folder'
    folder.mkdir()
    (folder / 'a.md').write_bytes(b'a')
    path, name, remote = ops.validate_op({'action': 'rename', 'path': str(backup_file), 'root': str(root), 'name': 'renamed.bak'})
    assert ops.apply_rename(path, name, remote)['new_path'] == str(directory / 'renamed.bak')
    path, target, remote = ops.validate_op({'action': 'copy', 'path': str(directory / 'renamed.bak'),
                                          'root': str(root), 'directory': str(directory)})
    assert ops.apply_copy(path, target, remote) == str(directory / 'renamed 副本.bak')
    path, _, remote = ops.validate_op({'action': 'delete', 'path': str(folder), 'root': str(root)})
    trash = Path(ops.apply_delete(path, remote))
    assert not folder.exists() and (trash / 'Folder' / 'a.md').read_bytes() == b'a'


def test_file_ops_reject_device_boundary_and_bad_names(tmp_path):
    root = 'mtp://device/00010001/RetroArch'
    with pytest.raises(ValueError):
        ops.validate_op({'action': 'delete', 'path': 'mtp://other/00010001/Roms/a.md', 'root': root})
    for name in ('', '..', 'a/b', 'a\\b'):
        with pytest.raises(ValueError):
            ops.validate_op({'action': 'rename', 'path': str(tmp_path / 'x'), 'root': str(tmp_path), 'name': name})
    with pytest.raises(ValueError):
        ops.validate_op({'action': 'unknown', 'path': str(tmp_path / 'x'), 'root': str(tmp_path)})


def test_sync_renames_paths_removes_entries_and_reports_unmatched(tmp_path):
    roms = tmp_path / 'Roms' / 'GBA'
    root, target = library(tmp_path, [
        {'path': str(roms / 'a.gba'), 'label': 'A'},
        {'path': str(roms / 'old.gba'), 'label': 'B'},
        {'path': str(roms / 'sub' / 'c.gba'), 'label': 'C'},
        {'path': str(roms / 'pack.zip#inner.gba'), 'label': 'D'},
    ])
    changes = [
        {'action': 'rename', 'path': str(roms / 'old.gba'), 'to': str(roms / 'new.gba'), 'folder': False},
        {'action': 'rename', 'path': str(roms / 'pack.zip'), 'to': str(roms / 'pack2.zip'), 'folder': False},
        {'action': 'delete', 'path': str(roms / 'sub'), 'folder': True},
        {'action': 'delete', 'path': str(roms / 'ghost.gba'), 'folder': False},
    ]
    plan = sync.preview(str(root), changes)
    public = plan['public']
    assert [entry['label'] for entry in public['renamed']] == ['B', 'D']
    assert public['renamed'][1]['new'] == str(roms / 'pack2.zip') + '#inner.gba'
    assert [entry['label'] for entry in public['removed']] == ['C']
    assert public['unmatched'] == [str(roms / 'ghost.gba')]
    sync.apply(str(root), changes, public['signature'])
    items = json.loads(target.read_text(encoding='utf-8'))['items']
    assert [item['label'] for item in items] == ['A', 'B', 'D']
    assert items[1]['path'] == str(roms / 'new.gba')
    assert items[2]['path'] == str(roms / 'pack2.zip') + '#inner.gba'


def test_sync_rejects_a_stale_signature(tmp_path):
    root, target = library(tmp_path, [{'path': str(tmp_path / 'x.gba'), 'label': 'X'}])
    changes = [{'action': 'delete', 'path': str(tmp_path / 'x.gba'), 'folder': False}]
    signature = sync.preview(str(root), changes)['public']['signature']
    target.write_text(json.dumps({'items': []}), encoding='utf-8')
    with pytest.raises(ValueError, match='已变化'):
        sync.apply(str(root), changes, signature)
