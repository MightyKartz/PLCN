"""Declared, reviewable descriptor scope. No filename guessing or global deletion claim."""
import copy
import json
from pathlib import Path, PureWindowsPath
import posixpath
import uuid

import app_paths
import chd_io
from content_scan import folders, read, join
from disc_inspection import parse_references, reference_path, Reader
import library_model
import mtp_runtime as mtp
import m3u_transaction as tx
from rom_paths import split_archive

EXTENSIONS={'.lpl','.m3u','.cue','.ccd','.toc','.gdi'}


def scope(roots,playlist,cancelled=lambda: None):
    reader=Reader(playlist);documents={};refs=[];errors=[];directories={};pending=list(roots);seen=set()
    while pending:
        cancelled();directory=pending.pop();directory=chd_io.key(directory)
        if directory in seen: continue
        seen.add(directory);entries=folders(directory)
        relevant=[entry for entry in entries if (entry['folder'] and not entry['name'].startswith(('PLCN-DEPLOY-','PLCN-SOURCES-','PLCN-CHD-','PLCN-ZIP-'))) or
                  (not entry['folder'] and Path(entry['name']).suffix.lower() in EXTENSIONS)]
        directories[directory]=sorted((entry['name'],entry['folder']) for entry in relevant)
        for entry in relevant:
            path=chd_io.key(join(directory,entry['name']));kind=Path(entry['name']).suffix.lower()[1:]
            if entry['folder']: pending.append(path);continue
            if kind in {'ccd','toc','gdi'}: errors.append('未解析描述文件：'+path);continue
            try:
                if entry.get('size') is None or entry['size']>1024*1024: raise ValueError('描述文件超过 1 MiB 或大小未知')
                raw=read(path)
                if raw is None: raise ValueError('描述文件不存在')
                if kind=='lpl':
                    document=json.loads(raw.decode('utf-8-sig'))
                    if not isinstance(document,dict) or not isinstance(document.get('items'),list) or any(not isinstance(item,dict) or not isinstance(item.get('path'),str) for item in document['items']):
                        raise ValueError('游戏列表字段无效')
                    values=[{'value':item['path'],'index':index} for index,item in enumerate(document['items'])]
                else:
                    document=raw.decode('utf-8-sig').splitlines();values,problems=parse_references(raw,kind)
                    if problems: raise ValueError('描述文件引用无法完整解析')
                documents[path]={'kind':kind,'raw':raw,'document':document}
                for value in values:
                    if value['value']=='DETECT' or not value['value']: continue
                    logical=reference_path(path,value['value'])
                    physical,member=split_archive(logical)
                    access=reader.locate(physical)
                    if access is None: raise ValueError('引用缺少设备映射：'+logical)
                    refs.append({'owner':path,'kind':kind,'target':chd_io.key(access),'member':member,**value})
            except (OSError,ValueError,RuntimeError) as error: errors.append(path+' · '+str(error))
    return {'documents':documents,'references':refs,'errors':errors,'directories':directories}


