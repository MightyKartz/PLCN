"""Synthetic cartridge/layout fixtures only; no user's ROMs or USB sessions."""
import json
from pathlib import Path
import zipfile

import pytest
import chd_io
import rom_storage as ops
from task_control import TaskCancelled


@pytest.fixture
def library(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('PLCN_HOME',str(home))
    root=tmp_path/'Roms';root.mkdir();game=root/'子目录';game.mkdir()
    rom=game/'游戏 (Japan).gba';rom.write_bytes(bytes(range(256))*8000)
    playlist=tmp_path/'GBA.lpl'
    playlist.write_text(json.dumps({'items':[{'path':str(rom),'label':'人工名称','core_path':'/cores/mgba_libretro_android.so'}]}),encoding='utf-8')
    payload={'playlist_path':str(playlist),'system':'GBA','source_directory':str(root),'target_directory':str(root),'workspace':str(tmp_path)}
    return payload,rom,playlist


def test_layout_is_read_only_and_zip_roundtrip_keeps_name_and_source(library):
    payload,rom,playlist=library;before={path:path.read_bytes() for path in [rom,playlist]}
    plan=ops.analyze(payload);row=plan['rows'][0]
    assert row['layout']=='candidate' and row['zip_eligible']
    assert not Path(plan['output_directory']).exists() and len(ops.history())==0
    result=ops.convert(plan,[row['id']]);assert result['status']=='completed' and result['device_saved_bytes']==0
    entry=result['results'][0];assert entry['verification']=='byte_for_byte'
    with zipfile.ZipFile(entry['output']) as zipped:
        assert zipped.namelist()==[rom.name] and zipped.read(rom.name)==before[rom]
        assert zipped.getinfo(rom.name).extract_version==20 # Ordinary cartridge ZIP needs no ZIP64 extension.
    assert Path(entry['output']).stem==rom.stem
    assert all(path.read_bytes()==raw for path,raw in before.items())
    assert entry['sha256']==chd_io.digest(entry['output']) and entry['output_bytes']<entry['input_bytes']
    assert ops.history()[0]['results']==result['results']


def test_same_names_never_merge_or_overwrite_but_zip_copies_are_separate(library):
    payload,rom,_=library
    other=rom.parent.parent/'another';other.mkdir();(other/rom.name).write_bytes(b'other game')
    plan=ops.analyze(payload)
    assert {row['layout'] for row in plan['rows']}=={'conflict'}
    assert plan['rows'][0]['zip_eligible'] # No layout mutation; ZIP has a per-source directory.
    (rom.parent.parent/rom.name).write_bytes(b'existing target')
    plan=ops.analyze(payload);assert all(row['layout'] in {'conflict','already_flat'} for row in plan['rows'])
    assert (rom.parent.parent/rom.name).read_bytes()==b'existing target'


def test_all_current_playlist_cores_must_be_reviewed(library):
    payload,rom,playlist=library
    playlist.write_text(json.dumps({'items':[{'path':str(rom),'core_path':'/cores/mgba_libretro.so'},
                                          {'path':str(rom),'core_path':'/cores/unknown_libretro.so'}]}),encoding='utf-8')
    row=ops.analyze(payload)['rows'][0];assert not row['zip_eligible'] and row['layout']=='candidate'
    with pytest.raises(ValueError,match='请选择'):ops.convert(ops.analyze(payload),[row['id']])


@pytest.mark.parametrize('core,extension,system',[('mgba','gba','GBA'),('gambatte','gb','GB'),('gambatte','gbc','GBC'),('snes9x','sfc','SNES')])
def test_reviewed_raw_cart_formats(library,core,extension,system):
    payload,rom,playlist=library
    new=rom.with_suffix('.'+extension);rom.rename(new)
    playlist.write_text(json.dumps({'items':[{'path':str(new),'core_path':f'/cores/{core}_libretro.dll'}]}),encoding='utf-8')
    payload['system']=system
    assert ops.analyze(payload)['rows'][0]['zip_eligible']


def test_companions_existing_archives_and_optical_descriptors_stay_put(library):
    payload,rom,_=library;(rom.with_suffix('.bps')).write_bytes(b'patch')
    assert not ops.analyze(payload)['rows'][0]['zip_eligible']
    payload['system']='SS'
    for name in ['disc.cue','disc.bin','multi.m3u','disc.chd','archive.zip','disc.ccd']:(rom.parent/name).write_bytes(b'fixture')
    plan=ops.analyze(payload);rows={row['name']:row for row in plan['rows']}
    assert rows['disc.chd']['layout']=='candidate'
    assert all(rows[name]['layout']=='keep' for name in ['disc.cue','multi.m3u','archive.zip','disc.ccd'])
    assert not any(row['zip_eligible'] for row in rows.values())


def test_source_and_playlist_drift_block_publication(library):
    payload,rom,playlist=library;plan=ops.analyze(payload)
    rom.write_bytes(b'changed')
    with pytest.raises(ValueError,match='ROM 在分析后变化'):ops.convert(plan,[plan['rows'][0]['id']])
    record=ops.history()[0];assert record['status']=='failed' and not record['results']
    assert not list(Path(record['output_directory']).glob('**/*.zip'))
    plan=ops.analyze(payload);playlist.write_bytes(b'changed')
    with pytest.raises(ValueError,match='列表已变化'):ops.convert(plan,[plan['rows'][0]['id']])


def test_cancel_cleans_working_copy_and_keeps_durable_verified_results(library):
    payload,_,_=library;plan=ops.analyze(payload);calls=[0]
    def cancel():
        calls[0]+=1
        if calls[0]>4:raise TaskCancelled('cancel fixture')
    with pytest.raises(TaskCancelled):ops.convert(plan,[plan['rows'][0]['id']],cancel)
    record=ops.history()[0];assert record['status']=='cancelled' and not record['results']
    assert not list(Path(record['output_directory']).glob('.work-*'))


def test_capacity_and_selection_boundary(library,monkeypatch):
    payload,_,_=library;plan=ops.analyze(payload)
    for selected in [[],['forged'],[plan['rows'][0]['id']]*2]:
        with pytest.raises(ValueError,match='请选择'):ops.convert(plan,selected)
    monkeypatch.setattr(ops.shutil,'disk_usage',lambda path:type('Disk',(),{'free':1})())
    with pytest.raises(ValueError,match='空间不足'):ops.convert(plan,[plan['rows'][0]['id']])
    assert not ops.history()


@pytest.mark.parametrize('system',['MAME','FBNeo - Arcade Games'])
def test_arcade_is_excluded(library,system):
    payload,_,_=library;payload['system']=system
    with pytest.raises(ValueError,match='街机'):ops.analyze(payload)


def test_fake_mtp_two_storages_only_download_to_computer(library,monkeypatch):
    payload,rom,playlist=library
    remote='mtp://synthetic/00010001/RetroArch/playlists/GBA.lpl'
    root='mtp://synthetic/00020001/Roms/GBA';source=ops.mtp.join(root,rom.name)
    monkeypatch.setattr(ops.mtp,'devices',lambda:pytest.fail('Synthetic fixture must not enumerate USB'))
    raw=json.dumps({'items':[{'path':'/storage/CARD/Roms/GBA/'+rom.name,'core_path':'/cores/mgba_libretro_android.so'}]}).encode()
    monkeypatch.setattr(ops,'read',lambda path:raw)
    monkeypatch.setattr(ops,'folders',lambda path:[{'name':rom.name,'folder':False,'size':rom.stat().st_size}])
    monkeypatch.setattr(ops.Reader,'probe',lambda self,path:{'status':'present','size':len(raw)})
    monkeypatch.setattr('disc_inspection.profiles',lambda:{remote.rsplit('/',2)[0]:[
        {'android_directory':'/storage/CARD/Roms/GBA','directory':root}]})
    original_digest=chd_io.digest
    monkeypatch.setattr(chd_io,'digest',lambda path,cancelled=lambda:None:__import__('hashlib').sha256(raw).hexdigest() if path==remote else original_digest(str(rom) if path==source else path,cancelled))
    def download(path,target,cancelled):
        assert path==source
        with rom.open('rb') as source_file,Path(target).open('xb') as dest:dest.write(source_file.read())
    monkeypatch.setattr(ops.mtp,'download_file',download)
    monkeypatch.setattr(ops.mtp,'write',lambda *args,**kwargs:pytest.fail('No device writes'))
    payload.update(playlist_path=remote,source_directory=root,target_directory=root)
    plan=ops.analyze(payload);assert plan['rows'][0]['zip_eligible'] and plan['rows'][0]['layout']=='already_flat'
    result=ops.convert(plan,[plan['rows'][0]['id']]);assert result['status']=='completed'
    payload['target_directory']='mtp://another/00010001/Roms'
    with pytest.raises(ValueError,match='不属于当前设备'):ops.analyze(payload)


def test_api_consumes_server_plan_once_and_ignores_client_file_paths(library,monkeypatch):
    from types import SimpleNamespace
    import api_rom_storage as api
    from server import JobManager
    payload,_,_=library;plan=ops.analyze(payload);selected=[plan['rows'][0]['id']]
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident);jobs.contexts[ident]={'rom_storage_plan':plan}
    captured=[];monkeypatch.setattr(api,'reply',lambda *args:None)
    monkeypatch.setattr(api,'background',lambda jobs,title,work:captured.append(work))
    observed=[];monkeypatch.setattr(ops,'convert',lambda trusted,chosen,*args:observed.append((trusted,chosen)))
    context=SimpleNamespace(job_manager=jobs)
    with pytest.raises(ValueError,match='不可转换'):api.convert(None,context,{'analysis_job_id':ident,'file_ids':['forged']})
    request={'analysis_job_id':ident,'file_ids':selected,'workspace':'/untrusted','source_directory':'/untrusted'}
    api.convert(None,context,request)
    with pytest.raises(ValueError,match='重新分析'):api.convert(None,context,request)
    captured[0](ident);assert observed==[(plan,selected)]


