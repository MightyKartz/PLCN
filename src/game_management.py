"""Reviewed game copies and playlist-only removals; ROM deletion is not exposed."""
import copy
import json
from pathlib import Path, PureWindowsPath
import posixpath
import shutil
import uuid

import chd_io
import content_scan as scan
import m3u_transaction as tx
import mtp_runtime as mtp
from system_resources import is_system_resource


def playlist_path(value):
    if not isinstance(value, str) or not value.endswith('.lpl') or value.startswith('adb://'):
        raise ValueError('请选择本地或 MTP 游戏列表')
    if mtp.is_mtp(value):
        mtp.parse(value)
        return value
    return str(Path(value).expanduser().resolve())


def document(path):
    raw = scan.read(path)
    data = json.loads(raw.decode('utf-8-sig')) if raw is not None else {'version': '1.5', 'items': []}
    if not isinstance(data, dict) or not isinstance(data.get('items'), list) or any(
            not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in data['items']):
        raise ValueError('游戏列表字段无效')
    return raw, data


def transaction(path, before, after, mode, label):
    return {'playlist': path, 'label': label, 'mode': mode, 'dependencies': [], 'patches': [],
            'can_apply': True, 'writes': [{'path': path, 'expected': mtp.digest(before),
                'content': (json.dumps(after, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), 'kind': 'playlist'}]}


def remove_preview(payload):
    path = playlist_path(payload.get('playlist'))
    indices, expected = payload.get('indices'), payload.get('expected')
    if not isinstance(indices, list) or not indices or any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices):
        raise ValueError('请选择要移出列表的游戏')
    raw, data = document(path)
    if not isinstance(expected, str) or mtp.digest(raw) != expected:
        raise ValueError('列表已变化，请重新读取后选择游戏')
    if max(indices) >= len(data['items']):
        raise ValueError('游戏条目不存在，请重新读取列表')
    selected = set(indices)
    from rom_paths import disc_group, preferred_disc_entry
    paths = [item['path'] for item in data['items']]
    preferred = preferred_disc_entry(data['items'])
    selected.update(i for i, item in enumerate(data['items'])
                    if preferred.get(disc_group(item['path'], item.get('label'), paths)) in indices)
    removed = [item for i, item in enumerate(data['items']) if i in selected]
    after = copy.deepcopy(data)
    after['items'] = [item for i, item in enumerate(after['items']) if i not in selected]
    return {'transaction': transaction(path, raw, after, 'game_remove', '移出列表'),
            'removed': removed, 'count': len(removed), 'can_apply': True}


def selected_item(payload):
    path = playlist_path(payload.get('playlist'))
    index, expected = payload.get('index'), payload.get('expected')
    raw, data = document(path)
    if not isinstance(expected, str) or mtp.digest(raw) != expected:
        raise ValueError('列表已变化，请重新读取后选择游戏')
    if type(index) is not int or not 0 <= index < len(data['items']):
        raise ValueError('游戏条目不存在，请重新读取列表')
    return path, raw, data, index


