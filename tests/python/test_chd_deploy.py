"""CHD deployment/restore on isolated synthetic images; no user/device mutations."""
import json
from pathlib import Path
import shutil

import pytest
import app_paths
import chd_cue
import chd_deploy as deploy
import chd_io
import chd_operations as ops
import m3u_transaction as tx
from playlist_browser import read_playlist

SYSTEM='Sega - Saturn'


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('PLCN_HOME',str(home))
    roms=tmp_path/'Roms';roms.mkdir();lists=tmp_path/'playlists';lists.mkdir()
    cue=roms/'游戏.cue';track=roms/'data.bin';track.write_bytes(bytes(2352*32))
    cue.write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n',encoding='utf-8')
    playlist=lists/'SS.lpl';playlist.write_text(json.dumps({'items':[{'path':str(cue),'label':'人工名称','core_path':'/cores/mednafen_saturn_libretro.so','custom':'keep'}]}),encoding='utf-8')
    monkeypatch.setattr(ops,'core_support',lambda path:{'extensions':['cue','chd','m3u'],'id':'mednafen_saturn'})
    monkeypatch.setattr(deploy,'core_support',lambda path:{'extensions':['cue','chd','m3u']})
    if not shutil.which('chdman'): pytest.skip('real chdman fixture required')
    plan=ops.analyze({'playlist_path':str(playlist),'system':SYSTEM,'workspace':str(tmp_path)})
    result=ops.convert(plan,[row['id'] for row in plan['rows']])
    payload={'conversion_id':result['id'],'disc_ids':[row['id'] for row in result['results']],'mode':'replace',
             'runtime':{'version':'fixture version','confirmed':True},'scope_confirmed':True}
    return playlist,cue,track,payload


def test_replace_and_restore_keep_exact_originals_and_identity(prepared):
    playlist,cue,track,payload=prepared
    before={path:path.read_bytes() for path in [playlist,cue,track]};game=read_playlist(str(playlist),SYSTEM)['items'][0]
    plan=deploy.prepare(payload);assert plan['can_apply'],plan['issues']
    assert all(path.read_bytes()==raw for path,raw in before.items())
    result=deploy.start(plan);assert result['status']=='completed',result.get('error')
    assert cue.with_suffix('.chd').exists() and not cue.exists() and not track.exists()
    updated=read_playlist(str(playlist),SYSTEM)['items'][0]
    assert updated['game_id']==game['game_id'] and updated['disc_id']==game['disc_id']
    assert updated['label']=='人工名称' and json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['custom']=='keep'
    result=deploy.run(result['id'],restore=True);assert result['status']=='restored',result.get('error')
    assert all(path.read_bytes()==raw for path,raw in before.items()) and not cue.with_suffix('.chd').exists()


def test_copy_only_needs_no_runtime_report_and_never_changes_references(prepared):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes()
    payload.update(mode='copy',runtime={})
    plan=deploy.prepare(payload);assert plan['can_apply'] and not plan['reference_changes']
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert cue.exists() and track.exists() and playlist.read_bytes()==before
    assert deploy.run(result['id'],restore=True)['status']=='restored'


def test_unknown_runtime_and_unknown_scope_block_cleanup(prepared):
    _,_,_,payload=prepared;payload.update(runtime={},scope_confirmed=False)
    plan=deploy.prepare(payload);assert not plan['can_apply']
    assert any('核心版本' in issue for issue in plan['issues']) and any('全部相关引用' in issue for issue in plan['issues'])


def test_loose_m3u_cross_list_and_shared_track_are_preserved(prepared):
    playlist,cue,track,payload=prepared
    loose=cue.parent/'合集.m3u';loose.write_text(cue.name+'\n',encoding='utf-8')
    shared=cue.parent/'其他.cue';shared.write_bytes(cue.read_bytes())
    other=playlist.parent/'Other.lpl';other.write_bytes(playlist.read_bytes())
    before={path:path.read_bytes() for path in [playlist,loose,other]}
    plan=deploy.prepare(payload);assert plan['can_apply'],plan['issues']
    assert any(file['path']==chd_io.key(track) for file in plan['retained'])
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert track.exists() and shared.exists() and '.chd' in loose.read_text(encoding='utf-8')
    assert all(json.loads(path.read_text(encoding='utf-8'))['items'][0]['path'].endswith('.chd') for path in [playlist,other])
    result=deploy.run(result['id'],restore=True);assert result['status']=='restored',result['error']
    assert all(path.read_bytes()==raw for path,raw in before.items())


