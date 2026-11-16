"""Stage 4A: read-only layout proposals and verified cartridge ZIP copies.

No source, playlist, save, artwork or device is ever written by this module.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid
import zipfile

import app_paths
import chd_io as io
from content_scan import folders, join, read
from disc_inspection import Reader, METADATA_LIMIT, parse_references, reference_path
import mtp_runtime as mtp
from safe_io import atomic_write_json
from task_control import TaskCancelled

CARTRIDGES = {
    'Nintendo - Nintendo Entertainment System': {'nes', 'unf', 'unif'},
    'Nintendo - Super Nintendo Entertainment System': {'sfc', 'smc'},
    'Nintendo - Game Boy': {'gb'},
    'Nintendo - Game Boy Color': {'gb', 'gbc'},
    'Nintendo - Game Boy Advance': {'gba'},
    'Sega - Mega Drive - Genesis': {'md', 'gen', 'smd', 'bin'},
}
ALIASES = {'NES':'Nintendo - Nintendo Entertainment System',
           'SNES':'Nintendo - Super Nintendo Entertainment System',
           'GB':'Nintendo - Game Boy','GBC':'Nintendo - Game Boy Color',
           'GBA':'Nintendo - Game Boy Advance','MD':'Sega - Mega Drive - Genesis',
           'SS':'Sega - Saturn','PS1':'Sony - PlayStation'}
OPTICAL = {'Sega - Saturn', 'Sony - PlayStation'}
# Official retro_get_system_info: need_fullpath=false, block_extract=false.
# These are reviewed upstream declarations, never evidence of installed versions.
ZIP_CORES = {
    'mgba': ({'gba','gb','gbc'}, 'https://github.com/mgba-emu/mgba/blob/master/src/platform/libretro/libretro.c'),
    'gambatte': ({'gb','gbc'}, 'https://github.com/libretro/gambatte-libretro/blob/master/libgambatte/libretro/libretro.cpp'),
    'snes9x': ({'sfc','smc'}, 'https://github.com/libretro/snes9x/blob/master/libretro/libretro.cpp'),
}
RESERVE = 64*1024*1024


def history():
    records=[json.loads(path.read_text(encoding='utf-8')) for path in sorted(
        (app_paths.user_data_dir()/'rom-storage').glob('*/manifest.json'),
        key=lambda value:value.stat().st_mtime, reverse=True)[:100]]
    for record in records:
        for row in record['results']:
            row.setdefault('id',hashlib.sha256(io.key(row['source']).encode()).hexdigest()[:24])
    return records


def analyze(payload, cancelled=lambda: None, progress=lambda message: None):
    playlist, system = payload.get('playlist_path'), payload.get('system')
    source, target = payload.get('source_directory'), payload.get('target_directory')
    workspace = payload.get('workspace') or str(app_paths.user_data_dir())
    if (not all(isinstance(value,str) and value for value in (playlist,system,source,target,workspace))
            or not playlist.lower().endswith('.lpl') or playlist.startswith('adb://')):
        raise ValueError('请选择列表、游戏源目录和主机目标目录（本地或 MTP）')
    system = ALIASES.get(system,system)
    if system not in CARTRIDGES and system not in OPTICAL:
        raise ValueError('当前仅分析卡带与 Saturn／PlayStation；街机 ROM 集不参与整理或重新压缩')
    if re.match(r'^\w+://',workspace): raise ValueError('ZIP 工作目录必须位于电脑')
    workspace = Path(workspace).expanduser().resolve()
    if not workspace.is_dir(): raise ValueError('电脑工作目录不存在')
    reader = Reader(playlist)
    # Both browser-selected directories must belong to this library transport/device.
    source, target = reader.locate(source), reader.locate(target)
    if not source or not target: raise ValueError('目录不属于当前设备或缺少唯一映射')
    source, target = io.key(source), io.key(target)
    target_entries = folders(target)
    state = reader.probe(playlist)
    if state['status']!='present' or state['size']>METADATA_LIMIT:
        raise ValueError('列表不可读或超过元数据大小限制')
    raw = read(playlist)
    document = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document,dict) or not isinstance(document.get('items'),list): raise ValueError('列表格式无效')
    cores = {}
    for item in document['items']:
        if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not isinstance(item.get('core_path',''),str):
            raise ValueError('列表包含无效的路径或核心字段')
        location = reader.locate(item['path'])
        if location: cores.setdefault(io.key(location),set()).add(item.get('core_path',''))
    rows = []; pending = [source]
    while pending:
        cancelled(); directory = pending.pop(); progress('检查目录：'+directory)
        entries = folders(directory)
        for entry in sorted(entries,key=lambda value:value['name'].casefold()):
            path = join(directory,entry['name'])
            if entry['folder']:
                if not entry['name'].startswith(('PLCN-ZIP-','PLCN-CHD-','PLCN-DEPLOY-','PLCN-SOURCES-')):
                    pending.append(path)
                continue
            name = entry['name']; extension = PurePosixPath(name).suffix.lower().lstrip('.')
            if extension not in CARTRIDGES.get(system,set()) | {'chd','cue','m3u','ccd','gdi','toc','iso','zip','7z','rar','fds'}: continue
            path = io.key(path); destination = join(target,name)
            row = {'id':hashlib.sha256(path.encode()).hexdigest()[:24], 'source':path,'name':name,
                   'target':destination,'size':entry['size'],'format':extension,'layout':'keep',
                   'zip_eligible':False,'issues':[],'cores':[]}
            raw_cart = extension in CARTRIDGES.get(system,set())
            standalone = raw_cart or (extension=='chd' and system in OPTICAL)
            companions = [other['name'] for other in entries if not other['folder'] and
                PurePosixPath(other['name']).suffix.lower() in {'.ips','.bps','.ups','.msu','.pcm'} and
                (PurePosixPath(other['name']).stem==PurePosixPath(name).stem or other['name'].startswith(PurePosixPath(name).stem+'-'))]
            if companions:
                standalone = False; row['issues'].append('存在补丁／增强资源，保留目录：'+'、'.join(companions))
            if standalone:
                row['layout'] = 'already_flat' if io.key(destination)==path else 'candidate'
            elif extension=='m3u': row['issues'].append('多盘入口保留；移动时须联动盘文件、相对引用和分组身份')
            elif not companions: row['issues'].append('压缩包、软盘或多文件镜像保留原目录，本项不改变其内容')
            for core_path in sorted(cores.get(path,[])):
                core = next((value for value in ZIP_CORES if re.fullmatch(re.escape(value)+r'_libretro(?:_android)?\.(?:so|dll|dylib)',core_path.replace('\\','/').rsplit('/',1)[-1])),None)
                row['cores'].append({'path':core_path,'id':core,'declares_zip_extraction':bool(core and extension in ZIP_CORES[core][0]),
                                     'source':ZIP_CORES[core][1] if core else None})
            if raw_cart and standalone:
                row['zip_eligible'] = bool(row['cores']) and all(core['declares_zip_extraction'] for core in row['cores'])
                if '\\' in name or '\x00' in name:
                    row['zip_eligible'] = False; row['issues'].append('文件名含 ZIP 路径分隔符，保留原文件')
                if not row['zip_eligible']: row['issues'].append('该文件的全部列表核心尚未核对 ZIP 解包支持，仅提供目录建议')
                else:
                    progress('读取源指纹：'+name)
                    row['sha256'] = io.digest(path,cancelled)
                    if row['sha256'] is None: raise ValueError('源 ROM 已消失，请重新分析：'+path)
            rows.append(row)
    by_path={row['source']:row for row in rows}
    for row in rows:
        if row['format']!='m3u' or system not in OPTICAL or row['size']>METADATA_LIMIT: continue
        values,errors=parse_references(read(row['source']),'m3u')
        members=[]
        for value in values:
            access=reader.locate(reference_path(row['source'],value['value']))
            member=by_path.get(io.key(access)) if access else None
            if member and member['format']=='chd' and member['layout'] in {'candidate','already_flat'}: members.append(member['id'])
        if not errors and len(members)==len(values) and len(members)>=2 and len(set(members))==len(members):
            row.update(members=members,layout='already_flat' if io.key(row['target'])==row['source'] else 'candidate',sha256=io.digest(row['source'],cancelled))
            row['issues']=['已识别独立 CHD 多盘入口；目录整理时联动盘文件与 M3U 引用，保留盘序']
    counts = Counter(row['name'].casefold() for row in rows if row['layout']!='keep')
    existing = {entry['name'].casefold() for entry in target_entries}
    for row in rows:
        if row['layout']=='candidate' and (counts[row['name'].casefold()]>1 or row['name'].casefold() in existing):
            row['layout']='conflict'; row['issues'].append('目标同名冲突；不会覆盖、按中文名合并或自动改名')
    rows.sort(key=lambda row:(not row['zip_eligible'],row['source']))
    eligible = [row for row in rows if row['zip_eligible']]
    size = sum(row['size'] for row in eligible)
    required = size*3+RESERVE
    ident = uuid.uuid4().hex
    return {'id':ident,'playlist':playlist,'playlist_sha256':hashlib.sha256(raw).hexdigest(),
            'system':system,'source_directory':source,'target_directory':target,'workspace':str(workspace),
            'output_directory':str(workspace/('PLCN-ZIP-'+ident)),'rows':rows,
            'required_bytes':required,'free_bytes':shutil.disk_usage(workspace).free,
            'note':'目录结果是只读建议；ZIP 仅生成电脑副本，原文件、列表、存档与图片均保留。安装版本和运行未验收。'}


def convert(plan, selected, cancelled=lambda: None, progress=lambda message: None):
    rows = [row for row in plan['rows'] if row['id'] in selected]
    if not rows or len(rows)!=len(selected) or any(not row['zip_eligible'] for row in rows): raise ValueError('请选择可生成 ZIP 的 ROM')
    if io.digest(plan['playlist'],cancelled)!=plan['playlist_sha256']: raise ValueError('列表已变化，请重新分析')
    if shutil.disk_usage(plan['workspace']).free < sum(row['size'] for row in rows)*3+RESERVE: raise ValueError('电脑工作空间不足')
    cancelled()
    output = Path(plan['output_directory'])
    manifest = app_paths.user_data_dir()/'rom-storage'/plan['id']/'manifest.json'
    manifest.parent.mkdir(parents=True)
    record = {'id':plan['id'],'created_at':datetime.now(timezone.utc).isoformat(),'status':'running',
              'playlist':plan['playlist'],'system':plan['system'],'output_directory':str(output),
              'target_directory':plan['target_directory'],'source_directory':plan['source_directory'],'workspace':plan['workspace'],
              'mode':'local_zip_copy','sources':rows,'results':[],'error':None,'device_saved_bytes':0}
    atomic_write_json(manifest,record)
    try:
        output.mkdir()
        for number,row in enumerate(rows,1):
            cancelled(); progress(f'{number}/{len(rows)} · 复制并核对 ROM：'+row['name'])
            with tempfile.TemporaryDirectory(prefix='.work-',dir=output) as temporary:
                work = Path(temporary); copied = work/'source'
                if io.copy_to(row['source'],copied,cancelled)!=row['sha256']: raise ValueError('ROM 在分析后变化：'+row['source'])
                archive = work/'verified.zip'
                with zipfile.ZipFile(archive,'x') as zipped:
                    info = zipfile.ZipInfo(row['name']); info.file_size = copied.stat().st_size; info.compress_type = zipfile.ZIP_DEFLATED
                    with copied.open('rb') as original,zipped.open(info,'w') as member:
                        while True:
                            cancelled(); chunk = original.read(1024*1024)
                            if not chunk: break
                            member.write(chunk)
                progress('解包并逐字节比对：'+row['name'])
                with zipfile.ZipFile(archive) as zipped:
                    if zipped.namelist()!=[row['name']]: raise ValueError('ZIP 成员不一致')
                    with zipped.open(row['name']) as member,copied.open('rb') as original:
                        while True:
                            cancelled(); chunk = original.read(1024*1024)
                            if member.read(len(chunk) or 1)!=chunk: raise ValueError('ZIP 解压内容不一致')
                            if not chunk: break
                if io.digest(row['source'],cancelled)!=row['sha256']: raise ValueError('源 ROM 在转换期间变化：'+row['source'])
                archive_hash = io.digest(str(archive),cancelled)
                destination = output/row['id']; destination.mkdir()
                final = destination/(PurePosixPath(row['name']).stem+'.zip')
                archive.rename(final)
                record['results'].append({'id':row['id'],'source':row['source'],'source_sha256':row['sha256'],'output':str(final),
                    'sha256':archive_hash,'member':row['name'],'input_bytes':row['size'],'output_bytes':final.stat().st_size,
                    'copy_size_delta_bytes':final.stat().st_size-row['size'],'cores':row['cores'],'verification':'byte_for_byte'})
                atomic_write_json(manifest,record)
        record['status']='completed'
    except (OSError,ValueError,RuntimeError,zipfile.BadZipFile,TaskCancelled) as error:
        record['status']='cancelled' if isinstance(error,TaskCancelled) else 'failed'; record['error']=str(error)
        atomic_write_json(manifest,record)
        raise
    atomic_write_json(manifest,record)
    return record