def edit_preview(payload):
    path, raw, data, index = selected_item(payload)
    label = payload.get('label')
    if not isinstance(label, str) or not label.strip() or len(label) > 300 or any(c in label for c in '\x00\r\n'):
        raise ValueError('请填写有效游戏名称（最多 300 字）')
    label = label.strip()
    before = data['items'][index].get('label', '')
    after = copy.deepcopy(data)
    after['items'][index]['label'] = label
    write = transaction(path, raw, after, 'game_edit', '修改游戏名称')
    thumbnails, system = payload.get('thumbnails', ''), payload.get('system', '')
    if not isinstance(thumbnails, str) or not isinstance(system, str):
        raise ValueError('图片目录或主机无效')
    copies = []
    if thumbnails and label != before:
        from artwork_resolver import validate_system, sanitize_filename
        from playlist_browser import open_artwork_reader, artwork_statuses
        validate_system(system)
        if thumbnails.startswith('adb://'):
            raise ValueError('名称编辑请使用本地或 MTP 图片目录')
        if mtp.is_mtp(thumbnails) and (not mtp.is_mtp(path) or mtp.parse(thumbnails)[0] != mtp.parse(path)[0]):
            raise ValueError('图片目录必须属于当前掌机')
        resolver, lookups, error = open_artwork_reader(thumbnails, system)
        if error: raise ValueError('无法检查原图片：' + error)
        images = artwork_statuses(before, data['items'][index]['path'], resolver, lookups, thumbnails, system)
        for kind, image in images.items():
            if image['status'] != 'exists': continue
            source = str(image['path'])
            target = scan.join(thumbnails, system, kind, sanitize_filename(label) + '.png')
            content, existing = scan.read(source), scan.read(target)
            if len(content) > 8 * 1024 * 1024: raise ValueError('图片超过 8 MiB，请先调整大小：' + source)
            if existing is not None and existing != content: raise ValueError('新名称已有不同图片，请选择其他名称：' + label)
            if existing == content: continue
            write['dependencies'].append({'path': source, 'digest': mtp.digest(content)})
            write['writes'].insert(0, {'path': target, 'content': content, 'expected': None, 'kind': 'artwork_copy'})
            copies.append(target)
    return {'transaction': write, 'before': before, 'after': label, 'edited': 1,
            'artwork_copies': copies, 'can_apply': label != before}


def details(payload):
    from disc_inspection import Reader, reference_path
    from rom_paths import split_archive
    path, raw, data, index = selected_item(payload)
    item = data['items'][index]
    reader = Reader(path)
    physical, member = split_archive(item['path'])
    location = reader.locate(reference_path(path, physical))
    probe = reader.probe(location)
    core_name = item.get('core_name') or 'DETECT'
    core_path = item.get('core_path') or 'DETECT'
    if core_path == 'DETECT':
        core_path = data.get('default_core_path') or 'DETECT'
        core_name = data.get('default_core_name') or 'DETECT'
    return {'index': index, 'label': item.get('label', ''), 'core_path': core_path, 'core_name': core_name,
            'size': probe.get('size'), 'file_status': probe['status'], 'file_path': location, 'archive_member': member}


def validate_import(payload):
    root, destination, system = payload.get('root'), payload.get('destination'), payload.get('system')
    sources, android = payload.get('sources'), payload.get('android_directory', '')
    if not isinstance(system, str) or system not in scan.SYSTEMS or not isinstance(root, str) or not root or not isinstance(destination, str) or not destination:
        raise ValueError('请选择主机和目标目录')
    if not isinstance(sources, list) or not sources or any(not isinstance(p, str) or not p for p in sources):
        raise ValueError('请选择电脑上的游戏文件或目录')
    if not isinstance(android, str):
        raise ValueError('掌机启动目录无效')
    remote = mtp.is_mtp(root)
    if remote:
        if not mtp.is_mtp(destination) or mtp.parse(root)[0] != mtp.parse(destination)[0]:
            raise ValueError('目标目录必须属于当前掌机')
        if not android.startswith(('/storage/', '/sdcard/')) or any(p in {'.', '..'} for p in android.split('/')):
            raise ValueError('请填写掌机实际游戏目录，例如 /storage/卡号/Roms/GBA')
        # Infer storage roots only from saved mappings whose relative folders agree.
        # A library on internal storage does not imply that ROMs belong there.
        for profile in scan.profiles().get(root, []):
            source = profile['directory']
            logical = profile['android_directory'].rstrip('/')
            if not mtp.is_mtp(source) or mtp.parse(source)[0] != mtp.parse(root)[0]:
                continue
            if not logical.startswith(('/storage/', '/sdcard/')):
                continue
            size = 4 if logical.startswith('/storage/emulated/') else 3 if logical.startswith('/storage/') else 2
            mount = '/'.join(logical.split('/')[:size])
            if mtp.parse(source)[2] != logical[len(mount):].strip('/').split('/'):
                continue
            if android == mount or android.startswith(mount + '/'):
                expected = mtp.uri(mtp.parse(source)[0], mtp.parse(source)[1], android[len(mount):].lstrip('/'))
                if mtp.parse(destination) != mtp.parse(expected):
                    raise ValueError('复制目录与掌机启动目录不一致，请重新选择目标存储和目录')
    else:
        if '://' in root or '://' in destination:
            raise ValueError('导入请使用本地目录或 MTP 连接')
        root, destination = (str(Path(p).expanduser().resolve()) for p in (root, destination))
        if not Path(root).is_dir():
            raise ValueError('RetroArch 目录不存在')
    selected = []
    for value in sources:
        if '://' in value:
            raise ValueError('来源必须是电脑上的文件或目录')
        path = Path(value).expanduser()
        if path.is_symlink() or not path.exists():
            raise ValueError('来源不存在或为符号链接：' + value)
        selected.append(str(path.resolve()))
        if not remote and path.is_dir() and Path(destination).is_relative_to(path.resolve()) and Path(destination) != path.resolve():
            raise ValueError('目标目录不能位于来源目录内部')
    filename = scan.playlist_name(system, payload.get('playlist_name'))
    return {'root': root, 'destination': destination, 'system': system, 'sources': list(dict.fromkeys(selected)),
            'android_directory': android.rstrip('/'), 'playlist_name': filename, 'playlist': scan.join(root, 'playlists', filename)}


