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


def test_rename_copy_and_delete_work_on_any_local_file_and_folder(tmp_path, monkeypatch):
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
    deleted = ops.apply_delete(path, remote)
    assert deleted == str(folder) and not folder.exists()


def test_file_ops_reject_device_boundary_and_bad_names(tmp_path):
    root = 'mtp://device/00010001/RetroArch'
    with pytest.raises(ValueError):
        ops.validate_op({'action': 'delete', 'path': 'mtp://other/00010001/Roms/a.md', 'root': root})
    for name in ('', '..', 'a/b', 'a\\b'):
        with pytest.raises(ValueError):
            ops.validate_op({'action': 'rename', 'path': str(tmp_path / 'x'), 'root': str(tmp_path), 'name': name})
    with pytest.raises(ValueError):
        ops.validate_op({'action': 'unknown', 'path': str(tmp_path / 'x'), 'root': str(tmp_path)})


def test_add_copies_files_and_folders_and_skips_existing(tmp_path):
    destination = tmp_path / 'Roms' / 'SFC'
    destination.mkdir(parents=True)
    (destination / 'existing.sfc').write_bytes(b'old')
    source_dir = tmp_path / 'incoming'
    game_folder = source_dir / 'Game'
    (game_folder / 'disc').mkdir(parents=True)
    (game_folder / 'disc' / 'game.cue').write_bytes(b'cue')
    (game_folder / 'disc' / 'game.bin').write_bytes(b'bin')
    rom = source_dir / 'new.sfc'
    rom.write_bytes(b'new')
    clash = source_dir / 'existing.sfc'
    clash.write_bytes(b'clash')
    sources, directory, remote, overwrite = ops.validate_add({
        'action': 'add', 'sources': [str(rom), str(game_folder), str(clash)],
        'directory': str(destination), 'root': str(tmp_path)})
    assert overwrite is False
    result = ops.apply_add(sources, directory, remote, overwrite)
    assert result['copied'] == ['new.sfc', 'Game']
    assert result['skipped'] == ['existing.sfc']
    assert result['failed'] == [] and result['remaining'] == []
    assert (destination / 'new.sfc').read_bytes() == b'new'
    assert (destination / 'Game' / 'disc' / 'game.cue').read_bytes() == b'cue'
    assert (destination / 'existing.sfc').read_bytes() == b'old'


