"""Durable CHD copy/switch/cleanup transactions, with source backups before mutation."""
from collections import defaultdict
from datetime import datetime, timezone
import copy
import base64
import json
from pathlib import Path
import posixpath
import re
import shutil
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
from safe_io import atomic_write_bytes, atomic_write_json, file_lock
from task_control import TaskCancelled

RESERVE=64*1024*1024


def receipt(ident):
    if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident): raise ValueError('CHD 操作 ID 无效')
    return app_paths.user_data_dir()/'chd-deployments'/ident/'manifest.json'


def history():
    return [json.loads(path.read_text(encoding='utf-8')) for path in sorted((app_paths.user_data_dir()/'chd-deployments').glob('*/manifest.json'),key=lambda path:path.stat().st_mtime,reverse=True)[:100]]


def conversion(ident):
    receipt(ident)
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
    backup=Path(record['output_directory']).parent/('PLCN-DEPLOY-'+operation)
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
    computer=(sum(file['size'] for file in sources.values()) if mode!='copy' else 0)+sum(item['size'] for item in copies)
    reserve(str(backup),computer)
    before_bytes=sum(len(checked['documents'][write['path']]['raw']) for write in metadata['writes'])
    reserve(str(app_paths.user_data_dir()/'metadata-probe'),before_bytes+sum(len(write['content']) for write in metadata['writes']))
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
            'copies':copies,'sources':list(sources.values()),'deletions':deletions,'retained':retained,'backup_directory':str(backup),
            'roots':roots,'scope_snapshot':snapshot,'scope_errors':checked['errors'],'runtime':{'cores':sorted(cores),'version':runtime.get('version',''),'confirmed':runtime.get('confirmed') is True,'source':'user_reported'},
            'metadata_plan':metadata,'capacity':capacity,'computer_required':computer,'temporary_required':temp_required,
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
    # Deleted descriptors legitimately disappear after references have been updated.
    expected=copy.deepcopy(record['scope_snapshot']['directories'])
    for file in record.get('sources',[]):
        if file.get('state') in {'deleting','deleted'}:
            parent=file['path'].rsplit('/',1)[0];name=mtp.parse(file['path'])[2][-1] if mtp.is_mtp(file['path']) else Path(file['path']).name
            if parent in expected and not io.digest(file['path']): expected[parent]=[entry for entry in expected[parent] if entry[0]!=name]
    if current!=expected: raise ValueError('引用目录在预览后变化，请重新核对')
    for path,digest in record['scope_snapshot']['documents'].items():
        if any(file['path']==path and file.get('state') in {'deleted','deleting'} and io.digest(path) is None for file in record['sources']): continue
        acceptable={digest}
        if after and record.get('references_id'):
            metadata=json.loads(tx.receipt_path(record['references_id']).read_text(encoding='utf-8'))
            acceptable.update(file['after_digest'] for file in metadata['files'] if file['path']==path)
        if mtp.digest(read(path)) not in acceptable: raise ValueError('引用内容已变化：'+path)
    if checked['errors'] and record['mode']=='replace': raise ValueError('引用检查出现未知项，停止清理')


def start(plan,cancelled=lambda: None,progress=lambda message: None):
    if not plan['can_apply']: raise ValueError('请处理方案中的待确认项')
    manifest=receipt(plan['id']);manifest.parent.mkdir(parents=True)
    record={key:copy.deepcopy(value) for key,value in plan.items() if key!='metadata_plan'}
    metadata=copy.deepcopy(plan['metadata_plan'])
    for write in metadata['writes']: write['content_base64']=base64.b64encode(write.pop('content')).decode('ascii')
    record.update(status='backing_up',created_at=datetime.now(timezone.utc).isoformat(),error=None,
                  references_id=uuid.uuid4().hex if plan['mode']!='copy' else None,metadata=metadata)
    if plan['mode']=='copy':
        for file in record['sources']: file['state']='kept'
    if Path(record['backup_directory']).exists(): raise ValueError('电脑备份目录已存在，请重新预览')
    atomic_write_json(manifest,record)
    return run(record['id'],False,cancelled,progress)


def backup_files(record):
    return record['copies'] if record['mode']=='copy' else record['sources']+record['copies']


