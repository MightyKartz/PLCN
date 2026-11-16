"""Phase 3A: local-only CHD copies; never update launch references or delete sources."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import uuid

import app_paths
import chd_cue
import chd_tool
from disc_inspection import inspect_discs, Reader
from library_model import OPTICAL_SYSTEMS
from m3u_plan import core_support
from safe_io import atomic_write_json
from task_control import TaskCancelled

RESERVE=64*1024*1024


def history():
    root=app_paths.user_data_dir()/'chd-operations'
    return [json.loads(path.read_text(encoding='utf-8')) for path in
            sorted(root.glob('*/manifest.json'),key=lambda value:value.stat().st_mtime,reverse=True)[:100]]


def analyze(payload,cancelled=lambda: None,progress=lambda message: None):
    playlist,system=payload.get('playlist_path'),payload.get('system')
    workspace=payload.get('workspace') or str(app_paths.user_data_dir())
    if not isinstance(playlist,str) or not isinstance(system,str) or system not in OPTICAL_SYSTEMS or not isinstance(workspace,str):
        raise ValueError('请选择 Saturn／PlayStation 列表与电脑工作目录')
    if workspace.startswith(('mtp://','adb://')): raise ValueError('工作目录必须位于电脑')
    workspace=Path(workspace).expanduser().resolve()
    if not workspace.is_dir(): raise ValueError('电脑工作目录不存在')
    tool=chd_tool.capability(payload.get('tool',''))
    graph=inspect_discs(playlist,system);reader=Reader(graph['playlist_path'])
    outgoing={}
    for edge in graph['references']: outgoing.setdefault(edge['source'],[]).append(edge['target'])
    cores={};rows=[];sources={};entry_cores={}
    for entry in graph['entries']:
        reached=set();pending=[entry['node_id']]
        while pending:
            ident=pending.pop()
            if ident in reached: continue
            reached.add(ident);pending.extend(outgoing.get(ident,[]))
        for ident in reached: entry_cores.setdefault(ident,set()).add(entry['core_path'])
    for node in graph['files']:
        cancelled()
        if node['format'] in {'bin','img','raw','wav','flac'}: continue
        row={'id':node['id'],'path':node['path'],'format':node['format'],'size':node['size'],
             'eligible':False,'status':node['status'],'issues':[],'files':[],'references':node['playlist_references'],'core':[]}
        if node['status']!='present': row['issues'].append('文件未就绪：'+node['status'])
        if node['format']!='cue':
            row['issues'].append('已有压缩文件，跳过' if node['format']=='chd' else '首版仅转换 BINARY 2352 扇区 CUE；M3U 作为组织文件保留')
        elif reader.remote:
            row['issues'].append('MTP 文件本轮仅分析；拉取、回传与引用更新在阶段 3B 实施')
        elif node['status']!='present' or node['issues']:
            row['issues'].append('CUE 或引用文件尚未通过检查')
        else:
            try:
                tracks=chd_cue.layout(reader.locate(node['path']))
                paths=list(dict.fromkeys([str(Path(reader.locate(node['path'])).resolve()),*[track['file'] for track in tracks]]))
                for path in paths:
                    if path not in sources:
                        progress('读取源文件指纹：'+Path(path).name)
                        stat=Path(path).stat();digest=chd_cue.fingerprint(path,cancelled)
                        if (stat.st_size,stat.st_mtime_ns)!=(Path(path).stat().st_size,Path(path).stat().st_mtime_ns):
                            raise ValueError('源文件在分析期间变化：'+path)
                        sources[path]={'path':path,'size':stat.st_size,'sha256':digest}
                row.update(eligible=True,output_name=node['id'][:12]+'-'+Path(node['path']).stem+'.chd',files=paths,tracks=tracks,source_bytes=sum(sources[path]['size'] for path in paths))
            except (OSError,ValueError) as error:
                row['issues'].append(str(error))
        # A CUE reached through M3U uses that entry's core too; no core is changed.
        for path in sorted(entry_cores.get(node['id'],set())):
            if path not in cores: cores[path]=core_support(path)
            row['core'].append({'path':path,'declares_chd':'chd' in cores[path]['extensions'],**cores[path]})
        if row['eligible'] and (not row['core'] or any(not core['declares_chd'] for core in row['core'])):
            row['issues'].append('核心 CHD 支持未确认；本轮仅生成电脑副本，不切换启动入口')
        rows.append(row)
    rows.sort(key=lambda row:not row['eligible'])
    for row in rows:
        row['shared_sources']=[path for path in row['files'] if sum(path in other['files'] for other in rows)>1]
    files=list(sources.values());size=sum(file['size'] for file in files)
    eligible=[row for row in rows if row['eligible']]
    # Budget twice the source for CHD and extraction expansion, plus one snapshot.
    required=2*sum(row['source_bytes'] for row in eligible)+3*max((row['source_bytes'] for row in eligible),default=0)+RESERVE
    free=shutil.disk_usage(workspace).free
    ident=uuid.uuid4().hex
    return {'id':ident,'output_directory':str(workspace/('PLCN-CHD-'+ident)),'playlist':graph['playlist_path'],'system':system,'workspace':str(workspace),
            'tool':tool,'rows':rows,'sources':files,'input_bytes':size,'required_bytes':required,'free_bytes':free,
            'space_sufficient':free>=required,'coverage':graph['coverage'],
            'observed_bytes':sum(node['size'] or 0 for node in graph['files']),
            'estimated_savings':None,'device_space':{'status':'not_required','message':'本轮不上传；掌机空间需求和传输暂存在阶段 3B 检查'},
            'can_convert':bool(eligible) and tool['available'],
            'mode':'local_copy','note':'只在电脑生成 CHD；不改列表、M3U、核心、存档或原光盘。压缩率未知，完成后报告实际大小。'}


def public(plan):
    return {key:value for key,value in plan.items() if key!='sources'} | {
        'rows':[{key:value for key,value in row.items() if key!='tracks'} for row in plan['rows']]}


def convert(plan,selected,cancelled=lambda: None,progress=lambda message: None):
    rows=[row for row in plan['rows'] if row['id'] in selected]
    if not rows or any(not row['eligible'] for row in rows): raise ValueError('请选择可转换的光盘')
    if not plan['can_convert']: raise ValueError('工具或空间条件不满足，请重新分析')
    tool=plan['tool'];current=chd_tool.capability(tool['path'])
    if not current['available'] or (current['version'],current['sha256'])!=(tool['version'],tool['sha256']):
        raise ValueError('chdman 在分析后变化，请重新分析')
    workspace=Path(plan['workspace'])
    required=2*sum(row['source_bytes'] for row in rows)+3*max(row['source_bytes'] for row in rows)+RESERVE
    if shutil.disk_usage(workspace).free<required: raise ValueError('电脑空间不足，请重新分析')
    cancelled()
    ident=plan['id']
    manifest=app_paths.user_data_dir()/'chd-operations'/ident/'manifest.json'
    manifest.parent.mkdir(parents=True)
    output=Path(plan['output_directory'])
    record={'id':ident,'created_at':datetime.now(timezone.utc).isoformat(),'playlist':plan['playlist'],
            'status':'running','tool':tool,'output_directory':str(output),'mode':'local_copy','error':None,
            'results':[],'sources':[file for file in plan['sources'] if any(file['path'] in row['files'] for row in rows)]}
    atomic_write_json(manifest,record)
    try:
        output.mkdir()
        source_map={file['path']:file for file in record['sources']}
        for number,row in enumerate(rows,1):
            cancelled();progress(f'{number}/{len(rows)} · 核对并复制源文件')
            with tempfile.TemporaryDirectory(prefix='.work-',dir=output) as temporary:
                work=Path(temporary);copied={}
                for index,path in enumerate(row['files']):
                    dest=work/f'source-{index}{Path(path).suffix.lower()}'
                    with Path(path).open('rb') as source,dest.open('xb') as target:
                        while True:
                            cancelled();chunk=source.read(1024*1024)
                            if not chunk: break
                            target.write(chunk)
                    if chd_cue.fingerprint(dest,cancelled)!=source_map[path]['sha256']:
                        raise ValueError('源文件在分析后变化：'+path)
                    copied[path]=dest
                # Rewrite only the strict, explicitly supported CUE grammar into private work files.
                tracks=row['tracks']
                lines=[];last=None
                def timecode(frames):
                    return f'{frames//4500:02d}:{frames//75%60:02d}:{frames%75:02d}'
                for track in tracks:
                    if track['file']!=last:
                        lines.append('FILE "'+copied[track['file']].name+'" BINARY');last=track['file']
                    lines.append(f'  TRACK {track["number"]:02d} {track["type"]}')
                    if track['pregap']: lines.append('    PREGAP '+timecode(track['pregap']))
                    start=track['offset']//2352
                    if track['index01']: lines.append('    INDEX 00 '+timecode(start))
                    lines.append('    INDEX 01 '+timecode(start+track['index01']))
                    if track['postgap']: lines.append('    POSTGAP '+timecode(track['postgap']))
                cue=work/'input.cue';cue.write_text('\n'.join(lines)+'\n',encoding='utf-8')
                expected=chd_cue.signature([{**track,'file':str(copied[track['file']])} for track in tracks],cancelled)
                chd=work/'result.chd'
                log=output/f'{number:03d}-commands.log'
                for stage,args in [('转换',['createcd','-i',str(cue),'-o',str(chd),'-np','1']),
                                   ('完整性校验',['verify','-i',str(chd)]),
                                   ('解压回读',['extractcd','-i',str(chd),'-o',str(work/'roundtrip.cue'),'-sb'])]:
                    progress(f'{number}/{len(rows)} · {stage} · '+Path(row['path']).name)
                    chd_tool.run(tool['path'],args,work,cancelled,log)
                actual=chd_cue.signature(chd_cue.layout(work/'roundtrip.cue'),cancelled)
                if actual!=expected: raise ValueError('CHD 解压后的轨道类型、长度、间隙或扇区 SHA-256 与源不一致')
                # Sources must still be identical after the long conversion.
                for path in row['files']:
                    if chd_cue.fingerprint(path,cancelled)!=source_map[path]['sha256']:
                        raise ValueError('源文件在转换期间变化，结果不发布：'+path)
                cancelled()
                destination=output/row['output_name']
                size=chd.stat().st_size;digest=chd_cue.fingerprint(chd,cancelled)
                chd.rename(destination)
                record['results'].append({'id':row['id'],'source':row['path'],'output':str(destination),
                    'status':'content_verified','input_bytes':row['source_bytes'],'output_bytes':size,
                    'difference_bytes':row['source_bytes']-size,'sha256':digest,'tracks':actual,'log':str(log),
                    'runtime_status':'not_tested','references_updated':False,'sources_deleted':False})
                atomic_write_json(manifest,record)
        record['status']='completed'
    except (OSError,ValueError,RuntimeError,TaskCancelled) as error:
        record.update(status='cancelled' if isinstance(error,TaskCancelled) else 'failed',error=str(error))
        atomic_write_json(manifest,record)
        raise
    finally:
        atomic_write_json(manifest,record)
    return record
