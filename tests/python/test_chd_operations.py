"""Real synthetic optical sectors only: no user ROM or emulator/device access."""
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import app_paths
import chd_cue
import chd_operations as ops
import chd_tool
from task_control import TaskCancelled

SYSTEM='Sega - Saturn'


@pytest.fixture
def optical(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir();monkeypatch.setenv('PLCN_HOME',str(home))
    root=tmp_path/'游戏 库';root.mkdir();cue=root/'测试 Disc1.cue';binary=root/'音轨.bin'
    # 100 synthetic raw sectors, including audio and a stored INDEX 00 pregap.
    binary.write_bytes(bytes(2352*60)+bytes(range(256))*(2352*40//256)+bytes(range(2352*40%256)))
    cue.write_text('FILE "音轨.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n TRACK 02 AUDIO\n INDEX 00 00:00:58\n INDEX 01 00:00:60\n',encoding='utf-8')
    playlist=root/'SS.lpl';playlist.write_text(json.dumps({'items':[{'path':str(cue),'label':'测试','core_path':'unknown-core'}]}))
    monkeypatch.setattr(ops,'core_support',lambda path:{'id':None,'extensions':[],'message':'unknown'})
    tool=chd_tool.capability()
    return {'playlist_path':str(playlist),'system':SYSTEM,'workspace':str(root),'tool':tool.get('path') or ''},cue,binary


def available_tool():
    capability=chd_tool.capability()
    if not capability['available'] and os.environ.get('PLCN_REQUIRE_CHD')=='1': pytest.fail(capability['message'])
    if not capability['available']: pytest.skip('Install MAME chdman to run real optical round-trip tests')
    return capability


def test_layout_hashes_raw_tracks_and_rejects_unproven_grammar(optical):
    _,cue,binary=optical
    tracks=chd_cue.layout(cue)
    assert [(track['length']//2352,track['index01']) for track in tracks]==[(58,0),(42,2)]
    assert len(chd_cue.signature(tracks))==2
    cue.write_text('FILE "音轨.bin" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\n',encoding='utf-8')
    with pytest.raises(ValueError,match='尚未支持'): chd_cue.layout(cue)
    cue.write_text('FILE "音轨.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:01\n',encoding='utf-8')
    with pytest.raises(ValueError,match='未引用'): chd_cue.layout(cue)
    binary.write_bytes(b'bad sector')
    with pytest.raises(ValueError,match='完整'): chd_cue.layout(cue)


def test_readonly_analysis_deduplicates_shared_sources_and_skips_chd(optical):
    payload,cue,binary=optical
    second=cue.with_name('第二盘.cue');second.write_bytes(cue.read_bytes())
    doc={'items':[{'path':str(cue)},{'path':str(second)},{'path':str(cue.with_suffix('.chd'))}]}
    Path(payload['playlist_path']).write_text(json.dumps(doc))
    before={path:path.read_bytes() for path in cue.parent.iterdir()}
    plan=ops.analyze(payload)
    assert plan['input_bytes']==cue.stat().st_size+second.stat().st_size+binary.stat().st_size
    assert len([row for row in plan['rows'] if row['eligible']])==2
    assert any('已有压缩' in ' '.join(row['issues']) for row in plan['rows'])
    assert plan['estimated_savings'] is None
    assert all(path.read_bytes()==data for path,data in before.items())
    assert not list(cue.parent.glob('PLCN-CHD-*'))


def test_real_chd_roundtrip_keeps_originals_and_records_exact_evidence(optical):
    available_tool();payload,cue,binary=optical
    before={path:path.read_bytes() for path in [cue,binary,Path(payload['playlist_path'])]}
    plan=ops.analyze(payload);assert plan['can_convert']
    result=ops.convert(plan,[row['id'] for row in plan['rows'] if row['eligible']])
    assert result['status']=='completed' and len(result['results'])==1
    verified=result['results'][0]
    assert verified['status']=='content_verified' and verified['runtime_status']=='not_tested'
    assert Path(verified['output']).is_file() and verified['output_bytes']<binary.stat().st_size
    assert chd_cue.fingerprint(verified['output'])==verified['sha256']
    assert verified['tracks']==chd_cue.signature(chd_cue.layout(cue))
    assert all(path.read_bytes()==data for path,data in before.items())
    assert not list(Path(result['output_directory']).glob('.work-*'))
    assert ops.history()[0]['id']==result['id']


def test_source_change_blocks_conversion_and_retains_failure_receipt(optical):
    available_tool();payload,cue,binary=optical
    plan=ops.analyze(payload);binary.write_bytes(bytes([2])*binary.stat().st_size)
    with pytest.raises(ValueError,match='分析后变化'):ops.convert(plan,[plan['rows'][0]['id']])
    assert ops.history()[0]['status']=='failed'
    assert not list(Path(ops.history()[0]['output_directory']).glob('*.chd'))


def test_roundtrip_mismatch_never_publishes_chd(optical,monkeypatch):
    available_tool();payload,_,_=optical;plan=ops.analyze(payload)
    signature=chd_cue.signature;calls=[0]
    def mismatch(*args):
        result=signature(*args);calls[0]+=1
        if calls[0]==2: result[0]['sha256']='changed'
        return result
    monkeypatch.setattr(chd_cue,'signature',mismatch)
    with pytest.raises(ValueError,match='不一致'): ops.convert(plan,[plan['rows'][0]['id']])
    record=ops.history()[0];assert record['status']=='failed'
    assert not list(Path(record['output_directory']).glob('*.chd'))
    assert list(Path(record['output_directory']).glob('*commands.log'))


def test_insufficient_space_and_missing_tool_block_execution(optical,monkeypatch):
    payload,_,_=optical
    monkeypatch.setattr(shutil,'disk_usage',lambda path:shutil._ntuple_diskusage(100,99,1))
    plan=ops.analyze(payload);assert not plan['space_sufficient']
    if plan['can_convert']:
        with pytest.raises(ValueError,match='空间不足'):ops.convert(plan,[plan['rows'][0]['id']])
    assert not chd_tool.capability(str(Path(payload['workspace'])/'missing'))['available']


def test_cancellation_terminates_worker_and_preserves_sources(optical,monkeypatch):
    available_tool();payload,cue,binary=optical;plan=ops.analyze(payload);original=binary.read_bytes()
    cancel=[False];original_run=chd_tool.run
    def stage(tool,args,directory,cancelled,log):
        cancel[0]=True
        return original_run(tool,args,directory,cancelled,log)
    def cancelled():
        if cancel[0]: raise TaskCancelled('stop requested')
    monkeypatch.setattr(chd_tool,'run',stage)
    with pytest.raises(TaskCancelled):ops.convert(plan,[plan['rows'][0]['id']],cancelled)
    record=ops.history()[0];assert record['status']=='cancelled'
    assert not list(Path(record['output_directory']).glob('*.chd'))
    assert not list(Path(record['output_directory']).glob('.work-*')) and binary.read_bytes()==original


def test_server_plan_is_single_use_and_client_paths_are_not_executed(optical,monkeypatch):
    import api_chd
    from job_manager import JobManager
    from types import SimpleNamespace
    available_tool();payload,_,_=optical;plan=ops.analyze(payload)
    jobs=JobManager();ident=jobs.create_job();jobs.complete_job(ident)
    jobs.contexts[ident]={'chd_plan':plan};context=SimpleNamespace(job_manager=jobs)
    captured=[]
    monkeypatch.setattr(api_chd,'reply',lambda *args:None)
    monkeypatch.setattr(api_chd,'background',lambda jobs,title,work:captured.append(work))
    request={'analysis_job_id':ident,'disc_ids':[plan['rows'][0]['id']],'workspace':'ignored','tool':'ignored'}
    api_chd.convert(None,context,request)
    with pytest.raises(ValueError,match='重新分析'):api_chd.convert(None,context,request)
    result=captured[0](jobs.create_job())
    assert Path(result['output_directory']).parent==Path(payload['workspace'])


def test_tool_change_and_source_change_during_conversion_are_not_published(optical,monkeypatch):
    available_tool();payload,_,binary=optical;plan=ops.analyze(payload)
    original=chd_tool.capability
    monkeypatch.setattr(chd_tool,'capability',lambda value:{**original(value),'sha256':'different'})
    with pytest.raises(ValueError,match='chdman.*变化'):ops.convert(plan,[plan['rows'][0]['id']])
    assert not ops.history()
    monkeypatch.setattr(chd_tool,'capability',original)
    original_run=chd_tool.run
    def mutate(tool,args,directory,cancelled,log):
        original_run(tool,args,directory,cancelled,log)
        if args[0]=='extractcd': binary.write_bytes(bytes([4])*binary.stat().st_size)
    monkeypatch.setattr(chd_tool,'run',mutate)
    with pytest.raises(ValueError,match='转换期间变化'):ops.convert(plan,[plan['rows'][0]['id']])
    assert not list(Path(ops.history()[0]['output_directory']).glob('*.chd'))


@pytest.mark.parametrize('mode',['MODE1/2352','MODE2/2352'])
def test_multifile_audio_disc_and_virtual_gap_roundtrip(optical,mode):
    available_tool();payload,cue,binary=optical
    other=cue.with_name('另一个音轨.bin');other.write_bytes(bytes([8])*(2352*35))
    cue.write_text('FILE "音轨.bin" BINARY\n TRACK 01 '+mode+'\n INDEX 01 00:00:00\nFILE "另一个音轨.bin" BINARY\n TRACK 02 AUDIO\n PREGAP 00:02:00\n INDEX 01 00:00:00\n',encoding='utf-8')
    plan=ops.analyze(payload);assert plan['can_convert']
    result=ops.convert(plan,[plan['rows'][0]['id']])
    assert result['results'][0]['tracks']==chd_cue.signature(chd_cue.layout(cue))
    assert other.exists() and binary.exists()


def test_multiple_discs_cancel_between_discs_keeps_verified_output(optical):
    available_tool();payload,cue,_=optical;second=cue.with_name('测试 Disc2.cue');second.write_bytes(cue.read_bytes())
    Path(payload['playlist_path']).write_text(json.dumps({'items':[{'path':str(cue)},{'path':str(second)}]}))
    plan=ops.analyze(payload);stop=[False]
    def progress(message):
        if message.startswith('2/2'):stop[0]=True
    def cancelled():
        if stop[0]:raise TaskCancelled('cancel second disc')
    with pytest.raises(TaskCancelled):ops.convert(plan,[row['id'] for row in plan['rows']],cancelled,progress)
    record=ops.history()[0];assert record['status']=='cancelled' and len(record['results'])==1
    assert Path(record['results'][0]['output']).exists()


def test_mtp_analysis_reports_known_size_without_reading_or_converting_remote_rom(optical,monkeypatch):
    import mtp_runtime as mtp
    payload,_,_=optical;uri=mtp.uri('device',0x10001,'RetroArch/playlists/SS.lpl')
    remote=mtp.uri('device',0x20001,'Roms/Game.cue')
    monkeypatch.setattr(ops,'inspect_discs',lambda *args:{'playlist_path':uri,'entries':[], 'references':[],
        'coverage':{'errors':[]},'files':[{'id':'disc','path':remote,'format':'cue','size':128,'status':'present','issues':[],'playlist_references':[]}]})
    monkeypatch.setattr(chd_tool,'capability',lambda value:{'available':False,'message':'not installed'})
    monkeypatch.setattr(chd_cue,'fingerprint',lambda *args:pytest.fail('No remote image may be read'))
    plan=ops.analyze({**payload,'playlist_path':uri})
    assert not plan['can_convert'] and plan['observed_bytes']==128
    assert not plan['rows'][0]['eligible'] and '远程 CUE 或音轨未就绪' in plan['rows'][0]['issues'][0]


def test_failed_integrity_check_never_publishes_output(optical,monkeypatch):
    available_tool();payload,_,_=optical;plan=ops.analyze(payload);original=chd_tool.run
    def fail_verify(tool,args,directory,cancelled,log):
        if args[0]=='verify':raise RuntimeError('verify rejected synthetic output')
        return original(tool,args,directory,cancelled,log)
    monkeypatch.setattr(chd_tool,'run',fail_verify)
    with pytest.raises(RuntimeError,match='verify rejected'):ops.convert(plan,[plan['rows'][0]['id']])
    record=ops.history()[0];assert record['status']=='failed' and not record['results']
    assert not list(Path(record['output_directory']).glob('*.chd'))


def test_selecting_a_smaller_batch_can_fit_when_all_discs_do_not(optical,monkeypatch):
    available_tool();payload,cue,binary=optical;second=cue.with_name('测试 Disc2.cue');second.write_bytes(cue.read_bytes())
    Path(payload['playlist_path']).write_text(json.dumps({'items':[{'path':str(cue)},{'path':str(second)}]}))
    size=cue.stat().st_size+binary.stat().st_size
    monkeypatch.setattr(shutil,'disk_usage',lambda path:shutil._ntuple_diskusage(10**9,0,ops.RESERVE+6*size))
    plan=ops.analyze(payload);assert plan['can_convert'] and not plan['space_sufficient']
    with pytest.raises(ValueError,match='空间不足'):ops.convert(plan,[row['id'] for row in plan['rows']])
    result=ops.convert(plan,[plan['rows'][0]['id']]);assert result['status']=='completed' and len(result['results'])==1