def import_preview(config, progress=lambda *args: None, cancelled=lambda: None):
    from disc_inspection import parse_references
    raw, data = document(config['playlist'])
    extensions = set(scan.SYSTEMS[config['system']][2].split())
    optical = config['system'] in {'Sony - PlayStation', 'Sega - Saturn'}
    if optical:
        extensions.add('iso')
    files, candidates, referenced = {}, set(), set()
    resources = set()

    def include(path, base):
        cancelled()
        if path.is_symlink() or not path.is_file():
            raise ValueError('来源不存在或为符号链接：' + str(path))
        rel = path.relative_to(base).as_posix()
        if rel in files:
            if files[rel] != str(path):
                raise ValueError('所选来源中有同名目标，请分开导入：' + rel)
            return rel
        files[rel] = str(path)
        if optical and path.suffix.lower() in {'.ccd', '.toc'}:
            raise ValueError('请将 CCD/TOC 转为 CHD 或选择 CUE 后导入：' + rel)
        if optical and path.suffix.lower() in {'.cue', '.m3u'}:
            if path.stat().st_size > 1024 * 1024:
                raise ValueError('光盘描述文件超过 1 MiB：' + rel)
            refs, errors = parse_references(path.read_bytes(), path.suffix[1:].lower())
            if errors:
                raise ValueError('无法解析光盘引用：' + rel)
            for ref in refs:
                value = ref['value']
                child = (path.parent / value).resolve()
                if Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or not child.is_relative_to(base):
                    raise ValueError('光盘引用必须位于所选来源目录内：' + value)
                referenced.add(include(child, base))
        return rel

    skipped = 0
    for selected in config['sources']:
        source = Path(selected)
        base = source if source.is_dir() else source.parent
        for path in sorted(source.rglob('*')) if source.is_dir() else [source]:
            cancelled()
            if path.is_symlink():
                raise ValueError('来源包含符号链接，请先移出：' + str(path))
            if not path.is_file():
                continue
            if path.suffix.lower().lstrip('.') not in extensions:
                skipped += 1
                continue
            rel = include(path, base)
            if is_system_resource({'path': str(path), 'label': path.stem}, config['system']):
                resources.add(rel)
            else:
                candidates.add(rel)
    candidates -= referenced
    existing = {item['path'].replace('\\', '/') for item in data['items']}
    additions, copies, conflicts = [], [], []
    duplicate = 0
    for i, (rel, source) in enumerate(sorted(files.items())):
        cancelled()
        progress(i, len(files), rel)
        target = scan.join(config['destination'], *rel.split('/'))
        if not mtp.is_mtp(target) and not Path(target).resolve().is_relative_to(Path(config['destination'])):
            raise ValueError('目标子目录包含指向外部的符号链接：' + rel)
        expected = chd_io.digest(source, cancelled)
        current = chd_io.digest(target, cancelled)
        state = 'new' if current is None else 'existing' if current == expected else 'conflict'
        if state == 'conflict': conflicts.append(rel)
        if state == 'existing': duplicate += 1
        copies.append({'source': source, 'target': target, 'relative': rel, 'digest': expected,
                       'size': Path(source).stat().st_size, 'state': state})
        logical = posixpath.join(config['android_directory'], rel) if mtp.is_mtp(target) else target
        if rel in candidates and logical.replace('\\', '/') not in existing:
            additions.append({'path': logical, 'label': Path(rel).stem, 'core_path': 'DETECT',
                              'core_name': 'DETECT', 'crc32': 'DETECT', 'db_name': config['system'] + '.lpl'})
            existing.add(logical.replace('\\', '/'))
    required = sum(f['size'] for f in copies if f['state'] == 'new')
    if mtp.is_mtp(config['destination']):
        free = mtp.free_bytes(config['destination'])
    else:
        ancestor = Path(config['destination'])
        while not ancestor.exists(): ancestor = ancestor.parent
        free = shutil.disk_usage(ancestor).free
    after = copy.deepcopy(data)
    after['items'].extend(additions)
    write = transaction(config['playlist'], raw, after, 'game_import', '导入游戏')
    saved = scan.profiles()
    profiles = list(saved.get(config['root'], []))
    if not any(profile['directory'] == config['destination'] and profile['system'] == config['system'] for profile in profiles):
        profiles.append({'root': config['root'], 'directory': config['destination'], 'system': config['system'],
            'core_id': scan.SYSTEMS[config['system']][0], 'core_path': data.get('default_core_path') or 'DETECT',
            'extensions': ' '.join(sorted(extensions)), 'recursive': True, 'dat_path': '', 'dat_filter': False,
            'android_directory': config['android_directory'], 'abi': '', 'playlist_name': config['playlist_name']})
        write['patches'].append(tx.patch(str(scan.profiles_path()), saved, [config['root']], profiles))
    return {'config': config, 'copies': copies, 'added': additions, 'duplicates': duplicate, 'resources': len(resources),
            'skipped': skipped, 'conflicts': conflicts, 'required_bytes': required, 'free_bytes': free,
            'can_apply': bool(additions or required) and not conflicts and required <= free,
            'transaction': write}