def test_no_zip_publication_if_roundtrip_changes_bytes(library,monkeypatch):
    payload,_,_=library;plan=ops.analyze(payload)
    original=zipfile.ZipFile.open
    def corrupt(self,name,mode='r',*args,**kwargs):
        if mode=='r':
            import io
            return io.BytesIO(b'wrong content')
        return original(self,name,mode,*args,**kwargs)
    monkeypatch.setattr(zipfile.ZipFile,'open',corrupt)
    with pytest.raises(ValueError,match='解压内容不一致'):ops.convert(plan,[plan['rows'][0]['id']])
    record=ops.history()[0];assert record['status']=='failed' and not record['results']
    assert not list(Path(record['output_directory']).glob('**/*.zip'))


@pytest.mark.parametrize('suffix',['BPS','XDELTA'])
def test_case_variant_patch_companion_preserves_directory(library,suffix):
    payload,rom,playlist=library;renamed=rom.with_name('Game.gba');rom.rename(renamed)
    playlist.write_text(json.dumps({'items':[{'path':str(renamed),'core_path':'/cores/mgba_libretro.so'}]}),encoding='utf-8')
    (renamed.parent/('game.'+suffix)).write_bytes(b'patch fixture')
    row=ops.analyze(payload)['rows'][0]
    assert row['layout']=='keep' and not row['zip_eligible'] and any('补丁' in issue for issue in row['issues'])
