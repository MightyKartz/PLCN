"""Guarded CHD copy/switch/cleanup transactions."""
from datetime import datetime, timezone
import copy
import base64
import json
from pathlib import Path
import posixpath
import re
import tempfile
import uuid

import app_paths
import chd_io as io
import chd_references as references
from content_scan import read
from disc_inspection import inspect_discs, Reader
from m3u_plan import core_support
from library_model import OPTICAL_SYSTEMS
import m3u_transaction as tx
import mtp_runtime as mtp
from task_control import TaskCancelled

RESERVE=64*1024*1024


def conversion(ident):
    if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident): raise ValueError('CHD 操作 ID 无效')
    return json.loads((app_paths.user_data_dir()/'chd-operations'/ident/'manifest.json').read_text(encoding='utf-8'))


def prepare(payload,cancelled=lambda: None,progress=lambda message: None):
    ident=payload.get('conversion_id');record=conversion(ident);selected=payload.get('disc_ids');mode=payload.get('mode','copy')
    if not isinstance(mode,str) or mode not in {'copy','switch','replace'} or not isinstance(selected,list) or not selected or any(not isinstance(value,str) for value in selected) or len(set(selected))!=len(selected):
        raise ValueError('请选择转换结果与回传模式')
    results={result['id']:result for result in record['results'] if result['status']=='content_verified'}
    if not set(selected)<=set(results): raise ValueError('请选择已有内容验证记录的 CHD')
    system=record.get('system') or payload.get('system')
    if not isinstance(system,str) or system not in OPTICAL_SYSTEMS: raise ValueError('请选择 Saturn／PlayStation 列表')
    runtime=payload.get('runtime',{})
    if not isinstance(runtime,dict) or not isinstance(runtime.get('version',''),str) or not isinstance(runtime.get('confirmed',False),bool) or not isinstance(payload.get('scope_confirmed',False),bool):
        raise ValueError('运行验证与引用范围信息无效')
    graph=inspect_discs(record['playlist'],system);reader=Reader(record['playlist'])
    nodes={node['id']:node for node in graph['files']};edges={}
    for edge in graph['references']: edges.setdefault(edge['source'],[]).append(edge['target'])
    inventory={io.key(file['path']):file for file in (record.get('transfer_sources') or record['sources'])}
    issues=[];sources={};copies=[];selections={}
    operation=uuid.uuid4().hex
    for disc_id in selected:
        cancelled();result=results[disc_id];node=nodes.get(disc_id)
        if not node or node['format']!='cue' or node['issues']: raise ValueError('原 CUE 或其引用已变化，请重新分析')
        progress('核对转换输出与原光盘：'+node['path'])
        local=result['output']
        if io.digest(local,cancelled)!=result['sha256']: raise ValueError('电脑 CHD 在验证后变化')
        access=io.key(reader.locate(node['path']));logical=posixpath.splitext(node['path'])[0]+'.chd'
        target=io.key(reader.locate(logical))
        if re.search('[\r\n]',logical): raise ValueError('目标路径含换行，无法更新 M3U')
        if mode!='copy' and mtp.is_mtp(logical): issues.append('启动路径仍是 MTP 传输地址，不能切换引用')
        existing=io.digest(target,cancelled)
        if existing is not None and existing!=result['sha256']: issues.append('目标已有不同 CHD：'+target)
        for entry in references.folders(target.rsplit('/',1)[0]):
            name=mtp.parse(target)[2][-1] if mtp.is_mtp(target) else Path(target).name
            if entry['name'].casefold()==name.casefold() and entry['name']!=name: issues.append('目标有大小写冲突：'+target)
        copies.append({'source':local,'target':target,'logical':logical,'sha256':result['sha256'],'size':result['output_bytes'],
                       'created':existing is None,'stage':target+'.plcn-'+operation+'.tmp'})
        selections[access]={'target':target,'logical':logical}
        for child in [disc_id,*edges.get(disc_id,[])]:
            path=reader.locate(nodes[child]['path']);key=io.key(path)
            expected=inventory.get(key)
            if expected is None or not expected.get('sha256'): raise ValueError('缺少原镜像的完整指纹，请重新转换')
            if io.digest(path,cancelled)!=expected['sha256']: raise ValueError('原光盘在转换后变化：'+path)
            sources[key]={'path':key,'size':expected['size'],'sha256':expected['sha256']}
    roots=sorted({path.rsplit('/',1)[0] for path in sources}|{io.key(record['playlist']).rsplit('/',1)[0]})
    roots=[root for root in roots if not any(root.startswith(other+'/') for other in roots if root!=other)]
    checked=references.scope(roots,record['playlist'],cancelled)
    writes,after_refs,cores=references.edits(checked,selections)
    if mode!='copy':
        issues.extend(checked['errors'])
        if not cores or any('chd' not in core_support(core)['extensions'] for core in cores): issues.append('受影响列表存在未确认 CHD 支持的核心')
        if len(cores)!=1: issues.append('受影响入口必须使用同一已核对核心；本功能不更换核心')
        if not isinstance(runtime.get('version'),str) or not runtime['version'].strip() or runtime.get('confirmed') is not True:
            issues.append('请先以这些 CHD 在原核心验证启动、游戏内存档及所需换盘，并记录核心版本；这是用户运行报告')
    if mode=='replace' and payload.get('scope_confirmed') is not True: issues.append('请确认预览中的目录包含全部相关引用；范围不完整时保留原文件')
    selected_cues=set(selections);deletions=[];retained=[]
    for path,file in sources.items():
        consumers=[ref['owner'] for ref in after_refs if ref['target']==path and ref['owner'] not in selected_cues]
        if consumers: retained.append({'path':path,'consumers':sorted(set(consumers))})
        elif mode=='replace': deletions.append(file)
    patches,guards=references.associations(checked,selections,system) if mode!='copy' else ([],[])
    snapshot={'directories':{path:[list(value) for value in values] for path,values in checked['directories'].items()},
              'documents':{path:mtp.digest(value['raw']) for path,value in checked['documents'].items()}}
    metadata={'can_apply':True,'playlist':record['playlist'],'label':'CHD 引用更新','mode':'chd_references',
              'writes':writes if mode!='copy' else [],'patches':patches,'dependencies':[]}
    requirements={}
    def reserve(path,size):
        entry=requirements.setdefault(io.volume(path),{'path':path,'bytes':0})
        entry['bytes']+=size
    for item in copies:
        if item['created']: reserve(item['target'],item['size'])
    for write in metadata['writes']: reserve(write['path'],len(write['content']))
    temp_required=max([file['size'] for file in sources.values()]+[item['size'] for item in copies])
    if reader.remote: reserve(str(Path(tempfile.gettempdir())/'verify-probe'),temp_required)
    capacity=[]
    for entry in requirements.values():
        free=io.free_bytes(entry['path']);required=entry['bytes']+RESERVE
        capacity.append({'path':entry['path'],'required':required,'free':free})
        if free<required: issues.append('目标或电脑卷空间不足：'+entry['path'])
    # Original source identity/choice keys remain guarded throughout resume; owned patches validate themselves.
    metadata['dependencies']=guards
    return {'id':operation,'conversion_id':ident,'playlist':record['playlist'],'system':system,'mode':mode,
            'copies':copies,'sources':list(sources.values()),'deletions':deletions,'retained':retained,
            'roots':roots,'scope_snapshot':snapshot,'scope_errors':checked['errors'],'runtime':{'cores':sorted(cores),'version':runtime.get('version',''),'confirmed':runtime.get('confirmed') is True,'source':'user_reported'},
            'metadata_plan':metadata,'capacity':capacity,'temporary_required':temp_required,
            'reference_changes':[{'path':write['path'],'bytes':len(write['content'])} for write in metadata['writes']],
            'image_delta_bytes':sum(file['size'] for file in deletions)-sum(item['size'] for item in copies if item['created']),
            'issues':list(dict.fromkeys(issues)),'can_apply':not issues}


