import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import game_management as games
import m3u_transaction as tx
import mtp_runtime as mtp

SYSTEM = 'Nintendo - Game Boy Advance'


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('PLCN_HOME', str(tmp_path / 'home'))
    root = tmp_path / 'RetroArch'; (root / 'playlists').mkdir(parents=True)
    source = tmp_path / 'source'; source.mkdir()
    destination = tmp_path / 'card' / 'GBA'
    playlist = root / 'playlists' / (SYSTEM + '.lpl')
    old = {'version':'1.5', 'custom':'keep', 'default_core_path':'special-core', 'items':[
        {'path':'/old.gba', 'label':'Custom name', 'core_path':'override', 'custom':42}]}
    playlist.write_text(json.dumps(old))
    config = games.validate_import({'root':str(root), 'destination':str(destination), 'system':SYSTEM, 'sources':[str(source)]})
    return root, source, destination, playlist, old, config


def test_import_copies_and_preserves_metadata_with_restore(library):
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    before = playlist.read_bytes()
    plan = games.import_preview(config)
    assert playlist.read_bytes() == before and not target.exists()
    assert plan['can_apply'] and plan['required_bytes'] == 4
    result = games.apply(plan)
    assert result['status'] == 'applied' and result['added'] == 1
    assert (source / 'demo.gba').read_bytes() == (target / 'demo.gba').read_bytes() == b'game'
    updated = json.loads(playlist.read_text())
    assert updated['items'][0] == old['items'][0]
    assert updated['default_core_path'] == 'special-core' and updated['custom'] == 'keep'
    assert tx.run(result['operation_id'], restore=True)['status'] == 'restored'
    assert playlist.read_bytes() == before and (target / 'demo.gba').exists()
    assert not games.import_preview(config)['copies'][0]['state'] == 'new'


def test_duplicate_files_reused_conflicts_blocked(library):
    root, source, target, playlist, old, config = library
    target.mkdir(parents=True)
    (source / 'same.gba').write_bytes(b'game'); (target / 'same.gba').write_bytes(b'game')
    plan = games.import_preview(config)
    assert plan['duplicates'] == 1 and plan['required_bytes'] == 0 and plan['can_apply']
    games.apply(plan)
    again = games.import_preview(config)
    assert not again['can_apply'] and not again['added']
    (source / 'same.gba').write_bytes(b'changed')
    conflict = games.import_preview(config)
    assert not conflict['can_apply'] and conflict['conflicts'] == ['same.gba']
    assert (target / 'same.gba').read_bytes() == b'game'


def test_stale_preview_does_not_copy(library):
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    plan = games.import_preview(config)
    playlist.write_text('{"items":[]}')
    with pytest.raises(ValueError, match='列表已变化'): games.apply(plan)
    assert not target.exists()


def test_changed_source_does_not_copy(library):
    root, source, target, playlist, old, config = library
    rom = source / 'demo.gba'; rom.write_bytes(b'game')
    before = playlist.read_bytes(); plan = games.import_preview(config); rom.write_bytes(b'change')
    with pytest.raises(ValueError, match='来源已变化'): games.apply(plan)
    assert playlist.read_bytes() == before and not target.exists()


def test_low_space_prevents_apply(library, monkeypatch):
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    monkeypatch.setattr(games.shutil, 'disk_usage', lambda p: SimpleNamespace(free=1))
    assert not games.import_preview(config)['can_apply']


def test_bios_copied_as_resource_never_playlist_entry(library):
    root, source, target, playlist, old, config = library
    config['system'] = 'FBNeo - Arcade Games'
    (source / 'neogeo.zip').write_bytes(b'bios'); (source / 'mslug.zip').write_bytes(b'game')
    plan = games.import_preview(config)
    assert plan['resources'] == 1
    assert [item['label'] for item in plan['added']] == ['mslug']
    games.apply(plan)
    assert (target / 'neogeo.zip').exists()


def test_cue_and_m3u_companions_imported_without_duplicate_entries(library):
    root, source, target, playlist, old, config = library
    config['system'] = 'Sony - PlayStation'
    (source / 'Game.m3u').write_text('disc/Game.cue\n')
    (source / 'disc').mkdir()
    (source / 'disc/Game.cue').write_text('FILE "track.bin" BINARY\n TRACK 01 MODE1/2352\n')
    (source / 'disc/track.bin').write_bytes(b'track')
    (source / 'notes.txt').write_text('do not copy')
    plan = games.import_preview(config)
    assert [item['label'] for item in plan['added']] == ['Game']
    assert len(plan['copies']) == 3
    games.apply(plan)
    assert (target / 'disc/track.bin').read_bytes() == b'track'
    assert not (target / 'notes.txt').exists()


