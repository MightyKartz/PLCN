"""Synthetic ROM moves, ZIP references and guarded writes; never real devices."""
import json
from pathlib import Path

import pytest
import app_paths
import chd_deploy as engine
import chd_io as io
import chd_references as refs
import library_model
from playlist_browser import read_playlist
import rom_relocation as relocation
import rom_storage

FLAGS=['auto_overrides_enable','game_specific_options','sort_savefiles_enable','sort_savefiles_by_content_enable',
       'savefiles_in_content_dir','sort_savestates_enable','sort_savestates_by_content_enable','savestates_in_content_dir']


@pytest.fixture
def library(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(home))
    root=tmp_path/'RetroArch';source=root/'Roms';target=root/'GBA';lists=root/'playlists'
    for path in [source,target,lists,root/'saves',root/'states']:path.mkdir(parents=True,exist_ok=True)
    options=root/'core-options.cfg';options.write_text('',encoding='utf-8')
    cfg=root/'retroarch.cfg';cfg.write_text('\n'.join(f'{key} = "false"' for key in FLAGS)+'\n'+
        f'savefile_directory = "{(root/"saves").as_posix()}"\nsavestate_directory = "{(root/"states").as_posix()}"\ncore_options_path = "{options.as_posix()}"\n',encoding='utf-8')
    nested=source/'游戏';nested.mkdir();rom=nested/'游戏.gba';rom.write_bytes(bytes(range(256))*200)
    playlist=lists/'GBA.lpl';playlist.write_text(json.dumps({'items':[{'path':rom.as_posix(),'label':'人工中文名','crc32':'original-crc','core_path':'/cores/mgba_libretro.so','custom':'keep'}]}),encoding='utf-8')
    read_playlist(str(playlist),'Nintendo - Game Boy Advance')
    return {'playlist_path':str(playlist),'system':'Nintendo - Game Boy Advance','source_directory':str(source),'target_directory':str(target),'workspace':str(tmp_path)},rom,playlist,cfg


def plan_for(payload,**kwargs):
    analysis=rom_storage.analyze(payload)
    ids=[row['id'] for row in analysis['rows'] if row['layout']!='keep' and row['source']!=row['target']]
    return relocation.prepare({'file_ids':ids,'mode':'replace','runtime':{'version':'synthetic','confirmed':True},'scope_confirmed':True,**kwargs},analysis)


def test_move_keeps_ids_crc_core_and_label(library):
    payload,rom,playlist,_=library
    old=read_playlist(str(playlist),payload['system'])['items'][0]
    plan=plan_for(payload);assert plan['can_apply'],plan['issues']
    result=engine.start(plan);assert result['status']=='completed',result['error']
    target=Path(result['copies'][0]['target']);assert target.exists() and not rom.exists()
    changed=read_playlist(str(playlist),payload['system'])['items'][0]
    assert changed['game_id']==old['game_id'] and changed['content_id']==old['content_id']
    raw=json.loads(playlist.read_text(encoding='utf-8'))['items'][0]
    assert raw['label']=='人工中文名' and raw['custom']=='keep' and raw['crc32']=='original-crc'
    assert result['actual_image_delta_bytes']==0


def test_zip_new_content_retains_game_and_image_choice(library):
    from artwork_identity import remember,remembered
    payload,rom,playlist,_=library;old=read_playlist(str(playlist),payload['system'])['items'][0]
    context={'system':payload['system'],'playlist_path':str(playlist),'rom_path':rom.as_posix(),'label':'人工中文名'}
    remember(context,'Chosen art','Named_Boxarts')
    analysis=rom_storage.analyze(payload);record=rom_storage.convert(analysis,[analysis['rows'][0]['id']])
    request={'conversion_id':record['id'],'file_ids':[record['results'][0]['id']],'mode':'replace','runtime':{'version':'fixture','confirmed':True},'scope_confirmed':True}
    plan=relocation.prepare(request);assert plan['can_apply'],plan['issues']
    result=engine.start(plan);assert result['status']=='completed',result['error']
    changed=read_playlist(str(playlist),payload['system'])['items'][0]
    assert changed['game_id']==old['game_id'] and changed['content_id']!=old['content_id']
    assert changed['rom_path'].endswith('.zip#游戏.gba') and remembered({**context,'rom_path':changed['rom_path']})
    assert not rom.exists()


def test_copy_then_move_reuses_existing_target(library):
    payload,rom,playlist,_=library;original=playlist.read_bytes()
    first=engine.start(plan_for(payload,mode='copy',runtime={},scope_confirmed=False));assert first['status']=='completed',first['error']
    assert rom.exists() and playlist.read_bytes()==original
    plan=plan_for(payload)
    assert plan['can_apply'],plan['issues'];assert not plan['copies'][0]['created']
    moved=engine.start(plan);assert moved['status']=='completed',moved['error'];assert not rom.exists()