def public(plan):
    return {key:value for key,value in plan.items() if key not in {'metadata_plan','scope_snapshot','origin_analysis'}} | {
        'copies':[{key:value for key,value in item.items() if key!='content_base64'} for item in plan['copies']]}


def check_scope(record,after=False):
    checked=references.scope(record['roots'],record['playlist'])
    current={path:[list(value) for value in values] for path,values in checked['directories'].items()}
    # Owned new descriptors are checked by their output hash, not the pre-operation inventory.
    for item in record['copies']:
        if item['created'] and item['target'] not in record['scope_snapshot']['documents']:
            parent=item['target'].rsplit('/',1)[0]
            name=mtp.parse(item['target'])[2][-1] if mtp.is_mtp(item['target']) else Path(item['target']).name
            if parent in current: current[parent]=[entry for entry in current[parent] if entry[0]!=name]
    # Deleted descriptors legitimately disappear after references have been updated;
    # a retried plan may also find scheduled deletions already absent.
    expected=copy.deepcopy(record['scope_snapshot']['directories'])
    absent={file['path'] for file in record.get('deletions',[]) if not io.digest(file['path'])}
    absent.update(file['path'] for file in record.get('sources',[]) if file.get('state') in {'deleting','deleted'} and not io.digest(file['path']))
    for path in absent:
        parent=path.rsplit('/',1)[0];name=mtp.parse(path)[2][-1] if mtp.is_mtp(path) else Path(path).name
        if parent in expected: expected[parent]=[entry for entry in expected[parent] if entry[0]!=name]
    if current!=expected: raise ValueError('引用目录在预览后变化，请重新核对')
    scheduled={file['path'] for file in record.get('deletions',[])}
    for path,digest in record['scope_snapshot']['documents'].items():
        gone=io.digest(path) is None
        if gone and (path in scheduled or any(file['path']==path and file.get('state') in {'deleted','deleting'} for file in record['sources'])): continue
        acceptable={digest}
        if after:
            acceptable.update(mtp.digest(write['content']) for write in record['metadata']['writes'] if write['path']==path)
        if mtp.digest(read(path)) not in acceptable: raise ValueError('引用内容已变化：'+path)
    if checked['errors'] and record['mode']=='replace': raise ValueError('引用检查出现未知项，停止清理')


