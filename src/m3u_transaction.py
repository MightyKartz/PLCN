"""Guarded metadata transactions. Never remove original disc/save files."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path

import mtp_runtime as mtp
from content_scan import read
from safe_io import atomic_write_bytes, atomic_write_json, file_lock


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


def check_dependencies(dependencies, ignored_paths=(), patches=()):
    from disc_inspection import Reader
    afters={(item['path'],json.dumps(item['keys'])):item['after'] for item in patches}
    for dependency in dependencies:
        path=dependency['path']
        if 'json_guard' in dependency:
            raw=read(path)
            document=json.loads(raw.decode('utf-8')) if raw is not None else dependency['default']
            for item in dependency['json_guard']:
                current=patch_value(document,item['keys'])
                if current!=item['state'] and current!=afters.get((path,json.dumps(item['keys']))):
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


def apply(plan):
    """Apply a confirmed plan: guard dependencies, stage writes, patch indexes."""
    if not plan['can_apply']:
        raise ValueError('请先解决方案中的待处理问题')
    check_dependencies(plan['dependencies'],patches=plan['patches'])
    files=[]
    for change in plan['writes']:
        before=read(change['path'])
        after_digest=mtp.digest(change['content'])
        if mtp.digest(before) not in {change['expected'],after_digest}:
            raise ValueError('文件在预览后已变化，请重新预览：'+change['path'])
        files.append({'path':change['path'],'content':change['content'],
                      'before_digest':mtp.digest(before),'after_digest':after_digest,
                      'kind':change['kind']})
    paths={entry['path'] for entry in files}
    dependencies=[entry for entry in plan['dependencies'] if entry['path'] not in paths]
    metadata=[]
    for path in dict.fromkeys(item['path'] for item in plan['patches']):
        patches=[item for item in plan['patches'] if item['path']==path]
        raw=read(path)
        document=json.loads(raw.decode('utf-8')) if raw is not None else copy.deepcopy(patches[0]['default'])
        for item in patches:
            if patch_value(document,item['keys']) not in (item['before'],item['after']):
                raise ValueError('关联记录已变化，拒绝覆盖：'+path)
        metadata.append((path,patches))
    # Lock metadata together with target files; source discs are read-only dependencies.
    with ExitStack() as locks:
        for path in sorted({entry['path'] for entry in files}|{path for path,_ in metadata}):
            if not mtp.is_mtp(path):
                locks.enter_context(file_lock(path))
        check_dependencies(dependencies,paths,plan['patches'])
        for entry in files:
            current=mtp.digest(read(entry['path']))
            if current not in {entry['before_digest'],entry['after_digest']}:
                raise ValueError('文件在操作后发生变化，拒绝覆盖：'+entry['path'])
        leftovers=[]
        for entry in files:
            current=mtp.digest(read(entry['path']))
            if current!=entry['after_digest']:
                leftover=write_checked(entry['path'],entry['content'],current)
                if leftover: leftovers.append(leftover)
        for path,patches in metadata:
            raw=read(path)
            latest=json.loads(raw.decode('utf-8')) if raw is not None else copy.deepcopy(patches[0]['default'])
            for item in patches:
                if patch_value(latest,item['keys']) not in (item['before'],item['after']):
                    raise ValueError('关联记录在应用期间变化：'+path)
                update_patch(latest,item['keys'],item['after'])
            atomic_write_json(path,latest,expected_digest=mtp.digest(raw) if raw is not None else None)
    playlist_change=next((entry for entry in files if entry['kind']=='playlist'),None)
    count=None
    if playlist_change:
        count=len(json.loads(playlist_change['content'].decode('utf-8-sig'))['items'])
    result={'playlist_count':count,'status':'applied','error':None,'playlist_path':plan['playlist']}
    if leftovers: result['cleanup_warnings']=[('已写入，但旧版本残留未能移除：'+path) for path in leftovers]
    return result
