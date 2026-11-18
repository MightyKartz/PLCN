"""Single-file ROM replacement on the existing guarded backup journal."""
import json
from pathlib import Path

import content_scan as scan
from disc_inspection import Reader, reference_path
import game_management as games
import m3u_transaction as tx
import mtp_runtime as mtp
from rom_paths import split_archive

MAX_BYTES = 64 * 1024 * 1024
SYSTEMS = {'Nintendo - Nintendo Entertainment System', 'Nintendo - Super Nintendo Entertainment System',
           'Nintendo - Game Boy', 'Nintendo - Game Boy Color', 'Nintendo - Game Boy Advance',
           'Sega - Mega Drive - Genesis', 'Sega - Master System - Mark III', 'Sega - Game Gear',
           'NEC - PC Engine - TurboGrafx 16', 'Nintendo - Nintendo 64'}


def supports(system, physical, member, probe):
    extension = Path(physical).suffix.lower()
    return (isinstance(system, str) and system in SYSTEMS and not member and probe['status'] == 'present'
            and 0 < probe['size'] <= MAX_BYTES
            and extension not in {'.zip','.7z','.rar','.cue','.m3u','.chd','.iso'}
            and extension.lstrip('.') in scan.SYSTEMS[system][2].split())


def latest(playlist, target):
    for record in tx.receipts():
        if record['mode'] == 'game_rom_update' and record['playlist'] == playlist and any(
                entry['path'] == target and entry['kind'] == 'rom' for entry in record['files']):
            return {'id':record['id'], 'status':record['status']}
    return None


def prepare(payload):
    playlist, raw, document, index = games.selected_item(payload)
    system = payload.get('system')
    if not isinstance(system, str) or system not in SYSTEMS:
        raise ValueError('当前仅支持单文件卡带 ROM；多文件光盘请使用对应工具')
    source = payload.get('source')
    if not isinstance(source, str) or '://' in source:
        raise ValueError('请选择电脑上的新版 ROM 文件')
    source = Path(source).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError('新版 ROM 文件不存在或为符号链接')
    item = document['items'][index]
    physical, member = split_archive(item['path'])
    extension = Path(physical).suffix.lower()
    if member or extension in {'.zip', '.7z', '.rar', '.cue', '.m3u', '.chd', '.iso'}:
        raise ValueError('请选中未压缩的单文件 ROM；此入口不替换压缩包或多文件光盘')
    if source.suffix.lower() != extension or extension.lstrip('.') not in scan.SYSTEMS[system][2].split():
        raise ValueError('新版 ROM 必须与当前文件格式相同')
    reader = Reader(playlist)
    target = reader.locate(reference_path(playlist, physical))
    probe = reader.probe(target)
    if probe['status'] != 'present':
        raise ValueError('原 ROM 不存在或路径尚未映射，请先检查连接和目录配置')
    if not mtp.is_mtp(target) and Path(target).is_symlink():
        raise ValueError('不能更新符号链接指向的 ROM')
    size = source.stat().st_size
    if not 0 < size <= MAX_BYTES or not supports(system, physical, member, probe):
        raise ValueError('此入口支持不超过 64 MiB 的非空单文件 ROM')
    before, after = scan.read(target), source.read_bytes()
    if mtp.digest(before) == mtp.digest(after):
        return {'rom_update':True, 'can_apply':False, 'source_name':source.name, 'old_size':len(before), 'new_size':len(after)}
    # Backup and readback use the same transaction as names/M3U, including MTP.
    writes = [{'path':target,'expected':mtp.digest(before),'content':after,'kind':'rom'}]
    changed = False
    for entry in document['items']:
        if entry['path'] == item['path'] and entry.get('crc32', 'DETECT') != 'DETECT':
            entry['crc32'] = 'DETECT'; changed = True
    dependencies = []
    if changed:
        writes.append({'path':playlist,'expected':mtp.digest(raw),
                       'content':(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode(),'kind':'playlist'})
    else:
        dependencies.append({'path':playlist,'digest':mtp.digest(raw)})
    plan = {'playlist':playlist,'label':'更新 ROM：'+str(item.get('label') or source.name),
            'mode':'game_rom_update','can_apply':True,'writes':writes,'patches':[], 'dependencies':dependencies}
    return {'rom_update':True,'transaction':plan,'can_apply':True,'source_name':source.name,
            'old_size':len(before),'new_size':len(after)}


def apply(plan):
    result = tx.start(plan['transaction'])
    if result['status'] != 'applied':
        restored = tx.run(result['operation_id'], restore=True)
        return {**result, 'restored':restored['status']=='restored'}
    return result
