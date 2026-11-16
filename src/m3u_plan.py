"""M3U review plans: explicit disc selection/order, guarded playlist and save linkage."""
import copy
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import uuid

import app_paths
import core_catalog
import library_model
import mtp_runtime as mtp
from artwork_identity import memory_key
from content_scan import read, folders, join
from disc_inspection import inspect_discs, Reader, METADATA_LIMIT
from m3u_transaction import patch, operations_dir, patch_value
from rom_paths import rom_title

SAVE_SUFFIXES={'mednafen_saturn':['.bkr','.bcr','.smpc'], 'mednafen_psx':['.srm','.0.mcr','.1.mcr'],
               'mednafen_psx_hw':['.srm','.0.mcr','.1.mcr'],'pcsx_rearmed':['.srm']}
CORE_IDS=set(SAVE_SUFFIXES)|{'swanstation','yabause'}


def core_support(path):
    name=str(path).replace('\\','/').rsplit('/',1)[-1]
    core=next((value for value in CORE_IDS if re.fullmatch(re.escape(value)+r'_libretro(?:_android)?\.(?:so|dylib|dll)',name)),None)
    if not core:
        return {'id':None,'extensions':[],'message':'原核心无法识别，未改变核心；切换列表前需核对 M3U 支持'}
    try:
        if core in core_catalog.scan.CORE_NAMES:
            info=core_catalog.info(core)
        else:
            url='https://raw.githubusercontent.com/libretro/libretro-core-info/master/'+core+'_libretro.info'
            raw=core_catalog.official_get(url).decode('utf-8-sig')
            found=re.search(r'^supported_extensions\s*=\s*"([^"\n]*)"',raw,re.M)
            if not found: raise ValueError('官方核心信息缺少格式字段')
            info={'source':url,'extensions':found[1].split('|')}
        return {'id':core,**info,'message':'官方格式声明已核对；安装版本与掌机运行尚未验证'}
    except (OSError,ValueError,RuntimeError) as error:
        return {'id':core,'extensions':[],'message':'无法核对核心格式：'+str(error)}


def settings(content):
    return dict(re.findall(r'^\s*([A-Za-z0-9_]+)\s*=\s*"([^"\r\n]*)"\s*(?:#.*)?$',content.decode('utf-8-sig'),re.M))


def small_file(reader,logical,dependencies,limit=METADATA_LIMIT):
    location=reader.locate(logical)
    state=reader.probe(location)
    if state['status']=='missing':
        dependencies.append({'path':location,'digest':None})
        return None
    if state['status']!='present' or state['size'] is None or state['size']>limit:
        raise ValueError('无法在范围内读取：'+logical+' · '+state['message'])
    content=read(location)
    if content is None: raise ValueError('文件已变化：'+logical)
    dependencies.append({'path':location,'digest':mtp.digest(content)})
    return content