def test_missing_and_escaping_disc_dependencies_rejected(library):
    root, source, target, playlist, old, config = library
    config['system'] = 'Sony - PlayStation'
    cue = source / 'Game.cue'; cue.write_text('FILE "missing.bin" BINARY\n')
    with pytest.raises(ValueError, match='来源不存在'): games.import_preview(config)
    cue.write_text('FILE "../outside.bin" BINARY\n')
    with pytest.raises(ValueError, match='引用必须'): games.import_preview(config)


def test_source_name_collision_rejected(library, tmp_path):
    root, source, target, playlist, old, config = library
    other = tmp_path / 'other'; other.mkdir()
    (source / 'demo.gba').write_bytes(b'one'); (other / 'demo.gba').write_bytes(b'two')
    config['sources'].append(str(other))
    with pytest.raises(ValueError, match='同名目标'): games.import_preview(config)


def test_removal_preserves_files_fields_and_is_recoverable(library):
    root, source, target, playlist, old, config = library
    rom = source / 'demo.gba'; rom.write_bytes(b'game')
    artwork = source / 'demo.png'; artwork.write_bytes(b'artwork')
    save = source / 'demo.srm'; save.write_bytes(b'save')
    before = playlist.read_bytes()
    plan = games.remove_preview({'playlist':str(playlist), 'indices':[0], 'expected':mtp.digest(before)})
    assert playlist.read_bytes() == before
    result = games.apply(plan)
    assert json.loads(playlist.read_text()) == {**old, 'items':[]}
    assert result['removed'] == 1
    assert rom.read_bytes() == b'game' and artwork.read_bytes() == b'artwork' and save.read_bytes() == b'save'
    tx.run(result['operation_id'], restore=True)
    assert playlist.read_bytes() == before


@pytest.mark.parametrize('indices', [[], [True], [-1], [1], [0,0], ['0']])
def test_invalid_removal_selection_rejected(library, indices):
    root, source, target, playlist, old, config = library
    with pytest.raises(ValueError): games.remove_preview({'playlist':str(playlist), 'indices':indices, 'expected':mtp.digest(playlist.read_bytes())})


def test_removal_read_and_apply_hash_guard(library):
    root, source, target, playlist, old, config = library
    with pytest.raises(ValueError, match='列表已变化'):
        games.remove_preview({'playlist':str(playlist), 'indices':[0], 'expected':'stale'})
    plan = games.remove_preview({'playlist':str(playlist), 'indices':[0], 'expected':mtp.digest(playlist.read_bytes())})
    playlist.write_text('{"items":[]}')
    with pytest.raises(ValueError, match='列表已变化'): games.apply(plan)


def test_mtp_import_keeps_android_paths_and_uses_verified_upload(library, monkeypatch):
    from contextlib import contextmanager
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    config.update(root='mtp://serial/00010001/RetroArch', destination='mtp://serial/00020001/Roms/GBA', android_directory='/storage/CARD/Roms/GBA', playlist='mtp://serial/00010001/RetroArch/playlists/GBA.lpl')
    config = games.validate_import({**config, 'playlist_name':'GBA.lpl'})
    calls = []
    real_read, real_digest = games.scan.read, games.chd_io.digest
    monkeypatch.setattr(games.scan, 'read', lambda p: None if mtp.is_mtp(p) else real_read(p))
    monkeypatch.setattr(games.chd_io, 'digest', lambda p, c=lambda:None: None if mtp.is_mtp(p) else real_digest(p, c))
    monkeypatch.setattr(mtp, 'free_bytes', lambda p: 100)
    @contextmanager
    def session(p): yield ('handle', 2, ['Roms','GBA','demo.gba'])
    monkeypatch.setattr(mtp, 'session', session)
    monkeypatch.setattr(mtp, 'resolve', lambda *a, **k: calls.append(('mkdir', a, k)))
    monkeypatch.setattr(mtp, 'upload_file', lambda *a: calls.append(('upload', a)))
    monkeypatch.setattr(tx, 'start', lambda p: {'status':'applied'})
    plan = games.import_preview(config)
    assert plan['added'][0]['path'] == '/storage/CARD/Roms/GBA/demo.gba'
    result = games.apply(plan)
    assert result['added'] == 1 and calls[-1][0] == 'upload'
    assert calls[-1][1][0] == 'mtp://serial/00020001/Roms/GBA/demo.gba'


def test_cancelled_copy_keeps_playlist_untouched(library):
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    plan = games.import_preview(config); before = playlist.read_bytes()
    def cancelled(): raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'): games.apply(plan, cancelled=cancelled)
    assert playlist.read_bytes() == before


def test_removal_includes_other_discs_in_visible_game(library):
    root, source, target, playlist, old, config = library
    items = [{'path':f'/Roms/Game (Disc {i}).chd','label':f'Game (Disc {i})'} for i in (1,2)]
    items.insert(0, {'path':'/Roms/Game.m3u','label':'Game'})
    playlist.write_text(json.dumps({'items':items + old['items']}))
    plan = games.remove_preview({'playlist':str(playlist),'indices':[0], 'expected':mtp.digest(playlist.read_bytes())})
    assert plan['count'] == 3
    assert plan['transaction']['writes'][0]['content'].decode().count('Custom name') == 1