def test_add_overwrite_stages_then_replaces(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    destination = tmp_path / 'Roms'
    destination.mkdir()
    (destination / 'game.sfc').write_bytes(b'old version')
    folder = destination / 'Game'
    folder.mkdir()
    (folder / 'a.bin').write_bytes(b'old bin')
    source_dir = tmp_path / 'incoming'
    source_dir.mkdir()
    (source_dir / 'game.sfc').write_bytes(b'new version')
    new_folder = source_dir / 'Game'
    new_folder.mkdir()
    (new_folder / 'b.bin').write_bytes(b'new bin')
    _, _, _, overwrite = ops.validate_add({
        'action': 'add', 'sources': [str(source_dir / 'game.sfc'), str(new_folder)],
        'directory': str(destination), 'root': str(tmp_path), 'overwrite': True})
    assert overwrite is True
    result = ops.apply_add([str(source_dir / 'game.sfc'), str(new_folder)], str(destination), False, True)
    assert result['replaced'] == ['game.sfc', 'Game']
    assert result['skipped'] == [] and result['failed'] == []
    assert (destination / 'game.sfc').read_bytes() == b'new version'
    assert (destination / 'Game' / 'b.bin').read_bytes() == b'new bin'
    assert not (destination / 'Game' / 'a.bin').exists()
    assert not (tmp_path / 'home' / 'file-trash').exists()


def test_add_reports_failure_and_remaining_and_cleans_partial(tmp_path):
    destination = tmp_path / 'dest'
    destination.mkdir()
    folder = tmp_path / 'src' / 'big'
    folder.mkdir(parents=True)
    (folder / 'a.bin').write_bytes(b'a')
    (folder / 'b.bin').write_bytes(b'b')
    later = tmp_path / 'src' / 'later.sfc'
    later.write_bytes(b'later')
    sources = [str(folder), str(later)]
    calls = iter([None, RuntimeError('disk full')])
    real_copy2 = ops.shutil.copy2

    def fake_copy2(*args, **kwargs):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return real_copy2(*args, **kwargs)

    ops.shutil.copy2 = fake_copy2
    try:
        result = ops.apply_add(sources, str(destination), False)
    finally:
        ops.shutil.copy2 = real_copy2
    assert result['failed'] == [{'name': 'big', 'error': 'disk full'}]
    assert result['remaining'] == ['later.sfc']
    assert result['copied'] == []
    assert not (destination / 'big').exists()


def test_validate_add_boundaries(tmp_path):
    with pytest.raises(ValueError):
        ops.validate_add({'action': 'add', 'sources': ['/nonexistent-file'], 'directory': str(tmp_path), 'root': ''})
    with pytest.raises(ValueError):
        ops.validate_add({'action': 'add', 'sources': [str(tmp_path)], 'directory': 'mtp://dev/0001/Roms', 'root': 'mtp://other/0001/Lib'})
    with pytest.raises(ValueError):
        ops.validate_add({'action': 'add', 'sources': ['mtp://dev/0001/a'], 'directory': str(tmp_path), 'root': ''})


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


def test_replace_publish_failure_preserves_original_file(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    destination = tmp_path / 'Roms'
    destination.mkdir()
    original = destination / 'game.sfc'
    original.write_bytes(b'old version')
    source = tmp_path / 'incoming'
    source.mkdir()
    (source / 'game.sfc').write_bytes(b'new version')
    real_replace = ops.os.replace

    def fail_replace(staged, target):
        raise OSError('publish failed')
    monkeypatch.setattr(ops.os, 'replace', fail_replace)
    result = ops.apply_add([str(source / 'game.sfc')], str(destination), False, overwrite=True)
    monkeypatch.setattr(ops.os, 'replace', real_replace)
    assert result['failed'] and 'publish failed' in result['failed'][0]['error']
    assert result['replaced'] == []
    assert original.read_bytes() == b'old version'
    assert not list(destination.glob('*.plcn-*'))


def test_replace_folder_publish_failure_rolls_back_original(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    destination = tmp_path / 'Roms'
    destination.mkdir()
    folder = destination / 'Game'
    folder.mkdir()
    (folder / 'a.bin').write_bytes(b'old bin')
    source = tmp_path / 'incoming'
    source.mkdir()
    (source / 'Game').mkdir()
    (source / 'Game' / 'b.bin').write_bytes(b'new bin')
    real_rename_into = ops._rename_into

    def fail_publish(target, staged, remote):
        raise OSError('device refused rename')
    monkeypatch.setattr(ops, '_rename_into', fail_publish)
    result = ops.apply_add([str(source / 'Game')], str(destination), False, overwrite=True)
    monkeypatch.setattr(ops, '_rename_into', real_rename_into)
    assert result['failed'] and 'refused' in result['failed'][0]['error']
    assert (folder / 'a.bin').read_bytes() == b'old bin'
    assert not list(destination.glob('*.plcn-*'))


def test_replace_failure_reports_recoverable_paths_when_rollback_fails(tmp_path, monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(tmp_path / 'home'))
    destination = tmp_path / 'Roms'
    destination.mkdir()
    folder = destination / 'Game'
    folder.mkdir()
    (folder / 'a.bin').write_bytes(b'old bin')
    source = tmp_path / 'incoming'
    source.mkdir()
    (source / 'Game').mkdir()
    (source / 'Game' / 'b.bin').write_bytes(b'new bin')
    monkeypatch.setattr(ops, '_rename_into', lambda *a: (_ for _ in ()).throw(OSError('publish failed')))
    real_rename = Path.rename
    parked = [True]

    def fail_rollback(self, target):
        if parked[0]:
            parked[0] = False
            return real_rename(self, target)
        raise OSError('rollback failed')
    monkeypatch.setattr(Path, 'rename', fail_rollback)
    result = ops.apply_add([str(source / 'Game')], str(destination), False, overwrite=True)
    error = result['failed'][0]['error']
    assert '.plcn-old-' in error and '.plcn-replace-' in error


def test_local_delete_and_copy_respect_cancellation(tmp_path):
    folder = tmp_path / 'Game'
    folder.mkdir()
    (folder / 'a.bin').write_bytes(b'a')
    (folder / 'b.bin').write_bytes(b'b')
    from task_control import TaskCancelled

    def cancelled():
        raise TaskCancelled('cancelled')
    with pytest.raises(TaskCancelled):
        ops.apply_delete(str(folder), False, cancelled=cancelled)
    assert (folder / 'a.bin').exists() and (folder / 'b.bin').exists()

    target = tmp_path / 'dest'
    target.mkdir()
    with pytest.raises(TaskCancelled):
        ops.apply_copy(str(folder), str(target), False, cancelled=cancelled)
    assert not (target / 'Game').exists()


def test_local_delete_can_stop_mid_folder(tmp_path):
    folder = tmp_path / 'Game'
    folder.mkdir()
    for name in ('a.bin', 'b.bin', 'c.bin'):
        (folder / name).write_bytes(name.encode())
    from task_control import TaskCancelled
    calls = [0]

    def cancelled():
        calls[0] += 1
        if calls[0] > 2:
            raise TaskCancelled('cancelled')
    with pytest.raises(TaskCancelled):
        ops.apply_delete(str(folder), False, cancelled=cancelled)
    remaining = list(folder.glob('*.bin'))
    assert 0 < len(remaining) < 3 and folder.exists()


def test_copy_paste_uses_host_platform_source_name(tmp_path):
    source = tmp_path / 'src'
    source.mkdir()
    (source / 'game.nes').write_bytes(b'rom')
    target = tmp_path / 'dest'
    target.mkdir()
    copied = ops.apply_copy(str(source / 'game.nes'), str(target), False)
    assert copied == str(target / 'game.nes')
    assert not list(source.glob('*副本*'))


def test_mtp_replace_moves_original_aside_then_cleans(tmp_path, monkeypatch):
    import mtp_runtime as mtp
    root_uri = mtp.uri('dev', 0x10001, 'Roms')
    files = {mtp.join(root_uri, 'game.sfc'): b'old version'}

    def entry(uri):
        return {'id': 1, 'folder': False, 'size': len(files[uri])}
    monkeypatch.setattr(mtp, 'stat_file', lambda path: entry(path) if path in files else None)
    monkeypatch.setattr(mtp, 'listing', lambda path: [])
    uploads = {}

    def upload(target, source, expected, stage, cancelled=lambda: None):
        uploads[target] = Path(source).read_bytes()
        files[target] = uploads[target]
    monkeypatch.setattr(mtp, 'upload_file', upload)
    monkeypatch.setattr(mtp, 'rename_object', lambda path, name: (
        files.__setitem__(path.rsplit('/', 1)[0] + '/' + name, files.pop(path)),
        path.rsplit('/', 1)[0] + '/' + name)[1])
    monkeypatch.setattr(mtp, 'delete_object', lambda path: files.pop(path, None))

    source = tmp_path / 'game.sfc'
    source.write_bytes(b'new version')
    result = ops.apply_add([str(source)], root_uri, True, overwrite=True)
    assert result['replaced'] == ['game.sfc'] and not result['leftovers']
    assert files[mtp.join(root_uri, 'game.sfc')] == b'new version'
    assert not any('.plcn-' in path for path in files)


def test_mtp_replace_reports_leftover_when_cleanup_fails(tmp_path, monkeypatch):
    import mtp_runtime as mtp
    root_uri = mtp.uri('dev', 0x10001, 'Roms')
    files = {mtp.join(root_uri, 'game.sfc'): b'old version'}
    monkeypatch.setattr(mtp, 'stat_file', lambda path: {'id': 1, 'folder': False, 'size': 1} if path in files else None)
    monkeypatch.setattr(mtp, 'listing', lambda path: [])
    monkeypatch.setattr(mtp, 'upload_file', lambda target, source, expected, stage, cancelled=lambda: None: files.__setitem__(target, Path(source).read_bytes()))
    monkeypatch.setattr(mtp, 'rename_object', lambda path, name: (
        files.__setitem__(path.rsplit('/', 1)[0] + '/' + name, files.pop(path)),
        path.rsplit('/', 1)[0] + '/' + name)[1])
    monkeypatch.setattr(mtp, 'delete_object', lambda path: (_ for _ in ()).throw(RuntimeError('delete refused')))

    source = tmp_path / 'game.sfc'
    source.write_bytes(b'new version')
    result = ops.apply_add([str(source)], root_uri, True, overwrite=True)
    assert result['replaced'] == ['game.sfc']
    assert result['leftovers'] and '.plcn-old-' in result['leftovers'][0]['path']
    assert files[mtp.join(root_uri, 'game.sfc')] == b'new version'
    assert files[result['leftovers'][0]['path']] == b'old version'


def test_mtp_copy_decodes_percent_encoded_source_name(tmp_path, monkeypatch):
    import mtp_runtime as mtp
    source_uri = mtp.uri('dev', 0x10001, 'Roms/仙剑 1.cue')
    dest_uri = mtp.uri('dev', 0x10001, 'Target')
    files = {source_uri: b'cue content'}
    monkeypatch.setattr(mtp, 'stat_file', lambda path: {'id': 1, 'folder': False, 'size': 1} if path in files else None)

    def download(path, target, cancelled=lambda: None):
        Path(target).write_bytes(files[path])
    monkeypatch.setattr(mtp, 'download_file', download)
    written = {}
    monkeypatch.setattr(mtp, 'upload_file', lambda target, source, expected, stage, cancelled=lambda: None: (
        written.__setitem__(target, Path(source).read_bytes()), files.__setitem__(target, Path(source).read_bytes()))[0])

    copied = ops.apply_copy(source_uri, dest_uri, True)
    expected_target = mtp.join(dest_uri, '仙剑 1.cue')
    assert copied == expected_target
    assert mtp.parse(copied)[2][-1] == '仙剑 1.cue'
    assert written == {expected_target: b'cue content'}


def test_sync_chains_sequential_renames_and_renamed_then_deleted(tmp_path):
    roms = tmp_path / 'Roms' / 'NES'
    roms.mkdir(parents=True)
    root, target = library(tmp_path, [
        {'path': str(roms / 'A.nes'), 'label': 'chain'},
        {'path': str(roms / 'gone.nes'), 'label': 'renamed-then-deleted'},
        {'path': str(roms / 'pack.zip#inner.nes'), 'label': 'archive'},
        {'path': str(roms / 'keep.nes'), 'label': 'untouched'},
    ])
    changes = [
        {'action': 'rename', 'path': str(roms / 'A.nes'), 'to': str(roms / 'B.nes'), 'folder': False},
        {'action': 'rename', 'path': str(roms / 'B.nes'), 'to': str(roms / 'C.nes'), 'folder': False},
        {'action': 'rename', 'path': str(roms / 'gone.nes'), 'to': str(roms / 'gone2.nes'), 'folder': False},
        {'action': 'delete', 'path': str(roms / 'gone2.nes'), 'folder': False},
        {'action': 'rename', 'path': str(roms / 'pack.zip'), 'to': str(roms / 'pack2.zip'), 'folder': False},
    ]
    plan = sync.preview(str(root), changes)
    public = plan['public']
    renamed = {entry['label']: entry['new'] for entry in public['renamed']}
    assert renamed['chain'] == str(roms / 'C.nes')
    assert renamed['archive'] == str(roms / 'pack2.zip') + '#inner.nes'
    assert [entry['label'] for entry in public['removed']] == ['renamed-then-deleted']
    sync.apply(str(root), changes, public['signature'])
    items = {item['label']: item['path'] for item in json.loads(target.read_text(encoding='utf-8'))['items']}
    assert items['chain'] == str(roms / 'C.nes')
    assert 'renamed-then-deleted' not in items
    assert items['archive'] == str(roms / 'pack2.zip') + '#inner.nes'
    assert items['untouched'] == str(roms / 'keep.nes')


def test_sync_dir_rename_then_file_rename_inside_chains(tmp_path):
    roms = tmp_path / 'Roms'
    folder = roms / 'Disc'
    folder.mkdir(parents=True)
    root, target = library(tmp_path, [{'path': str(folder / 'game.cue'), 'label': 'cue'}])
    changes = [
        {'action': 'rename', 'path': str(folder), 'to': str(roms / 'Disc Renamed'), 'folder': True},
        {'action': 'rename', 'path': str(roms / 'Disc Renamed' / 'game.cue'), 'to': str(roms / 'Disc Renamed' / 'game2.cue'), 'folder': False},
    ]
    public = sync.preview(str(root), changes)['public']
    assert public['renamed'][0]['new'] == str(roms / 'Disc Renamed' / 'game2.cue')


def test_sync_broken_playlist_does_not_block_valid_ones(tmp_path):
    roms = tmp_path / 'Roms'
    roms.mkdir()
    root, target = library(tmp_path, [{'path': str(roms / 'a.nes'), 'label': 'A'}])
    broken = root / 'playlists' / 'Broken.lpl'
    broken.write_text('{invalid json', encoding='utf-8')
    broken_bytes = broken.read_bytes()
    changes = [{'action': 'rename', 'path': str(roms / 'a.nes'), 'to': str(roms / 'b.nes'), 'folder': False}]
    plan = sync.preview(str(root), changes)
    public = plan['public']
    assert [entry['label'] for entry in public['renamed']] == ['A']
    assert [entry['playlist'] for entry in public['failed']] == ['Broken.lpl']
    sync.apply(str(root), changes, public['signature'])
    assert json.loads(target.read_text(encoding='utf-8'))['items'][0]['path'] == str(roms / 'b.nes')
    assert broken.read_bytes() == broken_bytes


def test_sync_reports_all_playlists_broken(tmp_path):
    root = tmp_path / 'RetroArch'
    (root / 'playlists').mkdir(parents=True)
    (root / 'playlists' / 'Broken.lpl').write_text('{bad', encoding='utf-8')
    plan = sync.preview(str(root), [{'action': 'rename', 'path': '/x.nes', 'to': '/y.nes', 'folder': False}])
    public = plan['public']
    assert public['failed'] and not public['renamed'] and not plan['writes']