def run(ident,restore=False,cancelled=lambda: None,progress=lambda message: None):
    manifest=receipt(ident)
    with file_lock(manifest):
        record=json.loads(manifest.read_text(encoding='utf-8'))
        if record['status']=='restored': raise ValueError('该操作已恢复')
        try:
            if restore and not any(item.get('state') in {'uploading','verified'} for item in record['copies']):
                record.update(status='restored',error=None,actual_image_delta_bytes=0);atomic_write_json(manifest,record);return record
            if not restore:
                consumed=defaultdict(int)
                for file in backup_files(record):
                    if file.get('backup_verified'): consumed[io.volume(file['backup'])]+=file['size']
                for item in record['copies']:
                    if item.get('state') in {'uploading','verified'} and io.digest(item['target'],cancelled)==item['sha256']:
                        consumed[io.volume(item['target'])]+=item['size']
                if record['references_id'] and tx.receipt_path(record['references_id']).exists():
                    nested=json.loads(tx.receipt_path(record['references_id']).read_text(encoding='utf-8'))
                    for file in nested['files']:
                        for snapshot in [file['before'],file['after']]:
                            if snapshot: consumed[io.volume(snapshot)]+=Path(snapshot).stat().st_size
                for capacity in record['capacity']:
                    if io.free_bytes(capacity['path'])<max(RESERVE,capacity['required']-consumed[io.volume(capacity['path'])]):
                        raise ValueError('执行前空间检查失败，停止继续')
                backup=Path(record['backup_directory']);backup.mkdir(exist_ok=True)
                for number,file in enumerate(backup_files(record)):
                    if file.get('backup_verified'): continue
                    cancelled()
                    if file.get('backup') and io.digest(file['backup'],cancelled)==file['sha256']:
                        file.update(backup_verified=True,state='kept' if 'path' in file else 'pending');atomic_write_json(manifest,record);continue
                    source=file['path'] if 'path' in file else file['source']
                    progress('建立电脑备份：'+source)
                    file['backup']=str(backup/(f'{number}-'+uuid.uuid4().hex+'.bin'))
                    atomic_write_json(manifest,record)
                    if 'content_base64' in file:
                        atomic_write_bytes(file['backup'],base64.b64decode(file['content_base64']))
                        actual=io.digest(file['backup'],cancelled)
                    else: actual=io.copy_to(source,file['backup'],cancelled)
                    if actual!=file['sha256']: raise ValueError('电脑备份与已确认指纹不一致')
                    file.update(backup_verified=True,state='kept' if 'path' in file else 'pending');atomic_write_json(manifest,record)
                if record['references_id'] and not tx.receipt_path(record['references_id']).exists():
                    metadata=copy.deepcopy(record['metadata'])
                    for write in metadata['writes']: write['content']=base64.b64decode(write.pop('content_base64'))
                    tx.prepare(metadata,record['references_id'])
            # All computer backups and current owned targets are checked before mutation.
            for file in backup_files(record):
                if not file.get('backup') or io.digest(file['backup'],cancelled)!=file['sha256']: raise ValueError('电脑备份不完整，停止操作')
            for item in record['copies']:
                current=io.digest(item['target'],cancelled)
                if current is not None and current!=item['sha256']: raise ValueError('CHD 目标已被外部修改')
            if restore:
                record['status']='restoring';atomic_write_json(manifest,record)
                needs={}
                restore_sources=record['sources'] if record['mode']!='copy' else []
                for file in restore_sources:
                    current=io.digest(file['path'],cancelled)
                    if current not in {None,file['sha256']}: raise ValueError('原镜像路径已有不同内容，拒绝恢复覆盖')
                    if current is None:
                        key=io.volume(file['path']);entry=needs.setdefault(key,{'path':file['path'],'size':0});entry['size']+=file['size']
                if record['references_id']:
                    metadata=json.loads(tx.receipt_path(record['references_id']).read_text(encoding='utf-8'))
                    for file in metadata['files']:
                        if file['before']:
                            key=io.volume(file['path']);entry=needs.setdefault(key,{'path':file['path'],'size':0});entry['size']+=Path(file['before']).stat().st_size
                for entry in needs.values():
                    if io.free_bytes(entry['path'])<entry['size']+RESERVE: raise ValueError('恢复原镜像与引用所需空间不足')
                for file in restore_sources:
                    cancelled()
                    io.put_new(file['path'],file['backup'],file['sha256'],file['path']+'.plcn-'+ident+'.restore.tmp',cancelled)
                    file['state']='kept';atomic_write_json(manifest,record)
                if record['references_id']:
                    metadata=json.loads(tx.receipt_path(record['references_id']).read_text(encoding='utf-8'))
                    if metadata['status']!='restored':
                        result=tx.run(record['references_id'],restore=True)
                        if result['status']!='restored': raise ValueError('引用恢复未完成：'+str(result['error']))
                checked=references.scope(record['roots'],record['playlist'],cancelled)
                record['restored_retained_outputs']=[]
                owned={item['target'] for item in record['copies'] if item['created']}
                live={ref['target'] for ref in checked['references'] if ref['owner'] not in owned}
                while True:
                    reached={ref['target'] for ref in checked['references'] if ref['owner'] in live}
                    if reached<=live: break
                    live.update(reached)
                removable=owned-live
                for item in sorted(record['copies'],key=lambda item:not item['target'].lower().endswith('.m3u')):
                    cancelled();item['state']='restored'
                    if item['created'] and io.digest(item['target'],cancelled) is not None:
                        consumers=[ref['owner'] for ref in checked['references'] if ref['target']==item['target'] and ref['owner'] not in removable]
                        if consumers or checked['errors']:
                            item['state']='retained';record['restored_retained_outputs'].append({'path':item['target'],'consumers':consumers,'issues':checked['errors']})
                        else: io.remove(item['target'],item['sha256'],cancelled)
                    if io.digest(item['stage'],cancelled) is not None: io.remove(item['stage'],item['sha256'],cancelled)
                record['status']='restored'
            else:
                if record['status'] in {'restore_pending','restoring'}: raise ValueError('请先完成恢复')
                if record['mode']!='copy': check_scope(record,after=True)
                for file in record['sources']:
                    current=io.digest(file['path'],cancelled)
                    if current is None and file['state'] in {'deleting','deleted'}: continue
                    if current!=file['sha256']: raise ValueError('原镜像已变化，停止继续')
                for item in record['copies']:
                    cancelled();progress('回传并回读校验：'+item['target'])
                    item['state']='uploading';atomic_write_json(manifest,record)
                    io.put_new(item['target'],item['backup'],item['sha256'],item['stage'],cancelled)
                    item['state']='verified';atomic_write_json(manifest,record)
                if record['references_id']:
                    for file in record['sources']:
                        current=io.digest(file['path'],cancelled)
                        if current is None and file['state'] in {'deleting','deleted'}: continue
                        if current!=file['sha256']: raise ValueError('原镜像在回传期间变化，不更新引用')
                    cancelled();progress('更新并核对列表与 M3U')
                    result=tx.run(record['references_id'])
                    if result['status']!='applied': raise ValueError('引用部分完成：'+str(result['error']))
                    record['status']='references_verified';atomic_write_json(manifest,record)
                if record['mode']=='replace':
                    check_scope(record,after=True)
                    metadata=json.loads(tx.receipt_path(record['references_id']).read_text(encoding='utf-8'))
                    for file in metadata['files']:
                        if mtp.digest(read(file['path']))!=file['after_digest']: raise ValueError('引用未保持已确认的新内容，停止清理')
                    for item in record['copies']:
                        if io.digest(item['target'],cancelled)!=item['sha256']: raise ValueError('CHD 在回传后变化，停止清理')
                    tx.check_dependencies(record['metadata']['dependencies'])
                    deleting={file['path'] for file in record['deletions']}
                    for file in record['sources']:
                        if file['path'] not in deleting or file['state']=='deleted': continue
                        cancelled()
                        if io.digest(file['backup'],cancelled)!=file['sha256']: raise ValueError('清理前电脑备份校验失败')
                        progress('清理已有电脑备份的原镜像：'+file['path'])
                        file['state']='deleting';atomic_write_json(manifest,record)
                        if io.digest(file['path'],cancelled) is not None: io.remove(file['path'],file['sha256'],cancelled)
                        file['state']='deleted';atomic_write_json(manifest,record)
                record['status']='completed'
            record['error']=None
        except (OSError,ValueError,RuntimeError,TaskCancelled) as error:
            record.update(status='restore_pending' if restore else 'partial',error=str(error))
        record['actual_image_delta_bytes']=(sum(file['size'] for file in record['sources'] if file.get('state')=='deleted')-sum(item['size'] for item in record['copies'] if item['created'] and item.get('state') in {'verified','retained'})) if record['status'] in {'completed','restored'} else None
        atomic_write_json(manifest,record)
    return record