@pytest.mark.parametrize('change',['flag','missing','include','shared','mapping','runtime','scope'])
def test_unknown_save_rules_or_runtime_block_switch_but_allow_copy(library,change):
    payload,_,_,cfg=library;kwargs={}
    if change=='flag':cfg.write_text(cfg.read_text(encoding='utf-8').replace('sort_savefiles_by_content_enable = "false"','sort_savefiles_by_content_enable = "true"'),encoding='utf-8')
    elif change=='missing':cfg.unlink()
    elif change=='include':cfg.write_text('#include "extra.cfg"\n'+cfg.read_text(encoding='utf-8'),encoding='utf-8')
    elif change=='shared':(cfg.parent/'core-options.cfg').write_text('beetle_saturn_shared_int = "enabled"\n',encoding='utf-8')
    elif change=='mapping':cfg.write_text(cfg.read_text(encoding='utf-8').replace('savefile_directory = "','savefile_directory = "relative/'),encoding='utf-8')
    elif change=='runtime':kwargs['runtime']={}
    elif change=='scope':kwargs['scope_confirmed']=False
    assert not plan_for(payload,**kwargs)['can_apply']
    assert plan_for(payload,mode='copy')['can_apply']


def test_existing_identical_target_is_treated_as_satisfied(library):
    payload,rom,_,_=library;(Path(payload['target_directory'])/rom.name).write_bytes(rom.read_bytes())
    plan=plan_for(payload);assert plan['can_apply'] and not plan['copies'][0]['created']


def test_loose_m3u_and_cross_playlist_paths_are_updated(library):
    payload,rom,playlist,_=library
    other=playlist.with_name('Other.lpl');other.write_bytes(playlist.read_bytes())
    loose=rom.parent/'loose.m3u';loose.write_text(rom.name+'\n',encoding='utf-8')
    plan=plan_for(payload);assert plan['can_apply'],plan['issues']
    result=engine.start(plan);assert result['status']=='completed',result['error']
    assert json.loads(other.read_text(encoding='utf-8'))['items'][0]['path']==result['copies'][0]['logical']
    assert '../' in loose.read_text(encoding='utf-8')


def test_changed_save_directory_or_new_descriptor_blocks_before_publication(library):
    payload,rom,playlist,_=library;plan=plan_for(payload)
    (playlist.parent.parent/'saves/new.srm').write_bytes(b'new save')
    result=engine.start(plan);assert result['status']=='partial' and not Path(plan['copies'][0]['target']).exists() and rom.exists()


def test_interrupted_move_retries_from_plan_and_changed_target_blocks_retry(library,monkeypatch):
    payload,rom,_,_=library;plan=plan_for(payload);original=io.put_new;calls=[0]
    def fail(*args,**kwargs):
        calls[0]+=1
        if calls[0]==1:raise RuntimeError('fixture disconnected')
        return original(*args,**kwargs)
    monkeypatch.setattr(io,'put_new',fail)
    result=engine.start(plan);assert result['status']=='partial'
    result=engine.start(plan);assert result['status']=='completed',result['error']
    Path(result['copies'][0]['target']).write_bytes(b'external update')
    assert engine.start(plan)['status']=='partial'


@pytest.fixture
def optical(library):
    payload,rom,playlist,cfg=library;rom.unlink()
    discs=[rom.with_name(f'Game (Disc {number}).chd') for number in [1,2]]
    for disc in discs:disc.write_bytes(b'isolated CHD move fixture '+disc.name.encode())
    m3u=rom.with_name('Game.m3u');m3u.write_text('\n'.join(disc.name for disc in discs)+'\n',encoding='utf-8')
    payload['system']='Sega - Saturn'
    playlist.write_text(json.dumps({'items':[{'path':m3u.as_posix(),'label':'自定义多盘名','core_path':'/cores/mednafen_saturn_libretro.so'}]}),encoding='utf-8')
    entry=read_playlist(str(playlist),payload['system'])['items'][0]
    members=library_model.build_library_model(str(playlist),payload['system'],[{'path':disc.as_posix(),'label':disc.stem} for disc in discs])['entries']
    source=library_model._source_path(str(playlist));key=json.dumps([source,payload['system'],m3u.as_posix()],ensure_ascii=False,separators=(',',':'))
    group={'playlist':source,'game_id':entry['game_id'],'launch_path':m3u.as_posix(),'launch_content_id':entry['content_id'],
           'discs':[{'id':str(number),'path':disc.as_posix(),'format':'chd','number':number,
                     'entry':{**member,'launch_path':disc.as_posix(),'label':disc.stem,'core_path':'/cores/mednafen_saturn_libretro.so'}} for number,(disc,member) in enumerate(zip(discs,members),1)],
           'original_items':{disc.as_posix():{'path':disc.as_posix(),'label':disc.stem,'crc32':'keep'} for disc in discs}}
    from safe_io import atomic_write_json
    atomic_write_json(app_paths.user_data_dir()/'library-disc-groups.json',{'version':1,'groups':{key:group}})
    return payload,m3u,discs,playlist,group


