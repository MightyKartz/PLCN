"""Reviewed ROM moves/ZIP deployments on the shared durable backup engine."""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import tempfile
import uuid
import zipfile

import app_paths
import chd_deploy as engine
import chd_io as io
import chd_references as refs
from content_scan import folders, join, read
from disc_inspection import Reader, parse_references
from m3u_plan import settings, small_file
import mtp_runtime as mtp
import rom_storage


def logical_directory(reader, target):
    if not reader.remote: return io.key(target)
    matches=[]
    for android,source in reader.mappings:
        source=io.key(source)
        if target==source or target.startswith(source+'/'):
            parts=mtp.parse(target)[2][len(mtp.parse(source)[2]):]
            matches.append((len(source),posixpath.join(android,*parts)))
    if not matches: raise ValueError('目标目录缺少 Android 路径映射，请先保存该存储目录的扫描配置')
    length=max(value[0] for value in matches);values={value for size,value in matches if size==length}
    if len(values)!=1: raise ValueError('目标目录存在多个 Android 路径映射')
    logical=values.pop();access=reader.locate(logical)
    if not access or io.key(access)!=target: raise ValueError('目标 Android 路径不能唯一映射回所选目录')
    return logical


def save_check(playlist, cores):
    reader=Reader(playlist);dependencies=[]
    result={'status':'pending','issues':[],'directories':[],'note':'文件与 ZIP 成员主文件名保持不变；只支持已确认的固定全局存档目录，存档和即时存档均不移动。'}
    try:
        raw=small_file(reader,join(playlist.rsplit('/',2)[0],'retroarch.cfg'),dependencies)
        if raw is None: raise ValueError('未找到可读取的 RetroArch 配置，存档位置未知')
        if re.search(r'^\s*#include\b',raw.decode('utf-8-sig'),re.M): raise ValueError('配置包含未读取的 include，存档规则尚未确认')
        config=settings(raw)
        flags=['auto_overrides_enable','game_specific_options','sort_savefiles_enable','sort_savefiles_by_content_enable',
               'savefiles_in_content_dir','sort_savestates_enable','sort_savestates_by_content_enable','savestates_in_content_dir']
        if any(config.get(key)!='false' for key in flags):
            raise ValueError('存档分类／内容目录／配置覆盖设置未明确关闭；仅复制，不能自动切换或清理')
        for key in ['savefile_directory','savestate_directory','core_options_path']:
            path=config.get(key,'')
            if not path.startswith('/') and not PureWindowsPath(path).is_absolute(): raise ValueError('配置缺少明确的绝对路径：'+key)
            access=reader.locate(path)
            if not access: raise ValueError('存档或核心选项目录缺少传输映射：'+path)
            if key=='core_options_path':
                options=small_file(reader,path,dependencies)
                if options is None: raise ValueError('核心选项文件不可读，不能假定共享存档已关闭')
                text=options.decode('utf-8-sig')
                if re.search(r'^\s*#include\b',text,re.M): raise ValueError('核心选项包含 include，尚未确认')
                if any('shared' in name and value not in {'disabled','false','off'} for name,value in settings(options).items()):
                    raise ValueError('核心选项含共享存档设置，请先核对，不能自动切换')
            else:
                entries=folders(access)
                dependencies.append({'path':access,'directory':sorted((entry['name'],entry['folder'],entry.get('size')) for entry in entries)})
                result['directories'].append(path)
        if len(cores)!=1 or any(not re.fullmatch(r'[a-z0-9_]+_libretro(?:_android)?\.(?:so|dll|dylib)',str(core).replace('\\','/').rsplit('/',1)[-1]) for core in cores):
            raise ValueError('受影响入口必须使用同一明确核心；不更换人工核心设置')
        result['status']='checked'
    except (OSError,ValueError,RuntimeError) as error: result['issues'].append(str(error))
    return result,dependencies


