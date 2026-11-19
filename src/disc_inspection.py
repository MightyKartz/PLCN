"""Read-only optical game grouping and declared-reference inspection.

Groups are review projections, not identity merges or authorization to rewrite files.
Only small M3U/CUE metadata is read; images are probed for presence and size.
"""
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
from urllib.parse import unquote, urlsplit

import mtp_runtime as mtp
from content_scan import profiles, folders, read, join
from library_model import OPTICAL_SYSTEMS, DISC_FORMATS, build_library_model, disc_groups, _source_path
from rom_paths import rom_title
from artwork_identity import rom_search_alias, remembered

METADATA_LIMIT = 1024 * 1024
DISC = re.compile(r'(?<![A-Za-z0-9])(?:\(|\[)?(?:Disc|Disk|CD)\s*(\d+)(?:\s*(?:of|/)\s*(\d+))?(?:\)|\])?(?![A-Za-z0-9])', re.I)
REGIONS = {'j':'Japan','japan':'Japan','u':'USA','usa':'USA','e':'Europe','europe':'Europe','world':'World','taiwan':'Taiwan'}
SPECIAL = re.compile(r'\b(?:bonus|demo|sample|soundtrack|trial|taikenban)\b|附赠|附贈|试玩|試玩|特典|体験', re.I)


def disc_evidence(path, system):
    title = rom_title(unquote(path) if mtp.is_mtp(path) else path)
    markers = list(DISC.finditer(title))
    marker = markers[0] if len(markers) == 1 else None
    invalid = bool(marker and (not 1 <= int(marker[1]) <= 99 or (marker[2] and not 1 <= int(marker[2]) <= 99)))
    base = DISC.sub('', title).strip(' -_') if marker else title
    tags = re.findall(r'[\(\[]([^\)\]]+)[\)\]]', base)
    family = re.sub(r'\s*[\(\[].*?[\)\]]', '', base).strip(' -_')
    # Only explicit, reviewed shortened-title mappings, never generic CN stripping.
    alias = rom_search_alias(system, family) if family.casefold() in {'gulliverboy','chaosseed','chaos seed','srwf','srwff'} else None
    regions = sorted({REGIONS[tag.strip().casefold()] for tag in tags if tag.strip().casefold() in REGIONS})
    editions = sorted(tag.strip().casefold() for tag in tags if tag.strip().casefold() not in REGIONS)
    return {'family': alias or family, 'number': int(marker[1]) if marker and not invalid else None,
            'total': int(marker[2]) if marker and marker[2] and not invalid else None,
            'regions': regions, 'editions': editions, 'role':'extra' if SPECIAL.search(title) else 'game',
            'source':'curated_filename_alias' if alias else 'explicit_filename' if marker else 'unknown',
            'marker':marker[0] if marker else '', 'ambiguous_marker':len(markers) > 1 or invalid}


def parse_references(content, kind):
    """UTF-8 metadata boundary; preserve order and report malformed declarations."""
    text = content.decode('utf-8-sig')
    references, errors = [], []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or (kind == 'm3u' and line.startswith('#')):
            continue
        if kind == 'm3u':
            value = line
        elif re.match(r'^FILE\b', line, re.I):
            match = re.fullmatch(r'FILE\s+(?:"([^"]+)"|(\S+))\s+\S+', line, re.I)
            if not match:
                errors.append({'code':'invalid_reference','line':number,'message':'CUE FILE 声明无法解析'})
                continue
            value = match[1] or match[2]
        else:
            continue
        if not value or re.match(r'^[A-Za-z][\w+.-]*://', value) or value.startswith(('"', "'")):
            errors.append({'code':'invalid_reference','line':number,'message':'引用必须是未加引号的文件路径，不支持网络地址'})
        else:
            references.append({'value':value.replace('\\','/'),'line':number})
    if not references and not errors:
        errors.append({'code':'empty_descriptor','message':'未找到有效文件引用'})
    return references, errors


