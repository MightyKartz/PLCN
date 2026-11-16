"""Durable, guarded metadata transactions. Never remove original disc/save files."""
from contextlib import ExitStack
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import re
import uuid

import app_paths
import mtp_runtime as mtp
from content_scan import read
from safe_io import atomic_write_bytes, atomic_write_json, file_lock


def operations_dir():
    return app_paths.user_data_dir() / 'm3u-operations'


def receipt_path(ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):
        raise ValueError('无效的多盘操作记录')
    return operations_dir() / ident / 'manifest.json'


def receipts():
    records=[json.loads(path.read_text(encoding='utf-8')) for path in
             sorted(operations_dir().glob('*/manifest.json'),key=lambda path:path.stat().st_mtime,reverse=True)]
    return [record for record in records if record['mode'] not in {'chd_references','rom_references'}][:100]


def patch_value(document, keys):
    value=document
    for key in keys:
        if key not in value:
            return {'exists':False}
        value=value[key]
    return {'exists':True,'value':value}


def patch(path, default, keys, value):
    content=read(str(path))
    document=json.loads(content.decode('utf-8')) if content is not None else default
    return {'path':str(path),'default':default,'keys':keys,'before':patch_value(document,keys),
            'after':{'exists':True,'value':value}}


def update_patch(document, keys, state):
    parent=document
    for key in keys[:-1]:
        parent=parent.setdefault(key,{})
    if state['exists']:
        parent[keys[-1]]=copy.deepcopy(state['value'])
    else:
        parent.pop(keys[-1],None)


def check_dependencies(dependencies, ignored_paths=()):
    from disc_inspection import Reader
    for dependency in dependencies:
        path=dependency['path']
        if 'json_guard' in dependency:
            raw=read(path)
            document=json.loads(raw.decode('utf-8')) if raw is not None else dependency['default']
            if any(patch_value(document,item['keys'])!=item['state'] for item in dependency['json_guard']):
                raise ValueError('来源关联记录已变化，请重新预览：'+path)
        elif 'directory' in dependency:
            from content_scan import folders, join
            ignored={Path(value).name for value in ignored_paths if str(Path(value).parent)==str(Path(path))} if not mtp.is_mtp(path) else {mtp.parse(value)[2][-1] for value in ignored_paths if mtp.is_mtp(value) and value.rsplit('/',1)[0]==path}
            ignored.update(value+'.plcn-lock' for value in list(ignored))
            current=sorted((entry['name'],entry['folder'],entry.get('size')) for entry in folders(path) if entry['name'] not in ignored)
            expected=[tuple(entry) for entry in dependency['directory'] if entry[0] not in ignored]
            if current!=expected: raise ValueError('存档目录在预览后变化，请重新检查：'+path)
        elif 'digest' in dependency:
            if mtp.digest(read(path)) != dependency['digest']:
                raise ValueError('方案依据已变化，请重新预览：'+path)
        else:
            reader=Reader(dependency['playlist'])
            location=reader.locate(dependency['logical'])
            state=reader.probe(location)
            if location!=path or state['status']!='present' or state['size']!=dependency['size']:
                raise ValueError('光盘或音轨已变化，请重新预览：'+dependency['logical'])


def write_checked(path,content,expected):
    if mtp.is_mtp(path):
        return mtp.write(path,content,expected)
    before=read(path)
    if mtp.digest(before)!=expected:
        raise ValueError('目标文件已变化：'+path)
    # Cooperative lock is held by the transaction; atomic replace cannot check absence.
    atomic_write_bytes(path,content,expected_digest=expected if before is not None else None)
    if read(path)!=content:
        raise RuntimeError('写回核对失败：'+path)
    return None


def remove_created(path,expected):
    if mtp.is_mtp(path):
        mtp.remove_verified(path,expected)
    else:
        if mtp.digest(read(path))!=expected:
            raise ValueError('新建文件已变化，拒绝移除：'+path)
        Path(path).unlink()


def prepare(plan,ident=None):
    if not plan['can_apply']:
        raise ValueError('请先解决方案中的待处理问题')
    check_dependencies(plan['dependencies'])
    resuming_preparation=ident is not None
    ident=ident or uuid.uuid4().hex
    directory=receipt_path(ident).parent
    directory.mkdir(parents=True,exist_ok=resuming_preparation)
    record={'id':ident,'created_at':datetime.now(timezone.utc).isoformat(),'status':'prepared',
            'playlist':plan['playlist'],'label':plan['label'],'mode':plan['mode'],
            'dependencies':plan['dependencies'],'files':[],'metadata':[],'error':None}
    for index,change in enumerate(plan['writes']):
        before=read(change['path'])
        if mtp.digest(before)!=change['expected']:
            raise ValueError('文件在备份前已变化，请重新预览：'+change['path'])
        old=directory/f'{index}-before.bin';new=directory/f'{index}-after.bin'
        if before is not None: atomic_write_bytes(old,before)
        atomic_write_bytes(new,change['content'])
        record['files'].append({'path':change['path'],'before':str(old) if before is not None else None,
            'after':str(new),'before_digest':mtp.digest(before),'after_digest':mtp.digest(change['content']),
            'kind':change['kind'],'state':'pending'})
    paths={entry['path'] for entry in record['files']}
    record['dependencies']=[entry for entry in record['dependencies'] if entry['path'] not in paths]
    for path in dict.fromkeys(item['path'] for item in plan['patches']):
        patches=[item for item in plan['patches'] if item['path']==path]
        content=read(path)
        before=directory/f'metadata-{len(record["metadata"])}-before.json'
        if content is not None: atomic_write_bytes(before,content)
        record['metadata'].append({'path':path,'patches':patches,'backup':str(before) if content is not None else None,'backup_digest':mtp.digest(content),'state':'pending'})
    atomic_write_json(receipt_path(ident),record)
    return ident


