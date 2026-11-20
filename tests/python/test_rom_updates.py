import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import game_management as games
import rom_updates as updates
import m3u_transaction as tx
import mtp_runtime as mtp

SYSTEM='Nintendo - Game Boy Advance'


@pytest.fixture
def rom(tmp_path,monkeypatch):
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(tmp_path/'profile'))
    target=tmp_path/'Original.gba';target.write_bytes(b'old ROM')
    source=tmp_path/'New v2.gba';source.write_bytes(b'new ROM')
    playlist=tmp_path/'GBA.lpl'
    document={'default_core_path':'custom-core','items':[{'path':str(target),'label':'My title','core_path':'own-core','crc32':'12345678|crc','custom':42}]}
    playlist.write_text(json.dumps(document))
    payload={'playlist':str(playlist),'expected':mtp.digest(playlist.read_bytes()),'index':0,'source':str(source),'system':SYSTEM}
    return target,source,playlist,document,payload


def test_update_preserves_metadata_and_saves(rom):
    target,source,playlist,original,payload=rom
    save=target.with_suffix('.sav');save.write_bytes(b'keep save')
    before=playlist.read_bytes();plan=updates.prepare(payload)
    assert target.read_bytes()==b'old ROM' and playlist.read_bytes()==before
    result=games.apply(plan)
    assert result['status']=='applied' and target.read_bytes()==b'new ROM'
    changed=json.loads(playlist.read_bytes());assert changed['items'][0]['crc32']=='DETECT'
    changed['items'][0]['crc32']='12345678|crc';assert changed==original
    assert save.read_bytes()==b'keep save'


def test_identical_rom_is_a_noop(rom):
    target,source,playlist,original,payload=rom;source.write_bytes(target.read_bytes())
    assert not updates.prepare(payload)['can_apply']


def test_changed_target_is_not_overwritten(rom):
    target,source,playlist,original,payload=rom;plan=updates.prepare(payload)
    target.write_bytes(b'changed by user')
    with pytest.raises(ValueError,match='变化'):games.apply(plan)
    assert target.read_bytes()==b'changed by user'


def test_interrupted_update_can_be_retried_with_the_same_plan(rom,monkeypatch):
    target,source,playlist,original,payload=rom;before=playlist.read_bytes();plan=updates.prepare(payload)
    write=tx.write_checked;failed=[False]
    def fail_after_write(path,content,expected):
        result=write(path,content,expected)
        if path==str(target) and content==b'new ROM' and not failed[0]:
            failed[0]=True;raise OSError('simulated readback failure')
        return result
    monkeypatch.setattr(tx,'write_checked',fail_after_write)
    with pytest.raises(OSError):games.apply(plan)
    assert target.read_bytes()==b'new ROM' and playlist.read_bytes()==before
    monkeypatch.setattr(tx,'write_checked',write)
    result=games.apply(plan)
    assert result['status']=='applied' and target.read_bytes()==b'new ROM'
    assert json.loads(playlist.read_bytes())['items'][0]['crc32']=='DETECT'


def test_optical_and_mismatched_formats_are_rejected(rom):
    *_,payload=rom
    with pytest.raises(ValueError,match='多文件光盘'):updates.prepare({**payload,'system':'Sega - Saturn'})
    wrong=Path(payload['source']).with_suffix('.zip');wrong.write_bytes(b'not a ROM')
    with pytest.raises(ValueError,match='格式相同'):updates.prepare({**payload,'source':str(wrong)})


def test_mtp_update_uses_the_same_guarded_transaction(rom,monkeypatch):
    target,source,playlist,original,payload=rom
    remote='mtp://device/00020001/Roms/GBA/Original.gba';listing='mtp://device/00010001/RetroArch/playlists/GBA.lpl'
    original['items'][0]['path']='/storage/CARD/Roms/GBA/Original.gba'
    files={remote:b'old ROM',listing:json.dumps(original).encode()}
    monkeypatch.setattr(games.scan,'read',lambda path:files.get(path))
    monkeypatch.setattr(tx,'read',lambda path:files.get(path))
    monkeypatch.setattr(updates,'Reader',lambda path:SimpleNamespace(locate=lambda logical:remote,probe=lambda location:{'status':'present','size':7}))
    def write(path,content,expected):
        assert mtp.digest(files.get(path))==expected
        files[path]=content
    monkeypatch.setattr(tx,'write_checked',write)
    plan=updates.prepare({**payload,'playlist':listing,'expected':mtp.digest(files[listing])})
    result=games.apply(plan);assert result['status']=='applied' and files[remote]==b'new ROM'
    assert json.loads(files[listing])['items'][0]['crc32']=='DETECT'


def test_reapply_refuses_to_overwrite_a_later_rom_change(rom):
    target,source,playlist,original,payload=rom
    plan=updates.prepare(payload)
    games.apply(plan);target.write_bytes(b'later manual version')
    with pytest.raises(ValueError,match='变化'):tx.apply(plan['transaction'])
    assert target.read_bytes()==b'later manual version'


def test_import_conflict_offers_the_existing_game_as_update_target(rom):
    target,source,playlist,original,payload=rom
    source_copy=source.parent/'incoming'/target.name;source_copy.parent.mkdir();source_copy.write_bytes(b'new ROM')
    root=playlist.parent;import_payload={'root':str(root),'destination':str(target.parent),'system':SYSTEM,'sources':[str(source_copy)],'playlist_name':playlist.name}
    # Import always targets root/playlists; use the same document there.
    destination=root/'playlists';destination.mkdir();(destination/playlist.name).write_bytes(playlist.read_bytes())
    plan=games.import_preview(games.validate_import(import_payload));candidate=games.public_preview(plan)['update_candidate']
    assert not plan['can_apply'] and candidate['index']==0 and candidate['source']==str(source_copy)