class Reader:
    def __init__(self, playlist):
        self.remote = mtp.is_mtp(playlist)
        self.device = urlsplit(playlist).netloc
        self.mappings = []
        self.directory_cache = {}
        if self.remote:
            mtp.parse(playlist)
            root = playlist.rsplit('/', 2)[0]
            for config in profiles().get(root, []):
                android, source = config.get('android_directory'), config.get('directory')
                if android and source and mtp.is_mtp(source) and urlsplit(source).netloc == urlsplit(playlist).netloc:
                    self.mappings.append((android.rstrip('/'), source.rstrip('/')))

    def locate(self, path):
        if self.remote:
            if mtp.is_mtp(path):
                mtp.parse(path)
                return path if urlsplit(path).netloc == self.device else None
            matches = [(prefix, source) for prefix, source in self.mappings if path == prefix or path.startswith(prefix + '/')]
            if not matches:
                return None
            length = max(len(prefix) for prefix, _ in matches)
            locations = {mtp.join(source, *path[len(prefix):].strip('/').split('/')) if path != prefix else source
                         for prefix, source in matches if len(prefix) == length}
            return locations.pop() if len(locations) == 1 else None
        if re.match(r'^\w+://', path) or (PureWindowsPath(path).is_absolute() and not Path(path).is_absolute()):
            return None
        return str(Path(path).expanduser().resolve())

    def probe(self, location):
        if not location:
            return {'status':'unmapped','size':None,'message':'缺少唯一的设备路径映射，尚未检查文件；请先保存对应目录的扫描配置'}
        try:
            if self.remote:
                serial, storage, parts = mtp.parse(location)
                parent = mtp.uri(serial, storage, '/'.join(parts[:-1]))
                if parent not in self.directory_cache:
                    self.directory_cache[parent] = mtp.listing(parent)
                info = next((entry for entry in self.directory_cache[parent] if parts and entry['name'] == parts[-1]), None)
                if info is None:
                    return {'status':'missing','size':None,'message':'文件不存在'}
                folder, size = info['folder'], info.get('size')
            else:
                target = Path(location)
                stat = target.stat()
                folder, size = target.is_dir(), stat.st_size
            return {'status':'invalid' if folder else 'present','size':None if folder else size,
                    'message':'目标是目录' if folder else ''}
        except FileNotFoundError:
            return {'status':'missing','size':None,'message':'文件不存在'}
        except (OSError, ValueError, RuntimeError) as error:
            return {'status':'unreadable','size':None,'message':str(error)}

    def metadata(self, location):
        return read(location)


def reference_path(parent, value):
    if PureWindowsPath(value).is_absolute() or value.startswith('/'):
        return value
    if mtp.is_mtp(parent):
        serial, storage, parts = mtp.parse(parent)
        relative = posixpath.normpath(posixpath.join('/'.join(parts[:-1]), value))
        if relative == '..' or relative.startswith('../'):
            raise ValueError('引用超出存储空间')
        return mtp.uri(serial, storage, relative)
    directory = parent.replace('\\', '/').rsplit('/', 1)[0]
    return posixpath.normpath(posixpath.join(directory, value))


