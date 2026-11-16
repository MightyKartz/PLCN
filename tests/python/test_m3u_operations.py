"""M3U plans and durable application/restore against isolated local fixtures."""
import copy
import json
from pathlib import Path

import pytest
import m3u_plan as plans
import m3u_transaction as tx
from disc_inspection import inspect_discs
from playlist_browser import read_playlist

SYSTEM='Sega - Saturn'


@pytest.fixture
def library(tmp_path,monkeypatch):
    monkeypatch.setenv('PLCN_HOME',str(tmp_path/'home'))
    root=tmp_path/'RetroArch';lists=root/'playlists';lists.mkdir(parents=True)
    roms=tmp_path/'Roms';saves=tmp_path/'saves';states=tmp_path/'states'
    for path in [roms,saves,states]: path.mkdir()
    playlist=lists/'SS.lpl'
    names=['Game (Disc 1).chd','Game (Disc 2).chd']
    for name in names:(roms/name).write_bytes(b'ROM contents retained')
    items=[{'path':str(roms/name),'label':'游戏','core_path':'/cores/mednafen_saturn_libretro_android.so',
            'core_name':'Beetle Saturn','db_name':'SS.lpl','custom':'keep'} for name in names]
    items.append({'path':str(roms/'Unrelated.chd'),'label':'保留条目','core_path':'other-core.so'})
    (roms/'Unrelated.chd').touch()
    playlist.write_text(json.dumps({'version':'1.5','items':items,'sort_mode':1},ensure_ascii=False),encoding='utf-8')
    (root/'retroarch.cfg').write_text(f'savefile_directory = "{saves.as_posix()}"\nsavestate_directory = "{states.as_posix()}"\nauto_overrides_enable = "false"\ngame_specific_options = "false"\n',encoding='utf-8')
    with (root/'retroarch.cfg').open('a',encoding='utf-8') as handle: handle.write('core_options_path = \"'+(root/'core-options.cfg').as_posix()+'\"\n')
    monkeypatch.setattr(plans,'core_support',lambda path:{'id':'mednafen_saturn','extensions':['cue','chd','m3u'],'message':'fixture official metadata'})
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='disc_set')
    payload={'playlist_path':str(playlist),'system':SYSTEM,'group_id':group['id'],'disc_ids':group['discs'],
             'label':'游戏','filename':'Game.m3u','mode':'switch','preserve_states':False}
    return playlist,roms,saves,states,payload


def test_preview_read_only_application_save_copy_identity_and_restore(library):
    playlist,roms,saves,_,payload=library
    (saves/'Game (Disc 1).bkr').write_bytes(b'my save')
    before=playlist.read_bytes();old=read_playlist(str(playlist),SYSTEM)
    disc_ids={item['rom_path']:(item['game_id'],item['disc_id'],item['content_id']) for item in old['items']}
    plan=plans.prepare(payload)
    assert plan['can_apply'],plan['issues']
    assert playlist.read_bytes()==before and not (roms/'Game.m3u').exists()
    assert plan['content']=='Game (Disc 1).chd\nGame (Disc 2).chd\n'
    result=tx.start(plan)
    assert result['status']=='applied',result
    doc=json.loads(playlist.read_text(encoding='utf-8'));assert len(doc['items'])==2
    assert Path(doc['items'][0]['path'])==roms/'Game.m3u' and doc['items'][0]['custom']=='keep'
    assert doc['items'][1]['label']=='保留条目'
    assert (saves/'Game.bkr').read_bytes()==b'my save'
    updated=read_playlist(str(playlist),SYSTEM)
    assert updated['items'][0]['game_id']==old['items'][0]['game_id']
    assert {disc['id'] for disc in updated['library_model']['discs']} >= {value[1] for path,value in disc_ids.items() if 'Disc' in path}
    restored=tx.run(result['operation_id'],restore=True)
    assert restored['status']=='restored',restored
    assert playlist.read_bytes()==before
    assert not (roms/'Game.m3u').exists() and not (saves/'Game.bkr').exists()
    assert (saves/'Game (Disc 1).bkr').read_bytes()==b'my save'


