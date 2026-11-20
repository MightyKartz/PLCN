"""Guarded CHD copy/switch/cleanup transactions on synthetic images; no devices."""
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
from task_control import TaskCancelled
from playlist_browser import read_playlist

SYSTEM='Sega - Saturn'


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(home))
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


def test_replace_applies_exactly_and_keeps_identity(prepared):
    playlist,cue,track,payload=prepared
    before={path:path.read_bytes() for path in [playlist,cue,track]};game=read_playlist(str(playlist),SYSTEM)['items'][0]
    plan=deploy.prepare(payload);assert plan['can_apply'],plan['issues']
    assert all(path.read_bytes()==raw for path,raw in before.items())
    result=deploy.start(plan);assert result['status']=='completed',result.get('error')
    assert cue.with_suffix('.chd').exists() and not cue.exists() and not track.exists()
    updated=read_playlist(str(playlist),SYSTEM)['items'][0]
    assert updated['game_id']==game['game_id'] and updated['disc_id']==game['disc_id']
    assert updated['label']=='人工名称' and json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['custom']=='keep'



def test_copy_only_needs_no_runtime_report_and_never_changes_references(prepared):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes()
    payload.update(mode='copy',runtime={})
    plan=deploy.prepare(payload);assert plan['can_apply'] and not plan['reference_changes']
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert cue.exists() and track.exists() and playlist.read_bytes()==before


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


def test_new_reference_after_preview_blocks_any_upload(prepared):
    _,cue,_,payload=prepared;plan=deploy.prepare(payload)
    (cue.parent/'new.m3u').write_text(cue.name+'\n',encoding='utf-8')
    result=deploy.start(plan);assert result['status']=='partial' and not cue.with_suffix('.chd').exists()


def test_partial_upload_can_retry_from_same_plan(prepared,monkeypatch):
    _,cue,_,payload=prepared;plan=deploy.prepare(payload);original=chd_io.put_new;calls=[0]
    def fail(*args,**kwargs):
        calls[0]+=1
        if calls[0]==1:raise RuntimeError('disconnected')
        return original(*args,**kwargs)
    monkeypatch.setattr(chd_io,'put_new',fail)
    result=deploy.start(plan);assert result['status']=='partial'
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert not cue.exists()


def test_changed_output_is_never_overwritten(prepared):
    _,cue,_,payload=prepared;plan=deploy.prepare(payload)
    result=deploy.start(plan);assert result['status']=='completed'
    cue.with_suffix('.chd').write_bytes(b'external change')
    result=deploy.start(plan);assert result['status']=='partial'
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
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('RETROARCH_ASSISTANT_HOME',str(home))
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
        files[path]=content
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


def test_remote_pull_conversion_transfer_and_cleanup(remote):
    files,original,calls,payload,cue,track=remote
    plan=deploy.prepare(payload);assert plan['can_apply'],plan['issues']
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    target=plan['copies'][0]['target'];assert target in files and cue not in files and track not in files
    assert any(kind=='upload' for kind,_ in calls)


def test_remote_disconnect_after_upload_retries_without_duplicate_upload(remote,monkeypatch):
    import mtp_runtime as mtp
    files,original,calls,payload,cue,track=remote
    plan=deploy.prepare(payload);upload=mtp.upload_file;failed=[False]
    def disconnect(*args,**kwargs):
        upload(*args,**kwargs)
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected after rename')
    monkeypatch.setattr(mtp,'upload_file',disconnect)
    result=deploy.start(plan);assert result['status']=='partial' and cue in files
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert len([call for call in calls if call[0]=='upload'])==1


def test_remote_disconnect_during_source_cleanup_retries_remaining_deletions(remote,monkeypatch):
    import mtp_runtime as mtp
    files,_,calls,payload,cue,track=remote;remove=mtp.remove_file;failed=[False]
    def disconnect(*args,**kwargs):
        remove(*args,**kwargs)
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected after delete')
    monkeypatch.setattr(mtp,'remove_file',disconnect)
    plan=deploy.prepare(payload)
    result=deploy.start(plan);assert result['status']=='partial'
    result=deploy.start(plan);assert result['status']=='completed',result['error']
    assert len([call for call in calls if call[0]=='remove'])==2