def test_m3u_move_updates_relative_paths_group_ids_and_relationships(optical):
    payload,m3u,discs,playlist,group=optical
    analysis=rom_storage.analyze(payload);row=next(row for row in analysis['rows'] if row['format']=='m3u')
    assert len(row['members'])==2 and row['layout']=='candidate'
    plan=relocation.prepare({'file_ids':[row['id']],'mode':'replace','runtime':{'version':'test','confirmed':True},'scope_confirmed':True},analysis)
    assert plan['can_apply'],plan['issues'];assert len(plan['copies'])==3
    result=engine.start(plan);assert result['status']=='completed',result['error']
    target=Path(payload['target_directory'])/'Game.m3u'
    assert target.read_text(encoding='utf-8')=='Game (Disc 1).chd\nGame (Disc 2).chd\n'
    moved=list(library_model.disc_groups()['groups'].values());assert len(moved)==1
    assert moved[0]['launch_path']==target.as_posix() and moved[0]['launch_content_id']==group['launch_content_id']
    assert [disc['entry']['disc_id'] for disc in moved[0]['discs']]==[disc['entry']['disc_id'] for disc in group['discs']]
    assert [disc['entry']['content_id'] for disc in moved[0]['discs']]==[disc['entry']['content_id'] for disc in group['discs']]
    assert not any(path.exists() for path in [m3u,*discs])


def test_m3u_containing_cue_remains_in_place(optical):
    payload,m3u,discs,_,_=optical;cue=m3u.with_name('other.cue');cue.write_text('FILE "data.bin" BINARY\n',encoding='utf-8')
    m3u.write_text(discs[0].name+'\nother.cue\n',encoding='utf-8')
    row=next(row for row in rom_storage.analyze(payload)['rows'] if row['format']=='m3u')
    assert row['layout']=='keep' and not row.get('members')


def test_new_descriptor_between_preview_and_apply_blocks_cleanup(library):
    payload,rom,_,_=library;plan=plan_for(payload)
    (rom.parent/'new.m3u').write_text(rom.name+'\n',encoding='utf-8')
    result=engine.start(plan);assert result['status']=='partial' and rom.exists() and not Path(plan['copies'][0]['target']).exists()


