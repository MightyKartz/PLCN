"""Reviewed removal across the open library and its accessible game files."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import uuid

import app_paths
from artwork_resolver import sanitize_filename, validate_system
import chd_io
import content_scan as scan
from disc_inspection import Reader, game_content_files, reference_path
from game_file_actions import CARTRIDGE_SUFFIXES
from game_management import document
import m3u_transaction as tx
import mtp_runtime as mtp
from playlist_browser import artwork_lookup_names
from retroarch_scanner import scan_retroarch_target
from rom_paths import split_archive
from safe_io import atomic_write_json, file_lock

OPTICAL = {'.cue', '.m3u', '.chd', '.iso', '.pbp', '.bin', '.img'}
DESCRIPTORS = {'.cue', '.m3u', '.ccd', '.toc', '.gdi'}
ARCHIVES = {'.zip', '.7z', '.rar'}
AUDIO_TRACKS = {'.wav', '.flac', '.mp3', '.aiff', '.aif', '.raw', '.ogg'}


def validate(payload):
    path, root = payload.get('path'), payload.get('root')
    if not isinstance(path, str) or not isinstance(root, str) or not root:
        raise ValueError('请先打开对应的 RetroArch 游戏库')
    if mtp.is_mtp(path):
        serial, _, parts = mtp.parse(path)
        if not parts or not mtp.is_mtp(root) or mtp.parse(root)[0] != serial:
            raise ValueError('请先打开此掌机的 RetroArch 游戏库')
    elif not Path(path).is_absolute() or not Path(root).is_absolute():
        raise ValueError('请选择文件所在的本地 RetroArch 游戏库')
    if PurePosixPath(path.replace('\\', '/')).suffix.lower() not in CARTRIDGE_SUFFIXES | OPTICAL | ARCHIVES:
        raise ValueError('请选择受支持的 ROM 或光盘启动文件')
    if not mtp.is_mtp(path) and Path(path).is_symlink():
        raise ValueError('请先定位原文件')
    return chd_io.key(path), root


def preview(path, root, thumbnails_override=''):
    library = scan_retroarch_target(root)
    if not library['connected']:
        raise ValueError('无法读取游戏库，请重新连接后预览')
    reader_path = next((row['path'] for row in library['playlists']), scan.join(root, 'playlists', 'Entry.lpl'))
    reader = Reader(reader_path)
    probe = reader.probe(path)
    if probe['status'] != 'present' or probe['size'] is None:
        raise ValueError('游戏文件不存在或无法读取')
    optical = PurePosixPath(path).suffix.lower() in OPTICAL
    references, writes, dependencies, removed, retained = {}, [], [], [], []
    for row in library['playlists']:
        raw, data = document(row['path'])
        if raw is None:
            raise ValueError('播放列表已移除，请重新读取游戏库')
        digest = mtp.digest(raw)
        dependencies.append({'path': row['path'], 'digest': digest})
        remaining = []
        for item in data['items']:
            physical, _ = split_archive(item['path'])
            logical = reference_path(row['path'], physical.replace('\\', '/'))
            location = reader.locate(logical)
            if location:
                location = chd_io.key(location)
            suffix = PurePosixPath(physical).suffix.lower()
            if not location and (optical and suffix in DESCRIPTORS or
                                 PurePosixPath(physical).name.casefold() == PurePosixPath(path).name.casefold()):
                raise ValueError('无法核对播放列表的启动路径，请先确认设备目录映射：' + physical)
            if location == path:
                removed.append((row, item))
            else:
                remaining.append(item)
                retained.append((row, item))
                if optical and location and suffix in DESCRIPTORS:
                    state = reader.probe(location)
                    files, total = game_content_files(reader, location, state, suffix[1:])
                    if total is None:
                        raise ValueError('无法完整核对其他光盘入口的引用：' + physical)
                    for entry in files:
                        references.setdefault(chd_io.key(entry['path']), set()).add(location)
        if len(remaining) != len(data['items']):
            data['items'] = remaining
            writes.append({'kind': 'playlist', 'path': row['path'], 'expected': digest,
                           'content': (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()})

    suffix = PurePosixPath(path).suffix.lower()
    files = {path: probe['size']}
    if suffix in {'.cue', '.m3u'}:
        children, total = game_content_files(reader, path, probe, suffix[1:])
        if total is None:
            raise ValueError('无法完整核对该游戏的关联文件')
        for entry in children:
            linked = chd_io.key(entry['path'])
            if PurePosixPath(linked).suffix.lower() not in OPTICAL | AUDIO_TRACKS:
                raise ValueError('关联文件不是可确认的光盘或音轨，已保留：' + linked)
            files[linked] = entry['size']

    if optical:
        # Include launch files beside the deletion candidates even if they
        # have not yet been added to a playlist.
        directories = {target.rsplit('/', 1)[0] for target in files}
        for directory in sorted(directories):
            for entry in scan.folders(directory):
                fmt = PurePosixPath(entry['name']).suffix.lower()
                if entry['folder'] or fmt not in DESCRIPTORS:
                    continue
                neighbor = chd_io.key(scan.join(directory, entry['name']))
                if neighbor in files:
                    continue
                state = reader.probe(neighbor)
                linked, total = game_content_files(reader, neighbor, state, fmt[1:])
                if total is None:
                    raise ValueError('无法完整核对同目录的光盘入口：' + neighbor)
                for linked_file in linked:
                    references.setdefault(chd_io.key(linked_file['path']), set()).add(neighbor)

    if path in references:
        raise ValueError('该文件仍被其他游戏入口引用，请先在游戏文件中选择对应的启动文件：' + sorted(references[path])[0])
    direct = set()
    if len(files) > 1:
        for row, item in retained:
            physical, _ = split_archive(item['path'])
            location = reader.locate(reference_path(row['path'], physical.replace('\\', '/')))
            if location:
                direct.add(chd_io.key(location))
    shared = [target for target in files if target != path and (target in references or target in direct)]
    for target in shared:
        del files[target]

    covers = {}
    thumbnails = thumbnails_override or library['directories'].get('thumbnails')
    if thumbnails and (mtp.is_mtp(thumbnails) == reader.remote) and (
            not reader.remote or mtp.parse(thumbnails)[0] == mtp.parse(path)[0]):
        used = {}
        for row, item in retained:
            for system in {row['system'], (item.get('db_name') or row['system']).removesuffix('.lpl')}:
                used.setdefault(system.casefold(), set()).update(
                    (sanitize_filename(name) + '.png').casefold()
                    for name in artwork_lookup_names(item.get('label'), item['path']))
        for row, item in removed:
            system = validate_system((item.get('db_name') or row['system']).removesuffix('.lpl'))
            for name in artwork_lookup_names(item.get('label'), item['path']):
                filename = sanitize_filename(name) + '.png'
                if filename.casefold() in used.get(system.casefold(), set()):
                    continue
                candidate = scan.join(thumbnails, system, 'Named_Boxarts', filename)
                state = reader.probe(candidate)
                if state['status'] == 'present' and state['size'] is not None:
                    covers[candidate] = state['size']

    # Guard descriptors as well as the playlist inventories used to make the plan.
    for descriptor in sorted({entry for entry in (*files, *shared, *references)
                              if PurePosixPath(entry).suffix.lower() in {'.cue', '.m3u'}} |
                             {owner for owners in references.values() for owner in owners}):
        if reader.probe(descriptor)['size'] is not None:
            dependencies.append({'path': descriptor, 'digest': mtp.digest(reader.metadata(descriptor))})
    public = {'files': list(files), 'shared': shared, 'covers': list(covers),
              'playlists': [write['path'] for write in writes],
              'entries': [{'playlist': row['name'], 'label': item.get('label') or item['path']} for row, item in removed]}
    signature = hashlib.sha256(json.dumps([public, files, covers, dependencies], sort_keys=True).encode()).hexdigest()
    return {'signature': signature, 'public': public, 'files': files, 'covers': covers,
            'writes': writes, 'dependencies': dependencies}


def apply(path, root, thumbnails_override, signature, clean_covers, progress, cancelled):
    plan = preview(path, root, thumbnails_override)
    if plan['signature'] != signature:
        raise ValueError('文件或播放列表已变化，请关闭后重新预览')
    files = plan['files'] | (plan['covers'] if clean_covers else {})
    backup = app_paths.user_data_dir() / 'game-file-deletions' / uuid.uuid4().hex
    backup.mkdir(parents=True)
    if shutil.disk_usage(backup).free < sum(files.values()):
        raise ValueError('电脑空间不足，无法备份本次要删除的文件')
    receipt = {'status': 'backing_up', 'files': [], 'playlist_operation': None}
    manifest = backup / 'deletion.json'
    atomic_write_json(manifest, receipt)
    try:
        for index, source in enumerate(files):
            cancelled()
            progress(index, len(files), '备份：' + source)
            original = backup / f'{index:04d}{PurePosixPath(source).suffix}'
            digest = chd_io.copy_to(source, original, cancelled)
            if original.stat().st_size != files[source]:
                raise ValueError('文件大小在备份期间变化：' + source)
            receipt['files'].append({'path': source, 'backup': original.name, 'digest': digest, 'deleted': False})
            atomic_write_json(manifest, receipt)
        if preview(path, root, thumbnails_override)['signature'] != signature:
            raise ValueError('游戏库在备份期间变化，请重新预览')
        cancelled()
        if plan['writes']:
            transaction = {'playlist': plan['writes'][0]['path'], 'label': '删除游戏并更新播放列表',
                           'mode': 'game_remove', 'can_apply': True, 'dependencies': plan['dependencies'],
                           'writes': plan['writes'], 'patches': []}
            result = tx.start(transaction)
            receipt['playlist_operation'] = result['operation_id']
            if result['status'] != 'applied':
                raise RuntimeError(result['error'] or '播放列表更新未完成')
        for index, entry in enumerate(receipt['files']):
            source = entry['path']
            progress(index, len(files), '删除：' + source)
            if mtp.is_mtp(source):
                chd_io.remove(source, entry['digest'])
            else:
                with file_lock(source):
                    chd_io.remove(source, entry['digest'])
            entry['deleted'] = True
            atomic_write_json(manifest, receipt)
    except (OSError, ValueError, RuntimeError) as error:
        receipt.update(status='interrupted', error=str(error))
        atomic_write_json(manifest, receipt)
        raise RuntimeError(str(error) + '；备份与处理记录：' + str(backup)) from error
    receipt['status'] = 'applied'
    atomic_write_json(manifest, receipt)
    return {'playlists': [write['path'] for write in plan['writes']], 'backup_directory': str(backup),
            'deleted': len(files)}