def test_new_reference_after_preview_blocks_any_upload(prepared):
    _,cue,_,payload=prepared;plan=deploy.prepare(payload)
    (cue.parent/'new.m3u').write_text(cue.name+'\n',encoding='utf-8')
    result=deploy.start(plan);assert result['status']=='partial' and not cue.with_suffix('.chd').exists()


def test_partial_upload_can_resume_without_repeating_metadata(prepared,monkeypatch):
    _,cue,_,payload=prepared;plan=deploy.prepare(payload);original=chd_io.put_new;calls=[0]
    def fail(*args,**kwargs):
        calls[0]+=1
        if calls[0]==1:raise RuntimeError('disconnected')
        return original(*args,**kwargs)
    monkeypatch.setattr(chd_io,'put_new',fail)
    result=deploy.start(plan);assert result['status']=='partial'
    result=deploy.run(result['id']);assert result['status']=='completed',result['error']
    assert not cue.exists()
    assert deploy.run(result['id'],restore=True)['status']=='restored'


def test_changed_output_or_corrupt_backup_is_never_overwritten(prepared):
    _,cue,_,payload=prepared;result=deploy.start(deploy.prepare(payload));assert result['status']=='completed'
    cue.with_suffix('.chd').write_bytes(b'external change')
    result=deploy.run(result['id'],restore=True);assert result['status']=='restore_pending'
    assert cue.with_suffix('.chd').read_bytes()==b'external change' and not cue.exists()


def test_unsupported_descriptor_blocks_cleanup_but_copy_remains_available(prepared):
    _,cue,_,payload=prepared;(cue.parent/'other.gdi').write_text('unsupported',encoding='utf-8')
    assert not deploy.prepare(payload)['can_apply']
    payload['mode']='copy';assert deploy.prepare(payload)['can_apply']


@pytest.fixture
def remote(tmp_path,monkeypatch):
    import ctypes
    from contextlib import contextmanager
    import mtp_runtime as mtp
    import disc_inspection
    from types import SimpleNamespace
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('PLCN_HOME',str(home))
    if not shutil.which('chdman'): pytest.skip('MAME chdman required')
    uri=lambda storage,path='':mtp.uri('handheld',storage,path)
    root=uri(0x10001,'RetroArch');playlist=uri(0x10001,'RetroArch/playlists/SS.lpl')
    cue=uri(0x20001,'Roms/中文.cue');track=uri(0x20001,'Roms/data.bin')
    files={playlist:json.dumps({'items':[{'path':'/storage/CARD/Roms/中文.cue','label':'中文名','core_path':'/cores/mednafen_saturn_libretro.so'}]}).encode(),
        cue:b'FILE "data.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n',track:bytes(2352*48)}
    original=dict(files);ids={};calls=[]
    def ident(path):
        if path not in ids: ids[path]=len(ids)+1
        return ids[path]
    @contextmanager
    def session(value):
        serial,storage,parts=mtp.parse(value);yield None,storage,parts
    def listing(value):
        serial,storage,parent=mtp.parse(value);entries={}
        for key,content in files.items():
            _,other,parts=mtp.parse(key)
            if other!=storage or parts[:len(parent)]!=parent or len(parts)<=len(parent):continue
            name=parts[len(parent)];folder=len(parts)>len(parent)+1;path=uri(storage,'/'.join(parent+[name]))
            entries[name]={'id':ident(path),'name':name,'folder':folder,'size':0 if folder else len(content)}
        return list(entries.values())
    def resolve(handle,storage,parts,create=False):
        if not parts:return {'id':0,'folder':True}
        return next((entry for entry in listing(uri(storage,'/'.join(parts[:-1]))) if entry['name']==parts[-1]),None)
    def children(handle,storage,parent):
        path=next((path for path,value in ids.items() if value==parent),uri(storage))
        return listing(path)
    def read_small(path):
        if path.endswith(('.bin','.chd')):pytest.fail('Full remote image used buffered read')
        return files.get(path)
    def download(path,target,cancelled=lambda:None):
        cancelled();calls.append(('download',path));Path(target).write_bytes(files[path])
    def upload(path,source,expected,stage,cancelled=lambda:None):
        cancelled()
        if path in files:
            assert mtp.digest(files[path])==expected;return
        files[stage]=Path(source).read_bytes();assert mtp.digest(files[stage])==expected
        files[path]=files.pop(stage);calls.append(('upload',path))
    def remove(path,expected,cancelled=lambda:None):
        cancelled();assert mtp.digest(files[path])==expected;files.pop(path);calls.append(('remove',path))
    def write(path,content,expected,suffix=None):
        assert mtp.digest(files.get(path))==expected
        backup=path+'.bak-test';files[backup]=files[path];files[path]=content;return backup
    monkeypatch.setattr(mtp,'session',session);monkeypatch.setattr(mtp,'listing',listing)
    monkeypatch.setattr(mtp,'resolve',resolve);monkeypatch.setattr(mtp,'children',children)
    monkeypatch.setattr(mtp,'read',read_small);monkeypatch.setattr(mtp,'download_file',download)
    monkeypatch.setattr(mtp,'upload_file',upload);monkeypatch.setattr(mtp,'remove_file',remove);monkeypatch.setattr(mtp,'write',write)
    monkeypatch.setattr(mtp,'stat_file',lambda value:resolve(None,mtp.parse(value)[1],mtp.parse(value)[2]))
    monkeypatch.setattr(mtp,'free_bytes',lambda value:10**10)
    monkeypatch.setattr(disc_inspection,'profiles',lambda:{root:[{'android_directory':'/storage/CARD/Roms','directory':uri(0x20001,'Roms')},
         {'android_directory':'/storage/emulated/0/RetroArch','directory':root}]})
    monkeypatch.setattr(ops,'core_support',lambda path:{'extensions':['cue','chd','m3u'],'id':'mednafen_saturn'})
    monkeypatch.setattr(deploy,'core_support',lambda path:{'extensions':['cue','chd','m3u']})
    plan=ops.analyze({'playlist_path':playlist,'system':SYSTEM,'workspace':str(tmp_path)})
    assert plan['can_convert'];assert not any(path==track for _,path in calls)
    result=ops.convert(plan,[row['id'] for row in plan['rows']])
    assert files==original
    payload={'conversion_id':result['id'],'disc_ids':[row['id'] for row in result['results']],'mode':'replace','scope_confirmed':True,
             'runtime':{'version':'fixture','confirmed':True}}
    return files,original,calls,payload,cue,track