def inspect_discs(playlist, system):
    if not isinstance(playlist, str) or not playlist or not playlist.lower().endswith('.lpl') or system not in OPTICAL_SYSTEMS:
        raise ValueError('请选择 Saturn 或 PlayStation 游戏列表')
    if playlist.startswith('adb://'):
        raise ValueError('当前多盘文件检查支持本地与 MTP 游戏库，请使用文件传输连接')
    requested_playlist = playlist
    reader = Reader(playlist)
    directory = playlist.rsplit('/', 1)[0]
    if not reader.remote:
        playlist = Path(playlist).expanduser().resolve().as_posix()
        directory = Path(playlist).parent.as_posix()
    nodes, locations, edges, errors, entries = {}, {}, [], [], []

    def node(path):
        try:
            location, invalid = reader.locate(path), None
        except ValueError as error:
            location, invalid = None, str(error)
        key = location or path
        if key not in nodes:
            nodes[key] = {'id':hashlib.sha256(key.encode('utf-8')).hexdigest()[:24], 'path':path,
                          'format':PurePosixPath(path).suffix.lower().lstrip('.'),
                          **({'status':'invalid','size':None,'message':invalid} if invalid else
                             {'status':'unchecked','size':None,'message':'压缩包内成员尚未检查；本次不读取整包内容'}
                             if re.search(r'\.(?:zip|7z|rar)#', path, re.I) else reader.probe(location)),
                          'playlist_references':[], 'issues':[], 'content_id':None, 'content_ids':[]}
            locations[nodes[key]['id']] = location
        return nodes[key]

    paths = [join(directory, entry['name']).replace('\\','/') for entry in folders(directory)
             if not entry['folder'] and entry['name'].lower().endswith('.lpl')]
    if playlist not in paths:
        paths.append(playlist)
    checked, entry_total = 0, 0
    for path in sorted(paths):
        try:
            data = read(path)
            if data is None:
                raise ValueError('列表不存在')
            document = json.loads(data.decode('utf-8-sig'))
            if not isinstance(document, dict) or not isinstance(document.get('items'), list):
                raise ValueError('列表不是有效 JSON 游戏列表')
            items = document['items']
            if any(not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in items):
                raise ValueError('列表条目路径无效')
        except (OSError, ValueError, RuntimeError) as error:
            if path == playlist:
                raise ValueError('无法读取当前列表：' + str(error)) from error
            errors.append({'path':path,'message':str(error)})
            continue
        checked += 1
        if path == playlist:
            entry_total = len(items)
        model = build_library_model(path, system if path == playlist else Path(path).stem, items)
        for index, item in enumerate(items):
            raw = item['path'].replace('\\','/')
            if not raw or raw == 'DETECT':
                if path == playlist:
                    errors.append({'path':path,'message':f'第 {index + 1} 项未指定启动文件'})
                continue
            logical = raw if raw.startswith(('/', 'mtp://')) or PureWindowsPath(raw).is_absolute() else reference_path(path, raw)
            content = node(logical)
            binding = model['entries'][index]
            if binding['content_id'] not in content['content_ids']:
                content['content_ids'].append(binding['content_id'])
            content['content_id'] = content['content_ids'][0] if len(content['content_ids']) == 1 else None
            record = {'playlist':path,'index':index,'label':item.get('label') or rom_title(logical),
                      'game_id':binding['game_id'],'disc_id':binding['disc_id'],'content_id':binding['content_id'],
                      'core_path':item.get('core_path') or document.get('default_core_path') or 'DETECT',
                      'node_id':content['id'],'launch_path':item['path']}
            if path == playlist:
                artwork_playlist = requested_playlist
                selection = remembered({'system':system,'playlist_path':artwork_playlist,'rom_path':item['path'],'label':item.get('label') or ''})
                if not selection and artwork_playlist != path:
                    artwork_playlist = path
                    selection = remembered({'system':system,'playlist_path':path,'rom_path':item['path'],'label':item.get('label') or ''})
                record['artwork_playlist_path'] = artwork_playlist
                record['artwork_sources'] = selection.get('sources') or ({'Named_Boxarts':selection['name']} if selection.get('name') else {})
            content['playlist_references'].append(record)
            if path == playlist:
                entries.append(record)

    queue = deque(nodes.values())
    processed = set()
    while queue:
        current = queue.popleft()
        if current['id'] in processed:
            continue
        processed.add(current['id'])
        if current['format'] in {'ccd','toc','gdi'}:
            current['issues'].append({'code':'descriptor_not_inspected','message':'当前仅解析 M3U 与 CUE，该描述文件的内部引用尚未检查'})
        if current['format'] not in {'m3u','cue'} or current['status'] != 'present':
            continue
        if current['size'] is None or current['size'] > METADATA_LIMIT:
            current['issues'].append({'code':'metadata_too_large','message':'引用文件超过 1 MiB，不读取其内容'})
            continue
        try:
            content = reader.metadata(locations[current['id']])
            if content is None:
                raise ValueError('引用文件在读取前已不可用')
            references, issues = parse_references(content, current['format'])
            current['issues'].extend(issues)
            for reference in references:
                try:
                    child = node(reference_path(current['path'], reference['value']))
                except ValueError as error:
                    current['issues'].append({'code':'invalid_reference','message':str(error),'line':reference['line']})
                    continue
                if current['format'] == 'm3u':
                    if child['format'] == 'm3u':
                        current['issues'].append({'code':'nested_m3u','message':'包含嵌套 M3U，需核对核心是否可加载'})
                    elif child['format'] not in DISC_FORMATS:
                        current['issues'].append({'code':'non_disc_reference','message':'M3U 引用了非光盘入口，CUE 游戏应引用 CUE 而非音轨'})
                    if any(edge['source'] == current['id'] and edge['target'] == child['id'] for edge in edges):
                        current['issues'].append({'code':'duplicate_reference','message':'M3U 重复引用同一文件','line':reference['line']})
                edges.append({'source':current['id'],'target':child['id'],'kind':current['format'],'line':reference['line']})
                queue.append(child)
        except (OSError, ValueError, RuntimeError) as error:
            current['issues'].append({'code':'metadata_unreadable','message':str(error)})

    files = {value['id']:value for value in nodes.values()}
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for edge in edges:
        outgoing[edge['source']].append(edge['target'])
        incoming[edge['target']].append(edge['source'])
    for value in files.values():
        value['referenced_by'] = list(dict.fromkeys(incoming[value['id']]))
        value['disc'] = disc_evidence(value['path'], system)

    def descendants(ident):
        seen, pending, cycles = set(), [(ident, ())], set()
        while pending:
            current, ancestors = pending.pop()
            if current in ancestors:
                cycles.add(current)
                continue
            if current in seen:
                continue
            seen.add(current)
            pending.extend((child, ancestors + (current,)) for child in outgoing[current])
        return seen, cycles

    groups, owned = [], set()
    entry_nodes = list(dict.fromkeys(entry['node_id'] for entry in entries))
    for ident in entry_nodes:
        if files[ident]['format'] != 'm3u':
            continue
        reached, cycles = descendants(ident)
        disc_ids = [key for key in reached if files[key]['format'] in DISC_FORMATS]
        # M3U line order is authoritative; do not replace it with filename sorting.
        ordered, pending, visited = [], [ident], set()
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            if key in disc_ids:
                ordered.append(key)
            if files[key]['format'] == 'm3u':
                pending.extend(reversed(outgoing[key]))
        groups.append({'kind':'m3u','members':[ident] + ordered, 'discs':ordered,
                       'files':sorted(reached),'cycles':sorted(cycles),'evidence':'existing_m3u'})
        owned.update(reached)
    candidates = defaultdict(list)
    singles = []
    for ident in entry_nodes:
        if ident in owned:
            continue
        value = files[ident]
        disc = value['disc']
        if value['format'] in DISC_FORMATS and disc['family'] and disc['number'] is not None and disc['role'] == 'game' and not disc['ambiguous_marker']:
            key = (posixpath.dirname(value['path']),disc['family'].casefold(),tuple(disc['regions']),tuple(disc['editions']))
            candidates[key].append(ident)
        else:
            singles.append(ident)
    for members in candidates.values():
        members.sort(key=lambda key:(files[key]['disc']['number'],files[key]['path']))
        reached, cycles = set(), set()
        for ident in members:
            children, loop = descendants(ident);reached.update(children);cycles.update(loop)
        groups.append({'kind':'disc_set','members':members,'discs':members,'files':sorted(reached),
                       'cycles':sorted(cycles),'evidence':'explicit_filename'})
        owned.update(reached)
    singles.sort(key=lambda key:files[key]['format'] not in DISC_FORMATS)
    for ident in singles:
        if ident in owned:
            continue
        reached, cycles = descendants(ident)
        groups.append({'kind':'single','members':[ident], 'discs':[ident] if files[ident]['format'] in DISC_FORMATS else [],
                       'files':sorted(reached),'cycles':sorted(cycles),'evidence':'playlist_entry'})
        owned.update(reached)

    associations=disc_groups()['groups']
    for group in groups:
        launch=files[group['members'][0]]['path']
        key=json.dumps([_source_path(playlist),system,launch],ensure_ascii=False,separators=(',',':'))
        saved=associations.get(key,{}) if group['kind']=='m3u' else {}
        group['disc_records']={}
        for disc in saved.get('discs',[]):
            ident=next((value for value in group['discs'] if files[value]['path']==disc['path']),None)
            if ident:
                group['disc_records'][ident]=disc['entry']
                content_id=disc['entry']['content_id']
                if content_id not in files[ident]['content_ids']: files[ident]['content_ids'].append(content_id)
                files[ident]['content_id']=files[ident]['content_ids'][0] if len(files[ident]['content_ids'])==1 else None
    families, family_paths = defaultdict(set), defaultdict(set)
    for value in files.values():
        if value['format'] in DISC_FORMATS:
            disc = value['disc']
            family = (posixpath.dirname(value['path']),disc['family'].casefold())
            families[family].add((tuple(disc['regions']),tuple(disc['editions'])))
            family_paths[family].add(value['path'])
    for group in groups:
        issues = []
        for ident in group['files']:
            value = files[ident]
            issues.extend({**issue,'path':value['path']} for issue in value['issues'])
            if value['status'] != 'present':
                issues.append({'code':value['status'],'path':value['path'],'message':value['message']})
            if len(value['content_ids']) > 1:
                issues.append({'code':'path_alias','path':value['path'],'message':'同一文件有多个路径入口，请核对；原入口保留'})
            if sum(entry['playlist'] == playlist for entry in value['playlist_references']) > 1:
                issues.append({'code':'duplicate_entry','path':value['path'],'message':'当前列表重复声明了同一文件入口'})
            if len({entry['playlist'] for entry in value['playlist_references']}) > 1:
                issues.append({'code':'shared_playlist','path':value['path'],'message':'此文件还被其他列表引用'})
            if len(set(incoming[ident])) > 1:
                issues.append({'code':'shared_reference','path':value['path'],'message':'此文件被多个入口／描述文件引用'})
        discs = [files[key] for key in group['discs']]
        numbers = [value['disc']['number'] for value in discs if value['disc']['number'] is not None]
        totals = {value['disc']['total'] for value in discs if value['disc']['total'] is not None}
        expected = max([*numbers,*totals],default=0)
        missing = sorted(set(range(1,expected+1))-set(numbers))
        if missing:
            issues.append({'code':'missing_disc','message':'缺少盘号：' + ', '.join(map(str,missing))})
        repeated = [number for number,count in Counter(numbers).items() if count > 1]
        if repeated:
            issues.append({'code':'duplicate_disc','message':'重复盘号：' + ', '.join(map(str,sorted(repeated)))})
        if len(totals) > 1 or any(total < max(numbers,default=0) for total in totals):
            issues.append({'code':'disc_total_conflict','message':'声明的总盘数与盘号不一致'})
        variants = {(tuple(value['disc']['regions']),tuple(value['disc']['editions'])) for value in discs}
        if len(variants) > 1 or any(len(families[(posixpath.dirname(value['path']),value['disc']['family'].casefold())]) > 1 for value in discs):
            issues.append({'code':'version_conflict','message':'发现不同地区／修订／汉化标记，保持独立，需核对版本',
                           'related_paths':sorted({path for value in discs for path in family_paths[(posixpath.dirname(value['path']),value['disc']['family'].casefold())]})})
        if len({value['disc']['family'].casefold() for value in discs}) > 1:
            issues.append({'code':'title_conflict','message':'M3U 引用了不同游戏名称，需核对'})
        if any(value['disc']['role'] == 'extra' for value in discs):
            issues.append({'code':'extra_disc','message':'包含附赠／试玩／特典盘，不能当作连续正篇光盘'})
        if group['cycles']:
            issues.append({'code':'reference_cycle','message':'引用中存在循环'})
        if any(value['disc']['ambiguous_marker'] for value in discs):
            issues.append({'code':'ambiguous_disc','message':'盘号标记有歧义或超出支持范围，请核对'})
        core_paths = {entry['core_path'] for ident in group['members'] for entry in files[ident]['playlist_references'] if entry['playlist'] == playlist}
        if len(core_paths) > 1:
            issues.append({'code':'core_conflict','message':'组内现有单项核心不同，未替换其设置'})
        group['id'] = hashlib.sha256(json.dumps([playlist,group['kind'],group['members']],sort_keys=True).encode()).hexdigest()[:24]
        group['label'] = next((entry['label'] for entry in entries if entry['node_id'] == group['members'][0]), rom_title(files[group['members'][0]]['path']))
        first_path = unquote(files[group['members'][0]]['path'])
        if group['kind'] == 'disc_set':
            group['label'] = (files[group['members'][0]]['disc']['family']
                              if group['label'] in {PurePosixPath(first_path).name, rom_title(first_path)}
                              else DISC.sub('', group['label']).strip(' -_')) or files[group['members'][0]]['disc']['family']
        elif group['kind'] == 'm3u' and group['label'] == PurePosixPath(first_path).name:
            group['label'] = rom_title(first_path)
        group['issues'] = issues
        group['status'] = 'attention' if issues else 'configured' if group['kind']=='m3u' else 'candidate' if group['kind']=='disc_set' else 'single'
        group['total_known'] = len(totals) == 1
        group['entry_indices'] = [entry['index'] for entry in entries if entry['node_id'] in group['files']]
    return {'version':1,'playlist_path':playlist,'system':system,'groups':groups,'files':list(files.values()),'references':edges,
            'entries':entries,'coverage':{'directory':directory,'playlists':checked,'files':len(files),'errors':errors,'recursive':False},
            'summary':{'groups':len(groups),'discs':len({key for group in groups for key in group['discs']}),
                       'files':len({key for group in groups for key in group['files']}),'entries':entry_total,
                       'candidates':sum(group['kind']=='disc_set' for group in groups),'attention':sum(bool(group['issues']) for group in groups)},
            'note':'只读检查；候选分组不改写列表、M3U、核心或游戏文件。未声明总盘数时不能证明末尾无缺盘。'}


def game_content_files(reader, location, probe, kind):
    """Collect and size only the launch entry and its declared dependencies."""
    files = {location: probe}
    pending = [(location, probe, kind)]
    complete = True
    while pending:
        path, info, fmt = pending.pop()
        if fmt in {'ccd', 'toc', 'gdi'}:
            complete = False
        if fmt not in {'cue', 'm3u'}:
            continue
        size = info['size']
        if size is None or size > METADATA_LIMIT:
            complete = False
            continue
        try:
            content = reader.metadata(path)
            if content is None or len(content) > METADATA_LIMIT:
                complete = False
                continue
            refs, issues = parse_references(content, fmt)
            complete = complete and not issues
            for ref in refs:
                declared = reference_path(path, ref['value'])
                target = reader.locate(declared)
                if target is None:
                    files[declared] = reader.probe(None)
                elif target not in files:
                    files[target] = reader.probe(target)
                    pending.append((target, files[target], PurePosixPath(target).suffix.lower().lstrip('.')))
        except (OSError, ValueError, RuntimeError):
            complete = False
    entries = [{'path': path, **info} for path, info in files.items() if path != location]
    sizes = [info['size'] for info in files.values()]
    return entries, sum(sizes) if complete and all(size is not None for size in sizes) else None