def start(plan):
    return run(prepare(plan))


def run(ident,restore=False):
    manifest=receipt_path(ident)
    # Lock metadata together with target files; source discs are read-only dependencies.
    with file_lock(manifest), ExitStack() as locks:
        record=json.loads(manifest.read_text(encoding='utf-8'))
        if record['status']=='restored':
            raise ValueError('该操作已恢复')
        paths=sorted({entry['path'] for entry in record['files']+record['metadata'] if not mtp.is_mtp(entry['path'])})
        for path in paths: locks.enter_context(file_lock(path))
        try:
            if not restore:
                if record['status']=='restore_pending': raise ValueError('请先完成待处理的恢复')
                check_dependencies(record['dependencies'],[entry['path'] for entry in record['files']])
            # Preflight every target and every backup before the first mutation.
            for entry in record['files']:
                current=mtp.digest(read(entry['path']))
                interrupted=mtp.is_mtp(entry['path']) and entry['state'] in {'writing','restoring'} and current is None
                if current not in {entry['before_digest'],entry['after_digest']} and not interrupted:
                    raise ValueError('文件在操作后发生变化，拒绝覆盖：'+entry['path'])
                if mtp.digest(Path(entry['after']).read_bytes())!=entry['after_digest']:
                    raise ValueError('方案输出备份损坏：'+entry['after'])
                if entry['before'] and mtp.digest(Path(entry['before']).read_bytes())!=entry['before_digest']:
                    raise ValueError('原文件备份损坏：'+entry['before'])
            metadata=[]
            for entry in record['metadata']:
                raw=read(entry['path'])
                if entry['backup']:
                    if raw is None: raise ValueError('关联索引已被移除，请先核对备份：'+entry['path'])
                    if mtp.digest(Path(entry['backup']).read_bytes())!=entry['backup_digest']: raise ValueError('关联索引备份已变化：'+entry['backup'])
                document=json.loads(raw.decode('utf-8')) if raw is not None else copy.deepcopy(entry['patches'][0]['default'])
                for item in entry['patches']:
                    if patch_value(document,item['keys']) not in (item['before'],item['after']):
                        raise ValueError('关联记录已变化，拒绝覆盖：'+entry['path'])
                metadata.append((entry,document))
            record.update(status='restoring' if restore else 'applying',error=None)
            atomic_write_json(manifest,record)
            for entry in record['files']:
                desired=entry['before_digest'] if restore else entry['after_digest']
                current=mtp.digest(read(entry['path']))
                if current!=desired:
                    entry['state']='restoring' if restore else 'writing'
                    atomic_write_json(manifest,record)
                    if desired is None:
                        remove_created(entry['path'],entry['after_digest'])
                    else:
                        content=Path(entry['before'] if restore else entry['after']).read_bytes()
                        entry['device_backup']=write_checked(entry['path'],content,current)
                entry['state']='restored' if restore else 'verified'
                atomic_write_json(manifest,record)
            for entry,document in metadata:
                raw=read(entry['path'])
                latest=json.loads(raw.decode('utf-8')) if raw is not None else copy.deepcopy(entry['patches'][0]['default'])
                for item in entry['patches']:
                    if patch_value(latest,item['keys']) not in (item['before'],item['after']):
                        raise ValueError('关联记录在应用期间变化：'+entry['path'])
                    update_patch(latest,item['keys'],item['before'] if restore else item['after'])
                atomic_write_json(entry['path'],latest,expected_digest=mtp.digest(raw) if raw is not None else None)
                entry['state']='restored' if restore else 'verified'
                atomic_write_json(manifest,record)
            record.update(status='restored' if restore else 'applied',error=None)
        except (OSError,ValueError,RuntimeError) as error:
            record.update(status='restore_pending' if restore else 'partial',error=str(error))
        atomic_write_json(manifest,record)
    playlist_change=next((entry for entry in record['files'] if entry['kind']=='playlist'),None)
    count=None
    if playlist_change and record['status'] in {'applied','restored'}:
        snapshot=playlist_change['before'] if record['status']=='restored' else playlist_change['after']
        count=len(json.loads(Path(snapshot).read_text(encoding='utf-8-sig'))['items'])
    return {'playlist_count':count,'operation_id':ident,'status':record['status'],'error':record['error'],
            'backup_directory':str(manifest.parent),'playlist_path':record['playlist']}