def start(plan,cancelled=lambda: None,progress=lambda message: None):
    """Apply a confirmed plan: guarded staged uploads, reference update, cleanup."""
    if not plan['can_apply']: raise ValueError('请处理方案中的待确认项')
    record={key:copy.deepcopy(value) for key,value in plan.items()}
    record['metadata']=copy.deepcopy(plan['metadata_plan'])
    record.update(status='applying',created_at=datetime.now(timezone.utc).isoformat(),error=None)
    try:
        for capacity in record['capacity']:
            if io.free_bytes(capacity['path'])<max(RESERVE,capacity['required']):
                raise ValueError('执行前空间检查失败，停止继续')
        if record['mode']!='copy': check_scope(record,after=True)
        deleting={file['path'] for file in record['deletions']}
        for file in record['sources']:
            current=io.digest(file['path'],cancelled)
            if current!=file['sha256'] and not (file['path'] in deleting and current is None):
                raise ValueError('原镜像已变化，停止继续')
        for item in record['copies']:
            current=io.digest(item['target'],cancelled)
            if current is not None and current!=item['sha256']: raise ValueError('CHD 目标已被外部修改')
        tx.check_dependencies(record['metadata']['dependencies'],patches=record['metadata']['patches'])
        with tempfile.TemporaryDirectory(prefix='plcn-deploy-') as staging:
            for index,item in enumerate(record['copies']):
                cancelled();progress('回传并回读校验：'+item['target'])
                if 'content_base64' in item:
                    staged=Path(staging)/f'content-{index}.bin'
                    staged.write_bytes(base64.b64decode(item['content_base64']))
                    if io.digest(str(staged),cancelled)!=item['sha256']: raise ValueError('生成内容与已确认指纹不一致')
                    io.put_new(item['target'],str(staged),item['sha256'],item['stage'],cancelled)
                else:
                    source=item['source']
                    if mtp.is_mtp(source):
                        staged=Path(staging)/f'source-{index}'
                        if io.copy_to(source,staged,cancelled)!=item['sha256']: raise ValueError('源回读校验失败：'+source)
                        source=str(staged)
                    io.put_new(item['target'],source,item['sha256'],item['stage'],cancelled)
                item['state']='verified'
        if record['mode']!='copy':
            for file in record['sources']:
                if io.digest(file['path'],cancelled)!=file['sha256'] and not (file['path'] in deleting and io.digest(file['path']) is None):
                    raise ValueError('原镜像在回传期间变化，不更新引用')
            cancelled();progress('更新并核对列表与 M3U')
            tx.apply(record['metadata'])
            record['status']='references_verified'
        if record['mode']=='replace':
            check_scope(record,after=True)
            for write in record['metadata']['writes']:
                if mtp.digest(read(write['path']))!=mtp.digest(write['content']): raise ValueError('引用未保持已确认的新内容，停止清理')
            for item in record['copies']:
                if io.digest(item['target'],cancelled)!=item['sha256']: raise ValueError('CHD 在回传后变化，停止清理')
            tx.check_dependencies(record['metadata']['dependencies'],patches=record['metadata']['patches'])
            deleting={file['path'] for file in record['deletions']}
            for file in record['sources']:
                if file['path'] not in deleting: continue
                cancelled();progress('删除原镜像：'+file['path'])
                if io.digest(file['path'],cancelled) is not None:
                    io.remove(file['path'],file['sha256'],cancelled)
                file['state']='deleted'
        record['status']='completed';record['error']=None
    except (OSError,ValueError,RuntimeError,TaskCancelled) as error:
        record.update(status='partial',error=str(error))
    record['actual_image_delta_bytes']=(sum(file['size'] for file in record['sources'] if file.get('state')=='deleted')-sum(item['size'] for item in record['copies'] if item['created'] and item.get('state')=='verified')) if record['status']=='completed' else None
    # The result travels through the job API; internal descriptors are not JSON-safe.
    return {key:value for key,value in record.items() if key not in {'metadata','metadata_plan','scope_snapshot','origin_analysis'}} | {
        'copies':[{key:value for key,value in item.items() if key!='content_base64'} for item in record['copies']]}
