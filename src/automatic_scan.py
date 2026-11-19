"""Discover supported console folders; review incremental playlist imports before writing."""
import json
from pathlib import Path
import content_scan as scan
import mtp_runtime as mtp
from task_control import checkpoint

ALIASES = {
    'nes': 'Nintendo - Nintendo Entertainment System', 'fc': 'Nintendo - Nintendo Entertainment System',
    'snes': 'Nintendo - Super Nintendo Entertainment System', 'sfc': 'Nintendo - Super Nintendo Entertainment System',
    'gb': 'Nintendo - Game Boy', 'gbc': 'Nintendo - Game Boy Color', 'gba': 'Nintendo - Game Boy Advance',
    'md': 'Sega - Mega Drive - Genesis', 'genesis': 'Sega - Mega Drive - Genesis',
    'ss': 'Sega - Saturn', 'saturn': 'Sega - Saturn', 'ps': 'Sony - PlayStation', 'ps1': 'Sony - PlayStation', 'psx': 'Sony - PlayStation',
    'fbneo': 'FBNeo - Arcade Games', 'mame': 'MAME',
}
CONTAINERS = {'roms', 'rom', 'games', 'game', 'emulation'}


def validate(payload):
    root, sources = payload.get('root'), payload.get('sources')
    if not isinstance(root, str) or not root or not isinstance(sources, list) or not sources or len(sources) > 8:
        raise ValueError('请选择游戏库和扫描存储范围')
    if root.startswith('adb://'):
        raise ValueError('自动扫描请使用文件传输连接或本地游戏库')
    if mtp.is_mtp(root):
        mtp.parse(root)
    elif not Path(root).expanduser().is_absolute() or not Path(root).expanduser().is_dir():
        raise ValueError('游戏库目录不存在')
    for source in sources:
        if not isinstance(source, str) or not source:
            raise ValueError('扫描目录无效')
        if mtp.is_mtp(root):
            if not mtp.is_mtp(source) or mtp.parse(source)[0] != mtp.parse(root)[0]:
                raise ValueError('扫描存储必须属于当前掌机')
        elif mtp.is_mtp(source) or not Path(source).expanduser().is_dir():
            raise ValueError('扫描目录不存在')
    return root, list(dict.fromkeys(sources))


def preview(root, sources, progress=lambda *args: None, cancel_check=None):
    documents = {}
    has_playlists = any(entry['folder'] and entry['name'] == 'playlists' for entry in scan.folders(root))
    for entry in scan.folders(scan.join(root, 'playlists')) if has_playlists else []:
        if not entry['folder'] and entry['name'].endswith('.lpl'):
            content = scan.read(scan.join(root, 'playlists', entry['name']))
            document = json.loads(content.decode('utf-8-sig'))
            documents[entry['name']] = document
    all_paths = [item.get('path', '') for doc in documents.values() for item in doc.get('items', [])]
    plans, unclassified, visited = {}, [], set()
    profiles = scan.profiles().get(root, [])
    def walk(directory, depth=0):
        checkpoint(cancel_check)
        if directory in visited:
            return
        visited.add(directory)
        progress(0, 0, '发现目录：' + directory)
        for entry in scan.folders(directory):
            if not entry['folder']:
                continue
            path = scan.join(directory, entry['name'])
            name = entry['name'].casefold()
            if name in {'bios', 'system', 'saves', 'savestates', 'screenshots'}:
                continue
            system = ALIASES.get(name) or next((s for s in scan.SYSTEMS if s.casefold() == name), None)
            if system:
                prepare(path, system)
            elif name in CONTAINERS and depth < 3:
                walk(path, depth + 1)
            elif depth:
                unclassified.append({'directory': path, 'reason': '目录名称未识别，可使用手动添加指定主机'})
    def prepare(directory, system):
        checkpoint(cancel_check)
        profile = next((p for p in profiles if p['directory'] == directory and p['system'] == system), None)
        if profile:
            filename = profile['playlist_name']
            old = documents.get(filename, {})
        else:
            filename, old = next(
                ((name, doc) for name, doc in documents.items()
                 if name == system + '.lpl' or ALIASES.get(name[:-4].casefold()) == system
                 or any(item.get('db_name') == system + '.lpl' for item in doc.get('items', []))),
                (system + '.lpl', {}),
            )
        core = scan.SYSTEMS[system][0]
        android = ''
        if mtp.is_mtp(directory):
            suffix = '/' + '/'.join(mtp.parse(directory)[2]) + '/'
            candidates = {p.split(suffix, 1)[0] + suffix[:-1] for p in all_paths if p.startswith(('/storage/', '/sdcard/')) and p.count(suffix) == 1}
            android = profile['android_directory'] if profile else next(iter(candidates)) if len(candidates) == 1 else ''
            if not android:
                unclassified.append({'directory': directory, 'reason': '需要确认掌机实际启动路径；请通过手动添加设置一次'})
                return
        config = dict(profile) if profile else dict(root=root, directory=directory, system=system, core_id=core,
            core_path=old.get('default_core_path') or 'DETECT', extensions=scan.SYSTEMS[system][2], recursive=True,
            dat_path='', dat_filter=False, android_directory=android, abi='', playlist_name=filename)
        plan = scan.preview(config, progress, cancel_check)
        for field in ('default_core_path', 'default_core_name'):
            plan['document'][field] = old.get(field) or 'DETECT'
        target = plan['target']
        if target not in plans:
            plans[target] = plan
        else:
            merged = plans[target]
            existing = {item['path'] for item in merged['document']['items']}
            added = [item for item in plan['added'] if item['path'] not in existing]
            merged['added'].extend(added)
            merged['document']['items'].extend(added)
            merged['skipped'] += plan['skipped']
        plans[target]['can_apply'] = bool(plans[target]['added'])
    for source in sources:
        name = (mtp.parse(source)[2][-1] if mtp.is_mtp(source) and mtp.parse(source)[2] else Path(source).name).casefold()
        if name in ALIASES:
            prepare(source, ALIASES[name])
        else:
            walk(source)
    return {'plans': plans, 'unclassified': unclassified}


def public_result(result):
    return {'rows': [{'system': plan['config']['system'], 'added': len(plan['added']),
                      'retained': plan['retained'], 'skipped': plan['skipped'], 'target': target}
                     for target, plan in result['plans'].items()], 'unclassified': result['unclassified']}


def apply(result, targets, progress=lambda *args: None, cancel_check=None):
    completed = []
    for index, target in enumerate(targets):
        checkpoint(cancel_check)
        plan = result['plans'][target]
        if plan['can_apply']:
            progress(index, len(targets), '导入：' + plan['config']['playlist_name'])
            completed.append(scan.apply(plan))
    return {'playlists': completed, 'added': sum(p['added'] for p in completed)}