def save_linkage(reader,playlist,core,paths,target,source,keep_states,dependencies):
    result={'status':'pending','issues':[],'copies':[],'states':[],'writes':[]}
    root=playlist.rsplit('/',2)[0]
    try:
        raw=small_file(reader,join(root,'retroarch.cfg'),dependencies)
        if raw is None: raise ValueError('未找到可访问的 RetroArch 配置，存档位置尚未确认')
        config=settings(raw)
        suffixes=SAVE_SUFFIXES.get(core)
        if suffixes is None: raise ValueError('当前核心的存档衔接规则尚未确认')
        if config.get('auto_overrides_enable')!='false' or config.get('game_specific_options')!='false':
            raise ValueError('请先在 RetroArch 中关闭并保存自动配置覆盖与按游戏核心选项，避免未读取的覆盖设置改变存档规则')
        flags=['sort_savefiles_enable','sort_savefiles_by_content_enable','savefiles_in_content_dir',
               'sort_savestates_enable','sort_savestates_by_content_enable','savestates_in_content_dir']
        if any(config.get(key,'false')!='false' for key in flags):
            raise ValueError('当前使用了分目录／内容目录存档设置，尚不能自动迁移')
        directories=[config.get('savefile_directory',''),config.get('savestate_directory','')]
        if any(not value.startswith('/') and not PureWindowsPath(value).is_absolute() for value in directories):
            raise ValueError('配置未给出明确的存档与即时存档绝对目录')
        options_path=config.get('core_options_path','')
        if not options_path.startswith('/') and not PureWindowsPath(options_path).is_absolute():
            raise ValueError('核心选项文件位置未确认，不能假定使用默认或非共享存档规则')
        if options_path:
            options_raw=small_file(reader,options_path,dependencies)
            options=settings(options_raw) if options_raw is not None else {}
            prefix='beetle_saturn_' if core=='mednafen_saturn' else 'beetle_psx_' if core.startswith('mednafen_psx') else core+'_'
            if any(key.startswith(prefix) and 'shared' in key and value not in {'disabled','false'} for key,value in options.items()):
                raise ValueError('检测到共享存档选项，需先手动核对核心存档规则')
        saves,states=directories
        save_location,state_location=reader.locate(saves),reader.locate(states)
        if not save_location or not state_location: raise ValueError('存档目录缺少设备传输映射，尚未检查')
        save_entries, state_entries=folders(save_location),folders(state_location)
        for directory,entries in [(save_location,save_entries),(state_location,state_entries)]:
            dependencies.append({'path':directory,'directory':sorted((entry['name'],entry['folder'],entry.get('size')) for entry in entries)})
        stems={rom_title(path) for path in paths}|{rom_title(target)}
        result['states']=[entry['name'] for entry in state_entries if not entry['folder']
                          and any(entry['name'].startswith(stem+'.state') for stem in stems)]
        if result['states'] and not keep_states:
            result['issues'].append('发现即时存档；请明确选择保留原文件、不迁移即时存档，再从游戏内存档继续')
        found_game_save=False
        for suffix in suffixes:
            candidates=[]
            for path in paths:
                name=rom_title(path)+suffix
                if source and path!=source: continue
                if any(entry['name']==name and not entry['folder'] for entry in save_entries):
                    logical=posixpath.join(saves,name)
                    content=small_file(reader,logical,dependencies,8*1024*1024)
                    candidates.append((logical,content))
            if not candidates: continue
            found_game_save=True
            if len({mtp.digest(content) for _,content in candidates})>1:
                result['issues'].append('多盘保存了不同的 '+suffix+' 存档，请选择要延续的那张盘')
                continue
            old,content=candidates[0]
            destination=posixpath.join(saves,rom_title(target)+suffix)
            current=small_file(reader,destination,dependencies,8*1024*1024)
            if current is not None and current!=content:
                result['issues'].append('目标已有不同存档，不覆盖：'+destination);continue
            if current!=content:
                result['writes'].append({'path':reader.locate(destination),'content':content,'expected':mtp.digest(current),'kind':'save_copy'})
                result['copies'].append({'source':old,'target':destination,'size':len(content)})
        if result['states'] and not found_game_save:
            result['issues'].append('存在即时存档但未找到游戏内存档，无法确认进度衔接；请先在游戏内保存或仅保存 M3U')
        result['status']='pending' if result['issues'] else 'checked'
        result['directories']=directories
        result['note']='只复制已识别的游戏内存档，原存档保留；即时存档不迁移、不声明兼容'
    except (OSError,ValueError,RuntimeError) as error:
        result['issues'].append(str(error))
    return result