def test_conflicting_saves_require_explicit_source_and_states_are_not_migrated(library):
    _,roms,saves,states,payload=library
    (saves/'Game (Disc 1).bkr').write_bytes(b'one');(saves/'Game (Disc 2).bkr').write_bytes(b'two')
    (states/'Game (Disc 1).state').write_bytes(b'state')
    plan=plans.prepare(payload);assert not plan['can_apply']
    assert any('不同' in issue for issue in plan['issues'])
    payload.update(save_source=str(roms/'Game (Disc 2).chd'),preserve_states=True)
    plan=plans.prepare(payload);assert plan['can_apply'],plan['issues']
    result=tx.start(plan);assert result['status']=='applied',result
    assert (saves/'Game.bkr').read_bytes()==b'two' and (states/'Game (Disc 1).state').read_bytes()==b'state'


def test_unknown_saves_offer_file_only_and_reject_target_collision(library):
    playlist,roms,_,_,payload=library
    (playlist.parent.parent/'retroarch.cfg').unlink()
    assert not plans.prepare(payload)['can_apply']
    payload['mode']='file';plan=plans.prepare(payload)
    assert plan['can_apply'];before=playlist.read_bytes()
    result=tx.start(plan);assert result['status']=='applied' and playlist.read_bytes()==before
    assert not plans.prepare(payload)['can_apply']
    (roms/'Game.m3u').write_text('different.chd\n',encoding='utf-8')
    assert not plans.prepare(payload)['can_apply']


def test_changed_playlist_and_new_save_after_preview_prevent_any_target_write(library):
    playlist,roms,saves,_,payload=library
    plan=plans.prepare(payload)
    (saves/'Game (Disc 1).bkr').write_bytes(b'new save')
    with pytest.raises(ValueError,match='目录'):tx.start(plan)
    assert not (roms/'Game.m3u').exists()
    plan=plans.prepare(payload);playlist.write_text('{"items":[]}',encoding='utf-8')
    with pytest.raises(ValueError,match='变化'):tx.start(plan)
    assert not (roms/'Game.m3u').exists()


def test_partial_write_is_recoverable_and_later_external_edits_are_not_overwritten(library,monkeypatch):
    playlist,roms,_,_,payload=library;before=playlist.read_bytes()
    plan=plans.prepare(payload);original=tx.write_checked
    def fail(path,content,expected):
        if Path(path)==playlist: raise RuntimeError('injected playlist write failure')
        return original(path,content,expected)
    monkeypatch.setattr(tx,'write_checked',fail)
    result=tx.start(plan);assert result['status']=='partial' and (roms/'Game.m3u').exists()
    monkeypatch.setattr(tx,'write_checked',original)
    restored=tx.run(result['operation_id'],restore=True);assert restored['status']=='restored' and playlist.read_bytes()==before
    result=tx.start(plans.prepare(payload));assert result['status']=='applied'
    (roms/'Game.m3u').write_text('external change\n',encoding='utf-8')
    result=tx.run(result['operation_id'],restore=True)
    assert result['status']=='restore_pending' and (roms/'Game.m3u').read_text(encoding='utf-8')=='external change\n'


def test_resume_partial_transaction_and_preserve_unrelated_metadata_on_restore(library,monkeypatch):
    playlist,_,_,_,payload=library;before=playlist.read_bytes()
    original=tx.write_checked;failed=[False]
    def fail_once(path,content,expected):
        if Path(path)==playlist and not failed[0]: failed[0]=True;raise RuntimeError('disconnect')
        return original(path,content,expected)
    monkeypatch.setattr(tx,'write_checked',fail_once)
    result=tx.start(plans.prepare(payload));assert result['status']=='partial'
    result=tx.run(result['operation_id']);assert result['status']=='applied',result
    index=tx.app_paths.user_data_dir()/'library-identities.json';data=json.loads(index.read_text(encoding='utf-8'))
    data['game_ids']['unrelated-key']='unrelated-value';index.write_text(json.dumps(data))
    result=tx.run(result['operation_id'],restore=True);assert result['status']=='restored',result
    assert json.loads(index.read_text(encoding='utf-8'))['game_ids']['unrelated-key']=='unrelated-value'
    assert playlist.read_bytes()==before