def test_remote_pull_conversion_transfer_cleanup_and_restore(remote):
    files,original,calls,payload,cue,track=remote
    plan=deploy.prepare(payload);assert plan['can_apply'],plan['issues']
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    target=plan['copies'][0]['target'];assert target in files and cue not in files and track not in files
    result=deploy.run(result['id'],restore=True);assert result['status']=='restored',result['error']
    assert all(files[path]==value for path,value in original.items()) and target not in files
    assert any(kind=='upload' for kind,_ in calls)


def test_remote_disconnect_after_upload_rename_resumes_without_duplicate_upload(remote,monkeypatch):
    import mtp_runtime as mtp
    files,original,calls,payload,cue,track=remote
    plan=deploy.prepare(payload);upload=mtp.upload_file;failed=[False]
    def disconnect(*args,**kwargs):
        upload(*args,**kwargs)
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected after rename')
    monkeypatch.setattr(mtp,'upload_file',disconnect)
    result=deploy.start(plan);assert result['status']=='partial' and cue in files
    result=deploy.run(result['id']);assert result['status']=='completed',result['error']
    assert len([call for call in calls if call[0]=='upload'])==1
    assert deploy.run(result['id'],restore=True)['status']=='restored'


def test_remote_disconnect_during_source_cleanup_resumes_only_remaining_deletions(remote,monkeypatch):
    import mtp_runtime as mtp
    files,_,calls,payload,cue,track=remote;remove=mtp.remove_file;failed=[False]
    def disconnect(*args,**kwargs):
        remove(*args,**kwargs)
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected after delete')
    monkeypatch.setattr(mtp,'remove_file',disconnect)
    result=deploy.start(deploy.prepare(payload));assert result['status']=='partial'
    result=deploy.run(result['id']);assert result['status']=='completed',result['error']
    assert len([call for call in calls if call[0]=='remove'])==2
    assert deploy.run(result['id'],restore=True)['status']=='restored'