def public_preview(plan):
    if 'edited' in plan:
        return {key: plan[key] for key in ('before', 'after', 'edited', 'artwork_copies', 'can_apply')}
    if 'removed' in plan:
        return {key: plan[key] for key in ('removed', 'count', 'can_apply')}
    return {**{key: plan[key] for key in ('added', 'duplicates', 'resources', 'skipped', 'conflicts', 'required_bytes', 'free_bytes', 'can_apply')},
            'files': [{'name': f['relative'], 'size': f['size'], 'state': f['state']} for f in plan['copies']],
            'playlist': plan['config']['playlist']}


def apply(plan, progress=lambda *args: None, cancelled=lambda: None):
    change = next(change for change in plan['transaction']['writes'] if change['kind'] == 'playlist')
    if mtp.digest(scan.read(change['path'])) != change['expected']:
        raise ValueError('列表已变化，请重新预览')
    for i, entry in enumerate(plan.get('copies', [])):
        cancelled()
        progress(i, len(plan['copies']), entry['relative'])
        if chd_io.digest(entry['source'], cancelled) != entry['digest']:
            raise ValueError('来源已变化，请重新预览：' + entry['source'])
        target = entry['target']
        if mtp.is_mtp(target):
            with mtp.session(target) as (handle, storage, parts):
                mtp.resolve(handle, storage, parts[:-1], create=True)
        else:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        stage = target + '.import-' + uuid.uuid4().hex + '.part'
        try:
            chd_io.put_new(target, entry['source'], entry['digest'], stage, cancelled)
        finally:
            if not mtp.is_mtp(stage) and Path(stage).exists():
                Path(stage).unlink()
    cancelled()
    # Playlist write and recovery use the existing transaction journal. Verified
    # copies are deliberately retained on cancellation, failure, and restoration.
    if not mtp.is_mtp(change['path']): Path(change['path']).parent.mkdir(parents=True, exist_ok=True)
    result = tx.start(plan['transaction'])
    return {**result, 'added': len(plan.get('added', [])), 'removed': plan.get('count', 0), 'edited': plan.get('edited', 0),
            'copied': sum(f['state'] == 'new' for f in plan.get('copies', []))}