def test_reorder_existing_m3u_preserves_identity_and_noop_is_not_applied(library):
    playlist,_,_,_,payload=library
    result=tx.start(plans.prepare(payload));assert result['status']=='applied'
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='m3u')
    game_id=read_playlist(str(playlist),SYSTEM)['items'][0]['game_id']
    payload.update(group_id=group['id'],disc_ids=list(reversed(group['discs'])))
    plan=plans.prepare(payload);assert plan['can_apply'],plan['issues']
    result=tx.start(plan);assert result['status']=='applied',result
    assert read_playlist(str(playlist),SYSTEM)['items'][0]['game_id']==game_id
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='m3u')
    payload.update(group_id=group['id'],disc_ids=group['discs'])
    assert not plans.prepare(payload)['can_apply']


def test_saved_artwork_choice_and_existing_images_extend_to_new_entry(library):
    import artwork_identity
    from PIL import Image
    playlist,_,_,_,payload=library
    images=playlist.parent.parent/'thumbnails'
    directory=images/SYSTEM/'Named_Boxarts';directory.mkdir(parents=True)
    original=directory/'Game (Disc 1).png';Image.new('RGB',(8,8),'blue').save(original)
    artwork_identity.remember({'system':SYSTEM,'playlist_path':str(playlist),'rom_path':json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['path'],
                               'label':'游戏'},'Manual cover (Japan)','Named_Boxarts')
    payload['thumbnails']=str(images)
    plan=plans.prepare(payload);assert plan['can_apply'],plan['issues']
    result=tx.start(plan);assert result['status']=='applied',result
    assert (directory/'游戏.png').read_bytes()==original.read_bytes()
    new=artwork_identity.remembered({'system':SYSTEM,'playlist_path':str(playlist),'rom_path':plan['target'],'label':'游戏'})
    assert new['sources']['Named_Boxarts']=='Manual cover (Japan)'
    result=tx.run(result['operation_id'],restore=True);assert result['status']=='restored',result
    assert original.exists() and not (directory/'游戏.png').exists()
    assert not artwork_identity.remembered({'system':SYSTEM,'playlist_path':str(playlist),'rom_path':plan['target'],'label':'游戏'})


def test_split_existing_m3u_keeps_unselected_disc_as_independent_entry(library):
    playlist,roms,_,_,payload=library
    doc=json.loads(playlist.read_text(encoding='utf-8'));third=roms/'Game (Disc 3).chd';third.touch()
    original_third={**doc['items'][1],'path':str(third),'label':'第三盘人工名称','custom':'third-only'}
    doc['items'].insert(2,original_third)
    playlist.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='disc_set')
    payload.update(group_id=group['id'],disc_ids=group['discs'])
    result=tx.start(plans.prepare(payload));assert result['status']=='applied'
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='m3u')
    payload.update(group_id=group['id'],disc_ids=group['discs'][:2])
    plan=plans.prepare(payload);assert plan['can_apply'],plan['issues']
    result=tx.start(plan);assert result['status']=='applied'
    assert next(item for item in json.loads(playlist.read_text(encoding='utf-8'))['items'] if Path(item['path'])==third)==original_third


def test_corrupted_computer_backup_prevents_restore_before_any_change(library):
    playlist,roms,_,_,payload=library
    result=tx.start(plans.prepare(payload));before=playlist.read_bytes()
    receipt=json.loads(tx.receipt_path(result['operation_id']).read_text(encoding='utf-8'))
    Path(next(entry['before'] for entry in receipt['files'] if entry['kind']=='playlist')).write_bytes(b'corrupted')
    result=tx.run(result['operation_id'],restore=True)
    assert result['status']=='restore_pending' and playlist.read_bytes()==before and (roms/'Game.m3u').exists()