def prepare(payload):
    playlist,system=payload.get('playlist_path'),payload.get('system')
    selected=payload.get('disc_ids');mode=payload.get('mode','switch')
    label=payload.get('label','');filename=payload.get('filename','')
    if (not all(isinstance(value,str) and value for value in (playlist,system,payload.get('group_id')))
            or not isinstance(mode,str) or not isinstance(payload.get('thumbnails',''),str)
            or not isinstance(selected,list) or len(selected)<2 or any(not isinstance(value,str) for value in selected)
            or len(set(selected))!=len(selected) or mode not in {'switch','file'} or not isinstance(label,str) or not label.strip()
            or not isinstance(filename,str) or not filename.lower().endswith('.m3u') or filename in {'.m3u','..m3u'}
            or re.search(r'[<>:"/\\|?*\x00\r\n]',filename) or not isinstance(payload.get('preserve_states',False),bool)):
        raise ValueError('请选择至少两张不重复光盘、显示名称和有效的 M3U 文件名')
    graph=inspect_discs(playlist,system)
    playlist=graph['playlist_path']
    group=next((group for group in graph['groups'] if group['id']==payload.get('group_id')),None)
    if not group or not set(selected)<=set(group['discs']): raise ValueError('游戏组已变化，请重新打开多盘检查')
    files={file['id']:file for file in graph['files']};discs=[files[value] for value in selected]
    first=files[group['members'][0]]
    reader=Reader(playlist);dependencies=[];issues=[];notes=[]
    paths=[file['path'] for file in discs]
    save_paths=list(dict.fromkeys(([first['path']] if group['kind']=='m3u' else [])+paths))
    source=payload.get('save_source') or ''
    if isinstance(source,str): source=source.replace('\\','/')
    if not isinstance(source,str) or source and source not in save_paths: raise ValueError('请选择当前组内的存档来源盘')
    if any(re.search(r'[\r\n]',path) for path in paths): raise ValueError('M3U 不支持含换行的文件名')
    variants={(file['disc']['family'].casefold(),tuple(file['disc']['regions']),tuple(file['disc']['editions'])) for file in discs}
    numbers=[file['disc']['number'] for file in discs]
    if len(variants)!=1 or any(file['disc']['role']!='game' or file['disc']['ambiguous_marker'] for file in discs):
        issues.append('所选光盘的游戏／地区／修订／汉化标记不一致，或包含特殊盘，请调整选择')
    if len([value for value in numbers if value is not None])!=len(set(value for value in numbers if value is not None)):
        issues.append('所选光盘存在重复盘号，请拆分选择')
    declared={file['disc']['total'] for file in discs if file['disc']['total'] is not None}
    expected=max([value for value in numbers if value is not None]+list(declared),default=0)
    if set(range(1,expected+1))-set(numbers) or len(declared)>1: issues.append('所选光盘存在已知缺盘／总数冲突，请补齐后再预览')
    if not declared: notes.append('未声明总盘数，请核对所选集合是否完整；不会把未知总盘数视为已验证')
    outgoing={}
    for edge in graph['references']: outgoing.setdefault(edge['source'],[]).append(edge['target'])
    reached=set();pending=list(selected)
    while pending:
        value=pending.pop()
        if value in reached: continue
        reached.add(value);pending.extend(outgoing.get(value,[]))
    for ident in reached:
        file=files[ident];location=reader.locate(file['path'])
        if file['status']!='present' or file['issues'] or file['format'] not in {'chd','cue','bin','img','wav','flac','raw'}:
            issues.append('引用文件尚未通过检查：'+file['path']);continue
        if file['format']=='cue': small_file(reader,file['path'],dependencies)
        else: dependencies.append({'path':location,'logical':file['path'],'playlist':playlist,'size':file['size']})
    parent=posixpath.dirname(first['path'] if group['kind']=='m3u' else paths[0])
    target=mtp.join(parent,filename) if mtp.is_mtp(parent) else posixpath.join(parent,filename)
    location=reader.locate(target)
    if not location: raise ValueError('M3U 目标位置缺少唯一传输映射')
    if reader.remote and any(mtp.parse(reader.locate(path))[:2]!=mtp.parse(location)[:2] for path in paths):
        raise ValueError('一个 M3U 不能跨不同设备或存储生成相对路径')
    if not reader.remote and any(PureWindowsPath(path).drive!=PureWindowsPath(target).drive for path in paths):
        raise ValueError('M3U 与光盘必须在相同卷上')
    relative_parent='/'.join(mtp.parse(parent)[2]) if mtp.is_mtp(parent) else parent
    content=('\n'.join(posixpath.relpath('/'.join(mtp.parse(path)[2]) if mtp.is_mtp(path) else path,relative_parent) for path in paths)+'\n').encode('utf-8')
    if group['kind']=='m3u': small_file(reader,first['path'],dependencies)
    if mode=='switch' and reader.remote and mtp.is_mtp(target): issues.append('原入口使用传输地址，需先恢复掌机实际启动路径后再切换列表')
    old=read(location)
    if old is not None and old!=content and (group['kind']!='m3u' or reader.locate(first['path'])!=location):
        issues.append('目标已有不同 M3U，拒绝覆盖；请更换文件名')
    for entry in folders(reader.locate(parent)):
        if entry['name'].casefold()==filename.casefold() and entry['name']!=filename:
            issues.append('目标已有大小写不同的同名文件，请更换文件名')
    playlist_raw=read(playlist);document=json.loads(playlist_raw.decode('utf-8-sig'))
    records=[entry for entry in graph['entries'] if entry['node_id'] in set(selected)|({first['id']} if group['kind']=='m3u' else set())]
    if not records: raise ValueError('当前列表没有可关联的原入口')
    for record in records:
        item=document['items'][record['index']]
        if item.get('path')!=record['launch_path'] or (item.get('label') or rom_title(item.get('path')))!=record['label']:
            raise ValueError('原列表已变化，请重新检查')
    anchor=next((entry for entry in records if group['kind']=='m3u' and entry['node_id']==first['id']),min(records,key=lambda entry:entry['index']))
    cores={entry['core_path'] for entry in records}
    core=core_support(anchor['core_path']) if mode=='switch' else {'id':None,'extensions':[],
        'message':'本次仅保存 M3U，未更换或验证核心；使用前请核对当前核心支持'}
    core_ok=len(cores)==1 and 'm3u' in core['extensions'] and all(file['format'] in core['extensions'] for file in discs)
    if not core_ok and mode=='switch': notes.append('原核心尚未确认同时支持所选格式与 M3U；不自动更换核心')
    saves=save_linkage(reader,playlist,core['id'],save_paths,target,source,payload.get('preserve_states',False),dependencies) if mode=='switch' else {
        'status':'not_requested','issues':[],'copies':[],'states':[],'writes':[],'note':'只保存 M3U，不切换列表或迁移存档'}
    if mode=='switch':
        if not core_ok: issues.append(core['message'])
        issues.extend(saves['issues'])
        if graph['coverage']['errors']: issues.append('当前列表目录的引用覆盖不完整，请先处理读取失败')
    writes=[] if old==content else [{'path':location,'content':content,'expected':mtp.digest(old),'kind':'m3u'}]
    patches=[];removed=[];retained_discs=[];artwork_copies=[]
    if mode=='switch':
        replacement=copy.deepcopy(document['items'][anchor['index']])
        replacement.update(path=target,label=label.strip(),crc32='DETECT')
        covered=set(selected)
        for ident in reached:
            if files[ident]['format'] in {'bin','img','raw','wav','flac'}: covered.add(ident)
        if group['kind']=='m3u': covered.add(first['id'])
        removed=[entry for entry in graph['entries'] if entry['node_id'] in covered]
        if any(reader.locate(item.get('path',''))==location and index not in {entry['index'] for entry in removed} for index,item in enumerate(document['items'])):
            issues.append('目标 M3U 已有独立入口，请重新检查后使用其现有游戏组')
        source_path=library_model._source_path(playlist)
        stored=library_model.disc_groups()
        old_key=json.dumps([source_path,system,first['path']],ensure_ascii=False,separators=(',',':'))
        previous=stored['groups'].get(old_key,{})
        original_items=copy.deepcopy(previous.get('original_items',{}))
        for entry in removed:
            if entry['node_id']!=first['id'] or group['kind']!='m3u':
                original_items.setdefault(entry['launch_path'],copy.deepcopy(document['items'][entry['index']]))
        retained_discs=[]
        if group['kind']=='m3u':
            listed={entry['node_id'] for entry in graph['entries']}
            for ident in group['discs']:
                if ident in selected or ident in listed: continue
                retained=copy.deepcopy(original_items.get(files[ident]['path']))
                if retained is None:
                    retained=copy.deepcopy(replacement)
                    retained.update(path=files[ident]['path'],label=rom_title(files[ident]['path']),crc32='DETECT')
                retained_discs.append(retained)
        indices={entry['index'] for entry in removed};output=[]
        for index,item in enumerate(document['items']):
            if index==min(indices): output.extend([replacement,*retained_discs])
            if index not in indices: output.append(item)
        changed=copy.deepcopy(document);changed['items']=output
        writes.extend(saves['writes'])
        after=(json.dumps(changed,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        if after!=playlist_raw: writes.append({'path':playlist,'content':after,'expected':mtp.digest(playlist_raw),'kind':'playlist'})
        bindings=library_model.build_library_model(playlist,system,[{'path':path,'label':rom_title(path)} for path in paths])['entries']
        artwork_copies=[]
        thumbnails=payload.get('thumbnails') or ''
        if not isinstance(thumbnails,str): raise ValueError('图片目录无效')
        if thumbnails:
            from playlist_browser import open_artwork_reader, artwork_statuses
            from artwork_resolver import sanitize_filename
            resolver,lookups,image_error=open_artwork_reader(thumbnails,system)
            if image_error: issues.append('无法检查原图片：'+image_error)
            images=artwork_statuses(anchor['label'],anchor['launch_path'],resolver,lookups,thumbnails,system)
            for kind,image in images.items():
                if image['status']!='exists': continue
                destination=join(thumbnails,system,kind,sanitize_filename(label.strip())+'.png')
                source_image=image['path']
                image_data=small_file(reader,source_image,dependencies,8*1024*1024)
                access=reader.locate(destination)
                if not access: issues.append('新入口图片位置缺少映射：'+destination);continue
                existing=read(access)
                if existing is not None and existing!=image_data:
                    issues.append('新入口已有不同图片，保留原记录不覆盖：'+destination);continue
                if existing!=image_data:
                    writes.append({'path':access,'content':image_data,'expected':mtp.digest(existing),'kind':'artwork_copy'})
                    artwork_copies.append({'source':source_image,'target':destination})
        else:
            notes.append('未指定图片目录；保留图片选择记录，未检查新入口的图片文件')
        source_path=library_model._source_path(playlist);scope=source_path.rsplit('/',1)[0]
        index_path=app_paths.user_data_dir()/'library-identities.json'
        index=library_model._read_index(index_path)
        source_keys=[]
        for original in [*paths,anchor['launch_path']]:
            locator=original.replace('\\','/')
            source_keys.extend([['game_ids',json.dumps([source_path,system,locator],ensure_ascii=False,separators=(',',':'))],
                                ['content_ids',json.dumps([scope,locator],ensure_ascii=False,separators=(',',':'))]])
        dependencies.append({'path':str(index_path),'default':index,'json_guard':[{'keys':keys,'state':patch_value(index,keys)} for keys in source_keys]})
        game_key=json.dumps([source_path,system,target.replace('\\','/')],ensure_ascii=False,separators=(',',':'))
        content_key=json.dumps([scope,target.replace('\\','/')],ensure_ascii=False,separators=(',',':'))
        content_id=index['content_ids'].get(content_key) or str(uuid.uuid4())
        patches.extend([patch(index_path,index,['game_ids',game_key],anchor['game_id']),patch(index_path,index,['content_ids',content_key],content_id)])
        group_path=app_paths.user_data_dir()/'library-disc-groups.json'
        previous_discs={disc['path']:disc for disc in previous.get('discs',[])}
        membership={'game_id':anchor['game_id'],'playlist':source_path,'launch_path':target,'launch_content_id':content_id,
                    'discs':[{'id':file['id'],'path':file['path'],'format':file['format'],'number':file['disc']['number'],
                              'entry':next((entry for entry in graph['entries'] if entry['node_id']==file['id']),
                                           previous_discs.get(file['path'],{}).get('entry') or
                                           {**bindings[index],'label':rom_title(file['path']),'launch_path':file['path'],'core_path':anchor['core_path']})} for index,file in enumerate(discs)],
                    'original_entries':previous.get('original_entries',records),'original_items':original_items}
        group_key=json.dumps([source_path,system,target],ensure_ascii=False,separators=(',',':'))
        patches.append(patch(app_paths.user_data_dir()/'library-disc-groups.json',{'version':1,'groups':{}},['groups',group_key],membership))
        memory_path=app_paths.user_data_dir()/'artwork-sources.json'
        chosen=anchor.get('artwork_sources') or {}
        if chosen:
            key=memory_key({'system':system,'playlist_path':playlist,'rom_path':target,'label':label.strip()})
            existing=read(str(memory_path));memory=json.loads(existing.decode('utf-8')) if existing is not None else {}
            old_memory_key=memory_key({'system':system,'playlist_path':playlist,'rom_path':anchor['launch_path'],'label':anchor['label']})
            dependencies.append({'path':str(memory_path),'default':{},'json_guard':[{'keys':[old_memory_key],'state':patch_value(memory,[old_memory_key])}]})
            choice={'name':next(iter(chosen.values())),'sources':chosen}
            if key in memory and memory[key]!=choice: issues.append('M3U 已保存不同图片选择，请先核对，不覆盖人工记录')
            else: patches.append(patch(memory_path,{},[key],choice))
    patches=[item for item in patches if item['before']!=item['after']]
    for path in {entry['playlist'] for file in graph['files'] for entry in file['playlist_references']}:
        dependencies.append({'path':path,'digest':mtp.digest(read(path))})
    affected=sorted({entry['playlist'] for file in graph['files'] if reader.locate(file['path'])==location for entry in file['playlist_references']})
    return {'playlist':playlist,'system':system,'label':label.strip(),'mode':mode,'target':target,'target_access':location,
            'content':content.decode('utf-8'),'disc_paths':paths,'core':core,'saves':saves,'issues':list(dict.fromkeys(issues)),
            'backup_root':str(operations_dir()),'notes':notes+['原光盘、音轨、存档、即时存档和其他列表条目均保留；运行与换盘仍需真机验证',
                           '即时存档不迁移，未验证与新入口或新盘序兼容'],
            'removed_indices':[entry['index'] for entry in removed],'retained_discs':retained_discs,'artwork_copies':artwork_copies,'affected_playlists':affected,
            'can_apply':not issues and bool(writes or patches),'writes':writes,'patches':patches,'dependencies':dependencies}


def public(plan):
    return {key:value for key,value in plan.items() if key not in {'writes','patches','dependencies'}} | {
        'saves':{key:value for key,value in plan['saves'].items() if key!='writes'},
        'changes':[{'path':entry['path'],'kind':entry['kind'],'size':len(entry['content'])} for entry in plan['writes']]}