def edits(checked,selections):
    changed={};refs=[];cores=set();reached=set(selections)
    while True:
        parents={ref['owner'] for ref in checked['references'] if ref['kind']=='m3u' and ref['target'] in reached}
        if parents<=reached: break
        reached.update(parents)
    for ref in checked['references']:
        if ref['kind']=='lpl' and ref['target'] in reached:
            document=checked['documents'][ref['owner']]['document'];item=document['items'][ref['index']]
            cores.add(item.get('core_path') or document.get('default_core_path') or 'DETECT')
    for ref in checked['references']:
        selected=selections.get(ref['target'])
        if not selected or ref['kind']=='cue': refs.append(ref);continue
        owner=ref['owner'];original=checked['documents'][owner]
        if owner not in changed: changed[owner]=copy.deepcopy(original['document'])
        if ref['kind']=='lpl':
            item=changed[owner]['items'][ref['index']]
            core=item.get('core_path') or changed[owner].get('default_core_path') or 'DETECT';cores.add(core)
            item['path']=selected['logical']+('#'+member if (member:=selected.get('member',ref.get('member'))) else '')
            if not selected.get('preserve_content'): item['crc32']='DETECT'
        else:
            raw=ref['value'];member=selected.get('member',ref.get('member'));suffix='#'+member if member else ''
            if raw.startswith(('/','mtp://')) or PureWindowsPath(raw).is_absolute(): value=selected['logical']
            else:
                target=selected['target'];parent=owner.rsplit('/',1)[0]
                if mtp.is_mtp(target):
                    if mtp.parse(target)[:2]!=mtp.parse(parent)[:2]: value=selected['logical']
                    else: value=posixpath.relpath('/'.join(mtp.parse(target)[2]),'/'.join(mtp.parse(parent)[2]))
                else: value=posixpath.relpath(target,parent)
            changed[owner][ref['line']-1]=value+suffix
        refs.append({**ref,'target':selected['target'],'member':selected.get('member',ref.get('member'))})
    writes=[]
    for path,document in changed.items():
        raw=(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if checked['documents'][path]['kind']=='lpl' else ('\n'.join(document)+'\n').encode('utf-8')
        before=checked['documents'][path]['raw']
        if raw!=before: writes.append({'path':path,'content':raw,'expected':mtp.digest(before),'kind':'playlist' if path.lower().endswith('.lpl') else 'descriptor'})
    return writes,refs,cores


def associations(checked,selections,system):
    patches=[];guards=[];allocated={};index_path=app_paths.user_data_dir()/'library-identities.json';index=library_model._read_index(index_path)
    memory_path=app_paths.user_data_dir()/'artwork-sources.json';raw=read(str(memory_path));memory=json.loads(raw.decode('utf-8')) if raw else {}
    from artwork_identity import memory_key
    for ref in checked['references']:
        if ref['kind']!='lpl' or ref['target'] not in selections: continue
        chosen=dict(selections[ref['target']]);member=chosen.get('member',ref.get('member'))
        if member: chosen['logical']+='#'+member
        owner=ref['owner'];document=checked['documents'][owner]['document'];item=document['items'][ref['index']]
        source=library_model._source_path(owner);scope=source.rsplit('/',1)[0];locator=item['path'].replace('\\','/')
        content_key=json.dumps([scope,chosen['logical']],ensure_ascii=False,separators=(',',':'))
        old_content_key=json.dumps([scope,locator],ensure_ascii=False,separators=(',',':'))
        old_content=index['content_ids'].get(old_content_key)
        guards.append({'path':str(index_path),'default':index,'json_guard':[{'keys':['content_ids',old_content_key],'state':tx.patch_value(index,['content_ids',old_content_key])}]})
        desired=old_content if chosen.get('preserve_content') else None
        if desired and content_key in index['content_ids'] and index['content_ids'][content_key]!=desired: raise ValueError('目标已绑定其他内容标识')
        content_id=allocated.setdefault(content_key,desired or index['content_ids'].get(content_key) or str(uuid.uuid4()))
        patches.append(tx.patch(index_path,index,['content_ids',content_key],content_id))
        systems={system}
        for key,game_id in index['game_ids'].items():
            parts=json.loads(key)
            if parts[0]!=source or parts[2]!=locator: continue
            systems.add(parts[1])
            guards.append({'path':str(index_path),'default':index,'json_guard':[{'keys':['game_ids',key],'state':tx.patch_value(index,['game_ids',key])}]})
            target=json.dumps([source,parts[1],chosen['logical']],ensure_ascii=False,separators=(',',':'))
            if target in index['game_ids'] and index['game_ids'][target]!=game_id: raise ValueError('目标已绑定其他游戏标识')
            patches.append(tx.patch(index_path,index,['game_ids',target],game_id))
            old_disc=index['disc_ids'].get(json.dumps([game_id,old_content],ensure_ascii=False,separators=(',',':')))
            if old_disc: patches.append(tx.patch(index_path,index,['disc_ids',json.dumps([game_id,content_id],ensure_ascii=False,separators=(',',':'))],old_disc))
        for playlist in {owner,library_model._source_path(owner),str(Path(owner)) if not mtp.is_mtp(owner) else owner}:
            for artwork_system in systems:
                context={'system':artwork_system,'playlist_path':playlist,'rom_path':item['path'],'label':item.get('label','')}
                original_key=memory_key(context)
                old=memory.get(original_key)
                if old:
                    guards.append({'path':str(memory_path),'default':{},'json_guard':[{'keys':[original_key],'state':tx.patch_value(memory,[original_key])}]})
                    key=memory_key({**context,'rom_path':chosen['logical']})
                    if key in memory and memory[key]!=old: raise ValueError('目标已有不同人工图片选择')
                    patches.append(tx.patch(memory_path,{},[key],old))
    groups=library_model.disc_groups();group_path=app_paths.user_data_dir()/'library-disc-groups.json'
    for key,group in groups['groups'].items():
        changed=copy.deepcopy(group)
        for disc in changed['discs']:
            access=Reader(group['playlist']).locate(disc['path'])
            chosen=selections.get(chd_io.key(access)) if access else None
            if not chosen: continue
            disc.setdefault('previous_contents',[]).append({'path':disc['path'],'entry':copy.deepcopy(disc['entry']),'format':disc['format']})
            disc.update(path=chosen['logical'],format=chosen.get('format','chd'))
            entry=disc['entry'];scope=library_model._source_path(group['playlist']).rsplit('/',1)[0]
            target_key=json.dumps([scope,chosen['logical']],ensure_ascii=False,separators=(',',':'))
            desired=entry.get('content_id') if chosen.get('preserve_content') else None
            if desired and target_key in index['content_ids'] and index['content_ids'][target_key]!=desired: raise ValueError('目标已绑定其他盘内容标识')
            content_id=allocated.setdefault(target_key,desired or index['content_ids'].get(target_key) or str(uuid.uuid4()))
            patches.append(tx.patch(index_path,index,['content_ids',target_key],content_id))
            if entry.get('disc_id'): patches.append(tx.patch(index_path,index,['disc_ids',json.dumps([entry['game_id'],content_id],ensure_ascii=False,separators=(',',':'))],entry['disc_id']))
            entry.update(content_id=content_id,launch_path=chosen['logical'])
        original={}
        for path,item in changed.get('original_items',{}).items():
            access=Reader(group['playlist']).locate(path);chosen=selections.get(chd_io.key(access)) if access else None
            if chosen:
                item['path']=chosen['logical'];path=chosen['logical']
                if not chosen.get('preserve_content'): item['crc32']='DETECT'
            original[path]=item
        changed['original_items']=original
        launch=Reader(group['playlist']).locate(group['launch_path'])
        chosen=selections.get(chd_io.key(launch)) if launch else None
        new_key=key
        if chosen:
            changed['launch_path']=chosen['logical']
            content_key=json.dumps([library_model._source_path(group['playlist']).rsplit('/',1)[0],chosen['logical']],ensure_ascii=False,separators=(',',':'))
            changed['launch_content_id']=allocated.setdefault(content_key,group['launch_content_id'] if chosen.get('preserve_content') else str(uuid.uuid4()))
            patches.append(tx.patch(index_path,index,['content_ids',content_key],changed['launch_content_id']))
            parts=json.loads(key);parts[2]=chosen['logical'];new_key=json.dumps(parts,ensure_ascii=False,separators=(',',':'))
            if new_key!=key:
                if new_key in groups['groups']: raise ValueError('目标已有其他多盘分组')
                removal=tx.patch(group_path,{'version':1,'groups':{}},['groups',key],None);removal['after']={'exists':False};patches.append(removal)
        if changed!=group: patches.append(tx.patch(group_path,{'version':1,'groups':{}},['groups',new_key],changed))
    # Repeated references to a disc must share one patch value, not conflicting UUIDs.
    unique={}
    for item in patches:
        key=(item['path'],tuple(item['keys']))
        if key in unique and unique[key]['after']!=item['after']: raise ValueError('多列表身份关联冲突，请重新检查')
        if item['before']!=item['after']: unique[key]=item
    return list(unique.values()),guards