def test_mtp_disconnect_after_rename_can_restore_from_computer_backup(tmp_path,monkeypatch):
    import disc_inspection as inspection
    import mtp_runtime as mtp
    monkeypatch.setenv('PLCN_HOME',str(tmp_path/'home'))
    uri=lambda storage,path:mtp.uri('device',storage,path)
    playlist=uri(0x10001,'RetroArch/playlists/SS.lpl');root=uri(0x10001,'RetroArch')
    mapping=[{'android_directory':'/storage/CARD/Roms','directory':uri(0x20001,'Roms')},
             {'android_directory':'/storage/emulated/0/RetroArch','directory':root}]
    monkeypatch.setattr(inspection,'profiles',lambda:{root:mapping})
    paths=['/storage/CARD/Roms/Game (Disc 1).chd','/storage/CARD/Roms/Game (Disc 2).chd']
    files={playlist:json.dumps({'items':[{'path':path,'label':'游戏','core_path':'/data/cores/mednafen_saturn_libretro_android.so'} for path in paths]}).encode(),
           uri(0x10001,'RetroArch/retroarch.cfg'):b'savefile_directory = "/storage/emulated/0/RetroArch/saves"\nsavestate_directory = "/storage/emulated/0/RetroArch/states"\nauto_overrides_enable = "false"\ngame_specific_options = "false"\n'}
    files[uri(0x10001,'RetroArch/retroarch.cfg')]+=b'core_options_path = \"/storage/emulated/0/RetroArch/core-options.cfg\"\n'
    for path in paths:files[uri(0x20001,'Roms/'+path.rsplit('/',1)[-1])]=b'disc-not-read'
    def listing(path):
        serial,storage,parent=mtp.parse(path);entries={}
        for key,data in files.items():
            _,other,parts=mtp.parse(key)
            if other!=storage or parts[:len(parent)]!=parent or len(parts)<=len(parent):continue
            name=parts[len(parent)];folder=len(parts)>len(parent)+1
            entries[name]={'name':name,'folder':folder,'size':0 if folder else len(data)}
        return list(entries.values())
    reads=[]
    def read(path):reads.append(path);return files.get(path)
    monkeypatch.setattr(mtp,'listing',listing);monkeypatch.setattr(mtp,'read',read)
    monkeypatch.setattr(inspection,'folders',listing);monkeypatch.setattr(plans,'folders',listing)
    monkeypatch.setattr('content_scan.folders',listing)
    monkeypatch.setattr(plans,'core_support',lambda _:{'id':'mednafen_saturn','extensions':['chd','cue','m3u'],'message':'official fixture'})
    graph=inspection.inspect_discs(playlist,SYSTEM);group=graph['groups'][0]
    plan=plans.prepare({'playlist_path':playlist,'system':SYSTEM,'group_id':group['id'],'disc_ids':group['discs'],
                        'label':'游戏','filename':'Game.m3u','mode':'switch'})
    assert plan['can_apply'],plan['issues']
    before=files[playlist];failed=[False]
    def write(path,content,expected):
        assert mtp.digest(files.get(path))==expected
        if path==playlist and not failed[0]:failed[0]=True;files.pop(path);raise RuntimeError('USB disconnected after rename')
        files[path]=content
    monkeypatch.setattr(mtp,'write',write)
    def remove(path,expected):assert mtp.digest(files[path])==expected;files.pop(path)
    monkeypatch.setattr(mtp,'remove_verified',remove)
    result=tx.start(plan);assert result['status']=='partial'
    result=tx.run(result['operation_id'],restore=True);assert result['status']=='restored',result
    assert files[playlist]==before and uri(0x20001,'Roms/Game.m3u') not in files
    assert not any(path.lower().endswith('.chd') for path in reads)