def test_game_apply_consumes_server_plan_once(library, monkeypatch):
    import api_games
    from job_manager import JobManager
    jobs = JobManager(); ident = jobs.create_job(); jobs.complete_job(ident)
    plan = {'can_apply':True, 'trusted':'original'}
    jobs.contexts[ident] = {'game_plan':plan}
    received = []
    monkeypatch.setattr(games, 'apply', lambda p, *args: received.append(p))
    monkeypatch.setattr(api_games, 'background', lambda jobs, title, work: work('apply'))
    monkeypatch.setattr(api_games, 'reply', lambda *args: None)
    api_games.apply(None, SimpleNamespace(job_manager=jobs), {'preview_job_id':ident,'transaction':{'untrusted':True}})
    assert received == [plan]
    with pytest.raises(ValueError, match='预览无效'): api_games.apply(None, SimpleNamespace(job_manager=jobs), {'preview_job_id':ident})


def test_name_edit_is_playlist_only_and_recoverable(library):
    root, source, target, playlist, old, config = library
    before = playlist.read_bytes()
    payload = {'playlist':str(playlist), 'index':0, 'expected':mtp.digest(before), 'label':'New display name'}
    plan = games.edit_preview(payload)
    assert plan['can_apply'] and plan['before'] == 'Custom name'
    result = games.apply(plan)
    updated = json.loads(playlist.read_text())
    assert result['edited'] == 1
    assert updated['items'][0] == {**old['items'][0], 'label':'New display name'}
    assert updated['default_core_path'] == old['default_core_path']
    tx.run(result['operation_id'], restore=True)
    assert playlist.read_bytes() == before
    with pytest.raises(ValueError, match='有效游戏名称'): games.edit_preview({**payload, 'label':'\n'})
    playlist.write_text('{"items":[]}')
    with pytest.raises(ValueError, match='列表已变化'): games.edit_preview(payload)


def test_inspector_details_report_actual_size_default_core_and_missing_file(library):
    root, source, target, playlist, old, config = library
    rom = source / 'demo.gba'; rom.write_bytes(b'game')
    data = {**old, 'default_core_name':'mGBA', 'items':[{'path':str(rom), 'label':'Demo', 'core_path':'DETECT'}]}
    playlist.write_text(json.dumps(data))
    payload = {'playlist':str(playlist), 'index':0, 'expected':mtp.digest(playlist.read_bytes())}
    details = games.details(payload)
    assert details['size'] == 4 and details['file_status'] == 'present'
    assert details['core_path'] == 'special-core' and details['core_name'] == 'mGBA'
    rom.unlink()
    assert games.details(payload)['file_status'] == 'missing'


def test_import_remembers_target_mapping_and_restore_reverts_profile(library):
    root, source, target, playlist, old, config = library
    (source / 'demo.gba').write_bytes(b'game')
    result = games.apply(games.import_preview(config))
    assert games.scan.profiles()[str(root)][0]['directory'] == str(target)
    tx.run(result['operation_id'], restore=True)
    assert not games.scan.profiles().get(str(root))


def test_name_edit_preserves_three_artwork_types_and_refuses_collisions(library):
    from PIL import Image
    root, source, target, playlist, old, config = library
    thumbnails = root / 'thumbnails'
    for kind in ('Named_Boxarts', 'Named_Snaps', 'Named_Titles'):
        directory = thumbnails / SYSTEM / kind; directory.mkdir(parents=True)
        Image.new('RGB', (4,4), 'blue').save(directory / 'Custom name.png')
    before = playlist.read_bytes()
    payload = {'playlist':str(playlist), 'expected':mtp.digest(before), 'index':0, 'label':'New label', 'system':SYSTEM, 'thumbnails':str(thumbnails)}
    plan = games.edit_preview(payload)
    assert len(plan['artwork_copies']) == 3
    result = games.apply(plan)
    for kind in ('Named_Boxarts', 'Named_Snaps', 'Named_Titles'):
        assert (thumbnails / SYSTEM / kind / 'Custom name.png').read_bytes() == (thumbnails / SYSTEM / kind / 'New label.png').read_bytes()
    tx.run(result['operation_id'], restore=True)
    assert playlist.read_bytes() == before
    assert not (thumbnails / SYSTEM / 'Named_Boxarts/New label.png').exists()
    Image.new('RGB', (4,4), 'red').save(thumbnails / SYSTEM / 'Named_Boxarts/New label.png')
    with pytest.raises(ValueError, match='已有不同图片'): games.edit_preview(payload)