def test_source_edit_during_upload_stops_before_reference_update(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes();plan=deploy.prepare(payload);upload=chd_io.put_new
    def mutate(*args,**kwargs):
        upload(*args,**kwargs);track.write_bytes(b'changed by another program')
    monkeypatch.setattr(chd_io,'put_new',mutate)
    result=deploy.start(plan);assert result['status']=='partial'
    assert playlist.read_bytes()==before and cue.exists() and track.read_bytes()==b'changed by another program'


def test_metadata_write_failure_stops_cleanup(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;before=playlist.read_bytes()
    monkeypatch.setattr(deploy.tx,'apply',lambda plan:(_ for _ in ()).throw(ValueError('metadata write failed')))
    result=deploy.start(deploy.prepare(payload));assert result['status']=='partial'
    assert cue.exists() and track.exists() and playlist.read_bytes()==before


def test_user_source_identity_edits_are_not_overwritten(prepared):
    import uuid
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    index=app_paths.user_data_dir()/'library-identities.json';data=json.loads(index.read_text(encoding='utf-8'))
    key=next(key for key in data['game_ids'] if str(cue).replace('\\','/') in key)
    data['game_ids'][key]=str(uuid.uuid4());index.write_text(json.dumps(data),encoding='utf-8')
    result=deploy.start(plan);assert result['status']=='partial' and not cue.with_suffix('.chd').exists()
    payload['mode']='copy';result=deploy.start(deploy.prepare(payload));assert result['status']=='completed'
    assert cue.exists() and track.exists()


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


def test_cancellation_after_upload_preserves_old_references(prepared,monkeypatch):
    from task_control import TaskCancelled
    playlist,cue,track,payload=prepared;before=playlist.read_bytes();put=chd_io.put_new;stop=[False]
    def upload(*args,**kwargs):
        result=put(*args,**kwargs);stop[0]=True;return result
    def cancelled():
        if stop[0]:raise TaskCancelled('cancel before metadata update')
    monkeypatch.setattr(chd_io,'put_new',upload)
    result=deploy.start(deploy.prepare(payload),cancelled);assert result['status']=='partial'
    assert playlist.read_bytes()==before and cue.exists() and track.exists() and result['actual_image_delta_bytes'] is None


def test_confirmed_m3u_group_keeps_disc_ids_and_split_snapshots_across_conversion(prepared,monkeypatch):
    import m3u_plan
    from disc_inspection import inspect_discs
    playlist,cue,track,_=prepared
    first=cue.with_name('游戏 (Disc 1).cue');second=cue.with_name('游戏 (Disc 2).cue');cue.rename(first);second.write_bytes(first.read_bytes())
    doc=json.loads(playlist.read_text(encoding='utf-8'));item=doc['items'][0]
    doc['items']=[{**item,'path':str(path)} for path in [first,second]];playlist.write_text(json.dumps(doc),encoding='utf-8')
    root=playlist.parent.parent;saves=root/'saves';states=root/'states';saves.mkdir();states.mkdir()
    (root/'retroarch.cfg').write_text(f'savefile_directory = "{saves.as_posix()}"\nsavestate_directory = "{states.as_posix()}"\ncore_options_path = "{(root/"options.cfg").as_posix()}"\nauto_overrides_enable = "false"\ngame_specific_options = "false"\n',encoding='utf-8')
    monkeypatch.setattr(m3u_plan,'core_support',lambda path:{'id':'mednafen_saturn','extensions':['cue','chd','m3u'],'message':'fixture'})
    graph=inspect_discs(str(playlist),SYSTEM);group=next(group for group in graph['groups'] if group['kind']=='disc_set')
    merge=m3u_plan.prepare({'playlist_path':str(playlist),'system':SYSTEM,'group_id':group['id'],'disc_ids':group['discs'],'mode':'switch','label':'两盘游戏','filename':'两盘.m3u'})
    assert merge['can_apply'],merge['issues'];assert tx.apply(merge)['status']=='applied'
    before=read_playlist(str(playlist),SYSTEM);ids={disc['id'] for disc in before['library_model']['discs']}
    plan=ops.analyze({'playlist_path':str(playlist),'system':SYSTEM,'workspace':str(root)})
    converted=ops.convert(plan,[row['id'] for row in plan['rows'] if row['eligible']])
    deployment=deploy.prepare({'conversion_id':converted['id'],'disc_ids':[row['id'] for row in converted['results']],'mode':'replace',
                               'scope_confirmed':True,'runtime':{'version':'fixture','confirmed':True}})
    assert deployment['can_apply'],deployment['issues'];result=deploy.start(deployment);assert result['status']=='completed',result['error']
    after=read_playlist(str(playlist),SYSTEM);assert {disc['id'] for disc in after['library_model']['discs']}==ids
    assert after['items'][0]['game_id']==before['items'][0]['game_id']
    groups=json.loads((app_paths.user_data_dir()/'library-disc-groups.json').read_text(encoding='utf-8'))['groups']
    assert all(item['path'].endswith('.chd') for group in groups.values() for item in group['original_items'].values())


def test_interrupted_metadata_apply_retries_from_same_plan(prepared,monkeypatch):
    payload=prepared[3];real=tx.apply;failed=[False]
    def interrupt(plan):
        if not failed[0]:
            failed[0]=True;raise RuntimeError('metadata apply interrupted')
        return real(plan)
    monkeypatch.setattr(deploy.tx,'apply',interrupt)
    plan=deploy.prepare(payload)
    result=deploy.start(plan);assert result['status']=='partial'
    result=deploy.start(plan);assert result['status']=='completed',result['error']


def test_interrupted_cleanup_offers_continuation(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    remove=chd_io.remove;failed=[False]
    def disconnect(*args,**kwargs):
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected during cleanup')
        return remove(*args,**kwargs)
    monkeypatch.setattr(chd_io,'remove',disconnect)
    result=deploy.start(plan)
    assert result['status']=='partial' and result['error']=='disconnected during cleanup'
    assert cue.exists() and track.exists()
    cleanup=result['cleanup'];assert result['cleanup_remaining']==[file['path'] for file in plan['deletions']]
    outcome=deploy.continue_cleanup(cleanup)
    assert outcome['status']=='completed' and not outcome['remaining']
    assert not cue.exists() and not track.exists() and cue.with_suffix('.chd').exists()
    assert json.loads(playlist.read_text(encoding='utf-8'))['items'][0]['path'].endswith('.chd')


def test_continuation_rechecks_scope_and_never_redetects_removed(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    remove=chd_io.remove;failed=[False]
    def disconnect(path,*args,**kwargs):
        if not failed[0] and path.endswith('.cue'):failed[0]=True;raise RuntimeError('disconnected')
        return remove(path,*args,**kwargs)
    monkeypatch.setattr(chd_io,'remove',disconnect)
    result=deploy.start(plan);assert result['status']=='partial'
    cleanup=result['cleanup']
    outcome=deploy.continue_cleanup(cleanup)
    assert outcome['status']=='completed' and not cue.exists() and not track.exists()
    # Already-removed entries stay satisfied on a retry; a file recreated with
    # different content is reported remaining, never deleted unread.
    track.write_bytes(b'external change')
    outcome=deploy.continue_cleanup(cleanup)
    assert outcome['status']=='partial'
    assert outcome['remaining']==[{'path':str(track),'error':'待移除文件已变化：'+str(track)}]
    assert track.read_bytes()==b'external change'


def test_cleanup_continuation_is_bound_to_its_job(prepared,monkeypatch):
    import api_chd
    from job_manager import JobManager
    from types import SimpleNamespace
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident);jobs.contexts[ident]={'chd_deployment':plan}
    captured=[];monkeypatch.setattr(api_chd,'reply',lambda *args:None)
    monkeypatch.setattr(api_chd,'background',lambda jobs,title,work:captured.append(work))
    remove=chd_io.remove
    monkeypatch.setattr(chd_io,'remove',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('disconnected')))
    api_chd.deployment_apply(None,SimpleNamespace(job_manager=jobs),{'preview_job_id':ident})
    apply_id=jobs.create_job();result=captured[0](apply_id);jobs.complete_job(apply_id)
    assert result['status']=='partial' and 'cleanup' not in result and result['cleanup_id']==apply_id
    # A different job id cannot reach this cleanup plan.
    with pytest.raises(ValueError,match='失效'):
        api_chd.deployment_cleanup(None,SimpleNamespace(job_manager=jobs),{'cleanup_job_id':'other'})
    monkeypatch.setattr(chd_io,'remove',remove)
    api_chd.deployment_cleanup(None,SimpleNamespace(job_manager=jobs),{'cleanup_job_id':result['cleanup_id']})
    outcome=captured[1](jobs.create_job())
    assert outcome['status']=='completed' and not cue.exists() and not track.exists()


def test_cleanup_remaining_lists_only_files_still_on_disk(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    remove=chd_io.remove
    def fail_track(path,*args,**kwargs):
        if str(path)==str(track):raise RuntimeError('bin locked')
        return remove(path,*args,**kwargs)
    monkeypatch.setattr(chd_io,'remove',fail_track)
    result=deploy.start(plan)
    assert result['status']=='partial' and not cue.exists() and track.exists()
    assert result['cleanup_remaining']==[str(track)]
    monkeypatch.setattr(chd_io,'remove',remove)
    outcome=deploy.continue_cleanup(result['cleanup'])
    assert outcome['status']=='completed' and outcome['deleted']==[str(track)] and not track.exists()


def test_cleanup_cancel_reports_deleted_and_only_continues_remaining(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    original={str(cue):cue.read_bytes(),str(track):track.read_bytes()}
    remove=chd_io.remove;failed=[False]
    def disconnect(*args,**kwargs):
        if not failed[0]:failed[0]=True;raise RuntimeError('disconnected during cleanup')
        return remove(*args,**kwargs)
    monkeypatch.setattr(chd_io,'remove',disconnect)
    cleanup=deploy.start(plan)['cleanup']
    monkeypatch.setattr(chd_io,'remove',remove)
    seen=[]
    def progress(message):
        seen.append(message)
        if len(seen)>=2: raise TaskCancelled('停止')
    outcome=deploy.continue_cleanup(cleanup,progress=progress)
    assert outcome['cancelled'] and len(outcome['deleted'])==1
    remaining={entry['path'] for entry in outcome['remaining']}
    assert remaining=={str(cue),str(track)}-set(outcome['deleted'])
    assert {file['path'] for file in outcome['cleanup']['pending']}==remaining
    # Restoring identical content must not put the file back on the deletion
    # list: the new continuation removes only the verified remainder.
    removed_path=outcome['deleted'][0]
    Path(removed_path).write_bytes(original[removed_path])
    done=deploy.continue_cleanup(outcome['cleanup'])
    assert done['deleted']==list(remaining) and Path(removed_path).read_bytes()==original[removed_path]


def test_continuation_refuses_when_reference_reverted(prepared,monkeypatch):
    playlist,cue,track,payload=prepared;plan=deploy.prepare(payload)
    monkeypatch.setattr(chd_io,'remove',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('disconnected')))
    result=deploy.start(plan);assert result['status']=='partial'
    doc=json.loads(playlist.read_text(encoding='utf-8'));doc['items'][0]['path']=str(cue);playlist.write_text(json.dumps(doc),encoding='utf-8')
    with pytest.raises(ValueError,match='引用'):
        deploy.continue_cleanup(result['cleanup'])
    assert cue.exists() and track.exists()