def test_changed_source_identity_or_manual_choice_cannot_apply_stale_plan(library):
    import uuid
    playlist,roms,_,_,payload=library
    plan=plans.prepare(payload)
    index_path=tx.app_paths.user_data_dir()/'library-identities.json'
    index=json.loads(index_path.read_text(encoding='utf-8'))
    key=next(key for key in index['game_ids'] if 'Disc 1' in key)
    index['game_ids'][key]=str(uuid.uuid4());index_path.write_text(json.dumps(index))
    with pytest.raises(ValueError,match='来源关联'):tx.start(plan)
    assert not (roms/'Game.m3u').exists()


def test_missing_core_options_location_blocks_switch_but_not_file_creation(library,monkeypatch):
    playlist,_,_,_,payload=library
    config=playlist.parent.parent/'retroarch.cfg'
    config.write_text('\n'.join(line for line in config.read_text(encoding='utf-8').splitlines() if not line.startswith('core_options_path')))
    assert not plans.prepare(payload)['can_apply']
    payload['mode']='file'
    monkeypatch.setattr(plans,'core_support',lambda _:pytest.fail('File-only review should not make core requests'))
    assert plans.prepare(payload)['can_apply']


def test_core_info_parses_android_filename_and_retains_official_source(monkeypatch):
    monkeypatch.setattr(plans.core_catalog,'info',lambda core:{'extensions':['cue','chd','m3u'],'source':'official-fixture'})
    result=plans.core_support('/data/user/0/com.retroarch/cores/mednafen_saturn_libretro_android.so')
    assert result['id']=='mednafen_saturn' and result['source']=='official-fixture'
    assert 'm3u' in result['extensions']


def test_server_plan_is_consumed_once_and_client_cannot_replace_its_paths(monkeypatch):
    from types import SimpleNamespace
    import api_m3u
    from job_manager import JobManager
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident,{})
    plan={'can_apply':True,'trusted':'original'};jobs.contexts[ident]={'m3u_plan':plan}
    calls=[]
    monkeypatch.setattr(api_m3u.transaction,'start',lambda value:calls.append(value) or {'status':'applied','operation_id':'receipt'})
    monkeypatch.setattr(api_m3u,'background',lambda manager,title,work:work('apply-job') or 'job')
    monkeypatch.setattr(api_m3u,'reply',lambda *args:None)
    context=SimpleNamespace(job_manager=jobs)
    payload={'preview_job_id':ident,'writes':[{'path':'untrusted','content':'not used'}]}
    api_m3u.apply(None,context,payload)
    assert calls==[plan]
    with pytest.raises(ValueError,match='重新'):api_m3u.apply(None,context,payload)


def test_state_only_progress_cannot_be_assumed_to_have_an_ingame_save(library):
    _,_,_,states,payload=library
    (states/'Game (Disc 1).state').write_bytes(b'only progress')
    payload['preserve_states']=True
    plan=plans.prepare(payload)
    assert not plan['can_apply'] and any('未找到游戏内存档' in issue for issue in plan['issues'])


def test_renaming_existing_m3u_checks_its_current_save_and_copies_to_new_basename(library):
    playlist,roms,saves,_,payload=library
    result=tx.start(plans.prepare(payload));assert result['status']=='applied'
    (saves/'Game.bkr').write_bytes(b'latest progress from M3U')
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='m3u')
    payload.update(group_id=group['id'],disc_ids=group['discs'],filename='Renamed.m3u')
    plan=plans.prepare(payload);assert plan['can_apply'],plan['issues']
    result=tx.start(plan);assert result['status']=='applied'
    assert (saves/'Renamed.bkr').read_bytes()==(saves/'Game.bkr').read_bytes()
    assert (roms/'Game.m3u').exists()
    result=tx.run(result['operation_id'],restore=True);assert result['status']=='restored'
    assert not (saves/'Renamed.bkr').exists() and (saves/'Game.bkr').exists()