def test_dual_storage_mtp_move_updates_android_paths(library,monkeypatch):
    from contextlib import contextmanager
    import disc_inspection
    import mtp_runtime as mtp
    payload,rom,_,_=library
    uri=lambda storage,path='':mtp.uri('synthetic',storage,path)
    root=uri(0x10001,'RetroArch');playlist=mtp.join(root,'playlists/GBA.lpl')
    source=uri(0x20001,'Roms/GBA');target=mtp.join(root,'Roms/GBA');game=mtp.join(source,rom.name)
    logical='/storage/CARD/Roms/GBA/'+rom.name
    cfg='\n'.join(f'{key} = "false"' for key in FLAGS)+'\n'+\
        'savefile_directory = "/sdcard/RetroArch/saves"\nsavestate_directory = "/sdcard/RetroArch/states"\ncore_options_path = "/sdcard/RetroArch/core-options.cfg"\n'
    files={playlist:json.dumps({'items':[{'path':logical,'label':'人工名称','core_path':'/cores/mgba_libretro_android.so'}]}).encode(),
           game:rom.read_bytes(),mtp.join(source,'loose.m3u'):(rom.name+'\n').encode(),mtp.join(target,'.keep'):b'',
           mtp.join(root,'retroarch.cfg'):cfg.encode(),mtp.join(root,'core-options.cfg'):b'',
           mtp.join(root,'saves/.keep'):b'',mtp.join(root,'states/.keep'):b''}
    original=dict(files);ids={};calls=[]
    def ident(path):
        if path not in ids:ids[path]=len(ids)+1
        return ids[path]
    def listing(value):
        serial,storage,parent=mtp.parse(value);entries={}
        for path,content in files.items():
            _,other,parts=mtp.parse(path)
            if other!=storage or parts[:len(parent)]!=parent or len(parts)<=len(parent):continue
            name=parts[len(parent)];folder=len(parts)>len(parent)+1
            entries[name]={'id':ident(uri(storage,'/'.join(parent+[name]))),'name':name,'folder':folder,'size':0 if folder else len(content)}
        return list(entries.values())
    def resolve(handle,storage,parts,create=False):
        if not parts:return {'id':0,'folder':True}
        return next((entry for entry in listing(uri(storage,'/'.join(parts[:-1]))) if entry['name']==parts[-1]),None)
    @contextmanager
    def session(value):
        _,storage,parts=mtp.parse(value);yield None,storage,parts
    def children(handle,storage,parent):return listing(next((path for path,number in ids.items() if number==parent),uri(storage)))
    def read_small(path):
        if path.endswith(('.gba','.zip')):pytest.fail('ROMs must be streamed')
        return files.get(path)
    def download(path,target,cancelled=lambda:None):cancelled();Path(target).write_bytes(files[path])
    def upload(path,source,expected,stage,cancelled=lambda:None):
        cancelled()
        if path in files:assert mtp.digest(files[path])==expected;return
        files[path]=Path(source).read_bytes();assert mtp.digest(files[path])==expected;calls.append(('upload',path))
    def remove(path,expected,cancelled=lambda:None):cancelled();assert mtp.digest(files[path])==expected;files.pop(path)
    def write(path,content,expected,suffix=None):
        assert mtp.digest(files.get(path))==expected
        files[path]=content
    for name,value in [('session',session),('listing',listing),('resolve',resolve),('children',children),('read',read_small),
                       ('download_file',download),('upload_file',upload),('remove_file',remove),('write',write)]:monkeypatch.setattr(mtp,name,value)
    monkeypatch.setattr(mtp,'devices',lambda:pytest.fail('No USB access in synthetic test'))
    monkeypatch.setattr(mtp,'stat_file',lambda path:resolve(None,mtp.parse(path)[1],mtp.parse(path)[2]))
    monkeypatch.setattr(mtp,'free_bytes',lambda path:10**10)
    monkeypatch.setattr(disc_inspection,'profiles',lambda:{root:[{'android_directory':'/storage/CARD','directory':uri(0x20001)},
                                                               {'android_directory':'/sdcard/RetroArch','directory':root}]})
    payload.update(playlist_path=playlist,source_directory=source,target_directory=target)
    plan=plan_for(payload);assert plan['can_apply'],plan['issues']
    result=engine.start(plan);assert result['status']=='completed',result['error']
    assert game not in files and mtp.join(target,rom.name) in files
    assert json.loads(files[playlist])['items'][0]['path']=='/sdcard/RetroArch/Roms/GBA/'+rom.name
    assert files[mtp.join(source,'loose.m3u')].decode().startswith('/sdcard/RetroArch/')


def test_target_directory_conflict_is_an_explicit_blocked_plan(library):
    payload,rom,_,_=library;(Path(payload['target_directory'])/rom.name).mkdir()
    plan=plan_for(payload);assert not plan['can_apply'] and any('同名目录' in message for message in plan['issues'])


def test_symlink_target_cannot_pass_hash_checks_and_break_after_cleanup(library):
    import os
    if os.name=='nt':pytest.skip('Windows symlinks require developer mode')
    payload,rom,_,_=library;plan=plan_for(payload);target=Path(plan['copies'][0]['target']);target.symlink_to(rom)
    result=engine.start(plan);assert result['status']=='partial' and '符号链接' in result['error'] and rom.exists()


def test_relocation_api_one_shot_plan(library,monkeypatch):
    from types import SimpleNamespace
    import api_rom_storage as api
    from server import JobManager
    payload,_,_,_=library;plan=plan_for(payload)
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident);jobs.contexts[ident]={'rom_relocation_plan':plan}
    work=[];monkeypatch.setattr(api,'reply',lambda *args:None);monkeypatch.setattr(api,'background',lambda jobs,title,task:work.append(task))
    context=SimpleNamespace(job_manager=jobs);request={'preview_job_id':ident,'target':'/untrusted'}
    api.relocation_apply(None,context,request)
    with pytest.raises(ValueError,match='重新生成'):api.relocation_apply(None,context,request)
    result=work[0](ident);assert result['status']=='completed'


def test_cross_playlist_artwork_choices_keep_their_bound_system_context(library):
    from artwork_identity import remember,remembered
    payload,rom,playlist,_=library;other=playlist.with_name('Collection.lpl');other.write_bytes(playlist.read_bytes())
    library_model.build_library_model(str(other),'Custom collection',[{'path':rom.as_posix(),'label':'人工中文名'}])
    context={'playlist_path':str(other),'system':'Custom collection','rom_path':rom.as_posix(),'label':'人工中文名'}
    remember(context,'Other explicit art','Named_Boxarts')
    result=engine.start(plan_for(payload));assert result['status']=='completed',result['error']
    target=result['copies'][0]['logical'];assert remembered({**context,'rom_path':target})['name']=='Other explicit art'