def test_source_edit_during_upload_stops_before_reference_update(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes();plan=deploy.prepare(payload);upload=chd_io.put_new
    def mutate(*args,**kwargs):
        upload(*args,**kwargs);track.write_bytes(b'changed by another program')
    monkeypatch.setattr(chd_io,'put_new',mutate)
    result=deploy.start(plan);assert result['status']=='partial'
    assert playlist.read_bytes()==before and cue.exists() and track.read_bytes()==b'changed by another program'


def test_metadata_rollback_after_write_stops_cleanup(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes();run=tx.run
    def rollback(ident,restore=False):
        result=run(ident,restore)
        if not restore:playlist.write_bytes(before)
        return result
    monkeypatch.setattr(tx,'run',rollback)
    result=deploy.start(deploy.prepare(payload));assert result['status']=='partial'
    assert cue.exists() and track.exists() and playlist.read_bytes()==before


def test_backup_corruption_and_user_source_identity_edits_are_not_overwritten(prepared):
    import uuid
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    index=app_paths.user_data_dir()/'library-identities.json';data=json.loads(index.read_text(encoding='utf-8'))
    key=next(key for key in data['game_ids'] if str(cue).replace('\\','/') in key)
    data['game_ids'][key]=str(uuid.uuid4());index.write_text(json.dumps(data),encoding='utf-8')
    result=deploy.start(plan);assert result['status']=='partial' and not cue.with_suffix('.chd').exists()
    payload['mode']='copy';result=deploy.start(deploy.prepare(payload));assert result['status']=='completed'
    Path(result['copies'][0]['backup']).write_bytes(b'corrupt backup')
    result=deploy.run(result['id'],restore=True);assert result['status']=='restore_pending'
    assert cue.exists() and track.exists()


def test_interrupted_backup_resumes_without_recopying_completed_sources(prepared,monkeypatch):
    _,_,_,payload=prepared;copy_file=chd_io.copy_to;calls=[];failed=[False]
    def fail_second(source,target,cancelled=lambda:None):
        calls.append(source)
        if len(calls)==2 and not failed[0]:failed[0]=True;raise RuntimeError('computer copy interrupted')
        return copy_file(source,target,cancelled)
    monkeypatch.setattr(chd_io,'copy_to',fail_second)
    result=deploy.start(deploy.prepare(payload));assert result['status']=='partial'
    first=calls[0];result=deploy.run(result['id']);assert result['status']=='completed',result['error']
    assert calls.count(first)==1


def test_nested_reference_restore_cannot_bypass_parent_source_restoration(prepared,monkeypatch):
    import api_m3u
    from types import SimpleNamespace
    result=deploy.start(deploy.prepare(prepared[3]));assert result['status']=='completed'
    assert all(item['id']!=result['references_id'] for item in tx.receipts())
    with pytest.raises(ValueError,match='先还原原镜像'):api_m3u.recover(None,SimpleNamespace(),{'id':result['references_id'],'action':'restore'})


def test_restore_preserves_output_that_gained_a_new_unrelated_reference(prepared):
    _,cue,track,payload=prepared;result=deploy.start(deploy.prepare(payload));assert result['status']=='completed'
    target=cue.with_suffix('.chd');new=cue.parent/'later.m3u';new.write_text(target.name+'\n',encoding='utf-8')
    result=deploy.run(result['id'],restore=True);assert result['status']=='restored',result['error']
    assert cue.exists() and track.exists() and target.exists() and result['restored_retained_outputs']
    assert result['actual_image_delta_bytes']==-target.stat().st_size


def test_server_owned_deployment_plan_is_single_use_and_ignores_client_mutations(prepared,monkeypatch):
    import api_chd
    from job_manager import JobManager
    from types import SimpleNamespace
    _,cue,track,payload=prepared;payload['mode']='copy';plan=deploy.prepare(payload)
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident);jobs.contexts[ident]={'chd_deployment':plan}
    captured=[];monkeypatch.setattr(api_chd,'reply',lambda *args:None)
    monkeypatch.setattr(api_chd,'background',lambda jobs,title,work:captured.append(work))
    request={'preview_job_id':ident,'mode':'replace','target':'/ignored','deletions':['/ignored']}
    api_chd.deployment_apply(None,SimpleNamespace(job_manager=jobs),request)
    with pytest.raises(ValueError,match='重新生成'):api_chd.deployment_apply(None,SimpleNamespace(job_manager=jobs),request)
    result=captured[0](jobs.create_job());assert result['mode']=='copy' and cue.exists() and track.exists()


def test_cancellation_after_upload_preserves_old_references_and_can_restore(prepared,monkeypatch):
    from task_control import TaskCancelled
    playlist,cue,track,payload=prepared;before=playlist.read_bytes();put=chd_io.put_new;stop=[False]
    def upload(*args,**kwargs):
        result=put(*args,**kwargs);stop[0]=True;return result
    def cancelled():
        if stop[0]:raise TaskCancelled('cancel before metadata update')
    monkeypatch.setattr(chd_io,'put_new',upload)
    result=deploy.start(deploy.prepare(payload),cancelled);assert result['status']=='partial'
    assert playlist.read_bytes()==before and cue.exists() and track.exists() and result['actual_image_delta_bytes'] is None
    result=deploy.run(result['id'],restore=True);assert result['status']=='restored' and result['actual_image_delta_bytes']==0