def prepare(payload, analysis=None, cancelled=lambda: None, progress=lambda message: None):
    if payload.get('operation_id'):
        prior=json.loads(engine.receipt(payload['operation_id']).read_text(encoding='utf-8'))
        if prior.get('kind')!='rom_relocation' or prior['status']!='completed' or prior['mode']!='copy': raise ValueError('只有已完成的复制操作可重新预览切换；其他操作请先恢复或重新分析')
        analysis=prior.get('origin_analysis');payload={**payload,'conversion_id':prior['conversion_id']}
    selected=payload.get('file_ids');mode=payload.get('mode','copy');runtime=payload.get('runtime',{})
    if (not isinstance(selected,list) or not selected or any(not isinstance(value,str) for value in selected)
            or len(set(selected))!=len(selected) or not isinstance(mode,str) or mode not in {'copy','switch','replace'}
            or not isinstance(runtime,dict) or not isinstance(runtime.get('version',''),str)
            or not isinstance(runtime.get('confirmed',False),bool) or not isinstance(payload.get('scope_confirmed',False),bool)):
        raise ValueError('请选择文件、执行方式和有效的运行报告')
    operation=uuid.uuid4().hex;issues=[];copies=[];sources={};selections={};zip_mode=analysis is None
    if zip_mode:
        conversion_id=payload.get('conversion_id');engine.receipt(conversion_id)
        record=json.loads((app_paths.user_data_dir()/'rom-storage'/conversion_id/'manifest.json').read_text(encoding='utf-8'))
        rows={entry.get('id') or hashlib.sha256(io.key(entry['source']).encode()).hexdigest()[:24]:entry for entry in record['results'] if entry.get('verification')=='byte_for_byte'}
        playlist=record['playlist'];system=record['system'];workspace=Path(record.get('workspace') or Path(record['output_directory']).parent)
    else:
        conversion_id=None;playlist=analysis['playlist'];system=analysis['system'];workspace=Path(analysis['workspace'])
        if io.digest(playlist,cancelled)!=analysis['playlist_sha256']: raise ValueError('列表已变化，请重新分析目录')
        rows={row['id']:row for row in analysis['rows']}
    if not set(selected)<=set(rows): raise ValueError('选择已失效，请重新分析')
    selected=set(selected)
    if not zip_mode:
        for ident in list(selected): selected.update(rows[ident].get('members',[]))
    reader=Reader(playlist)
    target_directories={}
    for ident in sorted(selected):
        cancelled();row=rows[ident];source=io.key(row['source'])
        if source!=row['source']: raise ValueError('源路径已改变，请重新分析：'+row['source'])
        extension=PurePosixPath(source).suffix.lower().lstrip('.')
        if not zip_mode and row['layout'] not in {'candidate','conflict','already_flat'}: raise ValueError('多文件例外不能移动：'+source)
        target_root=(record.get('target_directory') or source.rsplit('/',1)[0]) if zip_mode else analysis['target_directory']
        target_root=io.key(target_root)
        if target_root not in target_directories: target_directories[target_root]=folders(target_root)
        name=PurePosixPath(row['member']).stem+'.zip' if zip_mode else row['name']
        target=io.key(join(target_root,name))
        if target==source: continue
        progress('核对原文件与目标：'+source)
        sha=io.digest(source,cancelled)
        if not sha or (row.get('source_sha256') or row.get('sha256')) not in {None,sha}: raise ValueError('源文件已变化：'+source)
        state=reader.probe(source)
        if state['status']!='present' or state['size'] is None: raise ValueError('原文件不可读：'+source)
        sources[source]={'path':source,'size':state['size'],'sha256':sha}
        if re.search('[\r\n]',name): raise ValueError('文件名含换行，无法联动 M3U')
        logical=target if mode=='copy' and reader.remote else posixpath.join(logical_directory(reader,target_root),name)
        chosen={'target':target,'logical':logical,'format':'zip' if zip_mode else extension,'preserve_content':not zip_mode}
        if zip_mode:
            if io.digest(row['output'],cancelled)!=row['sha256']: raise ValueError('电脑 ZIP 已变化')
            with zipfile.ZipFile(row['output']) as zipped:
                if zipped.namelist()!=[row['member']] or PurePosixPath(row['member']).name!=row['member'] or '\\' in row['member']: raise ValueError('ZIP 必须仅含原文件名的单个 ROM')
                if PurePosixPath(row['member']).stem!=PurePosixPath(name).stem: raise ValueError('ZIP 主文件名不一致，不能保持存档名称')
                digest=hashlib.sha256()
                with zipped.open(row['member']) as member:
                    while True:
                        cancelled();chunk=member.read(1024*1024)
                        if not chunk: break
                        digest.update(chunk)
                if digest.hexdigest()!=sha: raise ValueError('ZIP 解压内容与原 ROM 不一致')
            chosen['member']=row['member']
        selections[source]=chosen
        copies.append({'original_source':source,'source':row['output'] if zip_mode else source,'target':target,'logical':logical,
                       'sha256':row['sha256'] if zip_mode else sha,'size':row['output_bytes'] if zip_mode else state['size'],
                       'created':True,'stage':target+'.plcn-'+operation+'.tmp'})
    if not copies: raise ValueError('没有需要整理或回传的文件')
    if len({item['target'].casefold() for item in copies})!=len(copies): issues.append('所选文件在目标目录重名，请排除冲突后重新预览')
    roots={source.rsplit('/',1)[0] for source in sources}|{io.key(playlist).rsplit('/',1)[0],*target_directories}
    if analysis: roots.add(analysis['source_directory'])
    roots=sorted(root for root in roots if not any(root.startswith(other+'/') for other in roots if other!=root))
    checked=refs.scope(roots,playlist,cancelled)
    if any(ref['kind']=='cue' and ref['target'] in selections for ref in checked['references']): issues.append('文件被 CUE 引用，必须保留多文件目录关系')
    writes,after_refs,cores=refs.edits(checked,selections)
    for item in copies:
        original=checked['documents'].get(item['source'])
        if original and original['kind']=='m3u':
            _,errors=parse_references(original['raw'],'m3u')
            if errors: raise ValueError('M3U 无法完整解析')
            if not analysis or not rows[next(key for key in selected if rows[key]['source']==item['source'])].get('members'):
                raise ValueError('仅整理已核对的独立 CHD 多盘入口')
            lines=list(original['document'])
            for ref in [entry for entry in checked['references'] if entry['owner']==item['source']]:
                chosen=selections.get(ref['target']);destination=chosen['target'] if chosen else ref['target']
                if mtp.is_mtp(destination):
                    if mtp.parse(destination)[:2]!=mtp.parse(item['target'])[:2]: raise ValueError('M3U 目标与盘文件不在同一存储')
                    value=posixpath.relpath('/'.join(mtp.parse(destination)[2]),'/'.join(mtp.parse(item['target'])[2][:-1]))
                else: value=posixpath.relpath(destination,item['target'].rsplit('/',1)[0])
                lines[ref['line']-1]=value
            content=('\n'.join(lines)+'\n').encode('utf-8')
            item.update(content_base64=base64.b64encode(content).decode(),sha256=mtp.digest(content),size=len(content))
            writes=[entry for entry in writes if entry['path']!=item['source']]
            for ref in after_refs:
                if ref['owner']==item['source']: ref['owner']=item['target']
    previous=engine.history()
    for item in copies:
        name=mtp.parse(item['target'])[2][-1] if mtp.is_mtp(item['target']) else Path(item['target']).name
        entries=target_directories[item['target'].rsplit('/',1)[0]]
        folder_conflict=any(entry['name']==name and entry['folder'] for entry in entries)
        if folder_conflict: issues.append('目标已有同名目录，不覆盖：'+item['target'])
        current=None if folder_conflict else io.digest(item['target'],cancelled)
        if current is not None:
            owned=any(record.get('kind')=='rom_relocation' and record['status']=='completed' and any(
                value['target']==item['target'] and value['sha256']==item['sha256'] and value.get('original_source')==item['original_source'] for value in record['copies']) and any(
                value['path']==item['original_source'] and value['sha256']==sources[item['original_source']]['sha256'] for value in record['sources']) for record in previous)
            if current!=item['sha256'] or not owned: issues.append('目标已存在，不覆盖或合并：'+item['target'])
            item['created']=False
        for entry in entries:
            if entry['name'].casefold()==name.casefold() and entry['name']!=name:
                issues.append('目标存在大小写冲突：'+item['target'])
    saves,dependencies=save_check(playlist,cores) if mode!='copy' else ({'status':'not_required','issues':[],'directories':[]},[])
    if mode!='copy':
        issues.extend(checked['errors']);issues.extend(saves['issues'])
        if not runtime.get('version','').strip() or runtime.get('confirmed') is not True: issues.append('请先以复制模式生成目标，再用原核心验证目标路径、游戏内存档和多盘换盘，填写核心版本运行报告')
        if payload.get('scope_confirmed') is not True: issues.append('请确认预览目录包含全部相关列表和描述文件，并已退出 RetroArch')
        if zip_mode:
            for core in cores:
                ident=next((key for key in rom_storage.ZIP_CORES if re.fullmatch(re.escape(key)+r'_libretro(?:_android)?\.(?:so|dll|dylib)',core.replace('\\','/').rsplit('/',1)[-1])),None)
                if not ident or any(PurePosixPath(value['member']).suffix.lower()[1:] not in rom_storage.ZIP_CORES[ident][0] for value in selections.values()): issues.append('受影响列表的核心 ZIP 解包支持未核对')
    patches,guards=refs.associations(checked,selections,system) if mode!='copy' else ([],[])
    retained=[];deletions=[]
    for source,file in sources.items():
        consumers=sorted({ref['owner'] for ref in after_refs if ref['target']==source and ref['owner'] not in selections})
        if consumers: retained.append({'path':source,'consumers':consumers})
        elif mode=='replace': deletions.append(file)
    backup=workspace/('PLCN-DEPLOY-'+operation);requirements={}
    def reserve(path,size):
        value=requirements.setdefault(io.volume(path),{'path':path,'bytes':0});value['bytes']+=size
    for item in copies:
        if item['created']: reserve(item['target'],item['size'])
    for write in writes if mode!='copy' else []: reserve(write['path'],len(write['content']))
    computer=sum(item['size'] for item in copies)+(sum(file['size'] for file in sources.values()) if mode!='copy' else 0)
    reserve(str(backup),computer)
    reserve(str(app_paths.user_data_dir()/'metadata-probe'),sum(len(checked['documents'][write['path']]['raw'])+len(write['content']) for write in writes) if mode!='copy' else 0)
    temporary=max([file['size'] for file in sources.values()]+[item['size'] for item in copies])
    if reader.remote: reserve(str(Path(tempfile.gettempdir())/'verify-probe'),temporary)
    capacity=[]
    for value in requirements.values():
        free=io.free_bytes(value['path']);required=value['bytes']+engine.RESERVE
        capacity.append({'path':value['path'],'required':required,'free':free})
        if free<required: issues.append('目标或电脑空间不足：'+value['path'])
    snapshot={'directories':{path:[list(value) for value in entries] for path,entries in checked['directories'].items()},
              'documents':{path:mtp.digest(value['raw']) for path,value in checked['documents'].items()}}
    metadata={'can_apply':True,'playlist':playlist,'label':'目录整理／ZIP 引用更新','mode':'rom_references',
              'writes':writes if mode!='copy' else [],'patches':patches,'dependencies':dependencies+guards}
    return {'id':operation,'origin_analysis':analysis,'selected_ids':sorted(selected),'kind':'rom_relocation','conversion_id':conversion_id,'playlist':playlist,'system':system,'mode':mode,
            'copies':copies,'sources':list(sources.values()),'deletions':deletions,'retained':retained,'backup_directory':str(backup),
            'roots':roots,'scope_snapshot':snapshot,'scope_errors':checked['errors'],'runtime':{'cores':sorted(cores),'version':runtime.get('version',''),'confirmed':runtime.get('confirmed') is True,'source':'user_reported'},
            'saves':saves,'metadata_plan':metadata,'capacity':capacity,'computer_required':computer,'temporary_required':temporary,
            'reference_changes':[{'path':write['path'],'bytes':len(write['content'])} for write in metadata['writes']],
            'image_delta_bytes':sum(file['size'] for file in deletions)-sum(item['size'] for item in copies if item['created']),
            'issues':list(dict.fromkeys(issues)),'can_apply':not issues}
