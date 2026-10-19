"""Stage one image for review, then write only its verified playlist destination."""
from adb_runtime import adb_executable, subprocess_options
import base64
import errno
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.parse import quote, unquote
import uuid

from PIL import Image, ImageOps
import requests

import app_paths
from artwork_resolver import THUMBNAIL_TYPES, sanitize_filename, validate_system, valid_png
from playlist_manager import PlaylistManager
from rom_paths import rom_title, remove_disc_companions
from retroarch_scanner import is_adb_uri, materialize_adb_file, parse_adb_uri, push_adb_file
from safe_io import atomic_write_bytes, atomic_write_json, file_lock

BASE = 'https://thumbnails.libretro.com'
LIMIT = 12 * 1024 * 1024
KIND_LABELS = {'Named_Boxarts': '封面', 'Named_Snaps': '游戏截图', 'Named_Titles': '标题图'}
# Gallery match grades, best first. A looser grade is only used when no stricter
# one matched, and every grade is still a proposal the user must confirm.
TIER_ORDER = {'exact': 0, 'catalog': 1, 'words': 2, 'fuzzy': 3}
FUZZY_GALLERY_MIN = 85


def digest(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None


def validated_kind(value):
    if value not in THUMBNAIL_TYPES:
        raise ValueError('请选择封面、截图或标题图')
    return value


def requested_kinds(payload):
    """Image types this preview should stage; a single type keeps the legacy request shape."""
    values = payload.get('kinds')
    if values is None:
        return [validated_kind(payload.get('kind', 'Named_Boxarts'))]
    if not isinstance(values, list):
        raise ValueError('请选择图片类型')
    kinds = [validated_kind(value) for value in dict.fromkeys(values)]
    if not kinds:
        raise ValueError('请至少选择一种图片类型')
    return kinds


def download(url, allow_missing=False):
    try:
        with requests.get(url, timeout=(8, 25), stream=True) as response:
            if response.status_code == 404:
                if allow_missing:
                    return None
                raise ValueError('在线图库未收录此图片，请搜索其他名称或导入本地图片')
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > LIMIT:
                    raise ValueError('图片或图库索引超过 12 MiB')
            return bytes(content)
    except requests.RequestException as error:
        raise RuntimeError('连接在线图库失败，请检查网络后重试') from error


class ImageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        if tag == 'a' and href.lower().endswith('.png'):
            name = unquote(href)
            if '/' not in name and '\\' not in name:
                self.names.add(name[:-4])


def catalog_names(system, kind):
    cache = app_paths.cache_dir() / 'artwork-index' / (digest((system + kind).encode()) + '.json')
    if cache.exists() and time.time() - cache.stat().st_mtime < 3600:
        return json.loads(cache.read_text(encoding='utf-8'))
    parser = ImageLinks()
    parser.feed(download(f'{BASE}/{quote(system, safe="")}/{kind}/').decode('utf-8'))
    names = sorted(parser.names)
    atomic_write_json(cache, names)
    return names


def catalog_image(system, kind, name):
    system, kind = validate_system(system), validated_kind(kind)
    if not name or name not in catalog_names(system, kind):
        raise ValueError('图库中没有此图片源，请重新搜索')
    cache = app_paths.cache_dir() / 'artwork-candidates' / (digest((system + kind + name).encode()) + '.png')
    if not cache.exists() or time.time() - cache.stat().st_mtime > 86400:
        content, _ = normalize_image(download(f'{BASE}/{quote(system, safe="")}/{kind}/{quote(name + ".png", safe="")}'))
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((240, 240))
            output = io.BytesIO(); image.save(output, format='PNG')
        atomic_write_bytes(cache, output.getvalue())
    return cache.read_bytes()


def gallery_matches(names, queries, query, fuzzy=False):
    """Grade every gallery filename against the query, most certain first.

    Tiers downgrade only when nothing stricter matched: an exact title, then a
    name containing every query word, then (manual search only) a close spelling.
    A graded candidate is still only a proposal — the user picks the image.
    """
    from artwork_identity import title_key, base_title
    word_sets = [re.findall(r'\w+', base_title(value).casefold()) for value in queries]
    word_sets = [group for group in word_sets if group]
    key = title_key(query)
    strict, loose = [], []
    for name in names:
        if name.casefold() == query.casefold() or title_key(name) == key:
            strict.append((name, 'exact', 100))
            continue
        words = re.findall(r'\w+', name.casefold())
        if any(all(word in words for word in group) for group in word_sets):
            strict.append((name, 'words', 90))
        elif fuzzy:
            score = fuzzy_ratio(base_title(query), base_title(name))
            if score >= FUZZY_GALLERY_MIN:
                loose.append((name, 'fuzzy', round(score)))
    found = strict or loose
    found.sort(key=lambda row: (TIER_ORDER[row[1]], -row[2], row[0]))
    return found


def fuzzy_ratio(left, right):
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return 0.0
    return float(fuzz.WRatio(str(left).casefold(), str(right).casefold()))


def search(payload):
    from artwork_identity import title_key
    from gallery_names import gallery_title_key
    from dos_artwork_names import search_names
    import name_suggestions
    if payload.get('provider') == 'wikipedia':
        from secondary_artwork import search as secondary_search
        return secondary_search(payload)
    if payload.get('provider', 'libretro') != 'libretro':
        raise ValueError('未知图片来源')
    system = validate_system(payload.get('system', ''))
    kind = validated_kind(payload.get('kind', 'Named_Boxarts'))
    query = str(payload.get('query', '')).strip().casefold()
    if len(query) < 2:
        raise ValueError('请输入至少两个字符，建议使用英文游戏名')
    names = catalog_names(system, kind)
    # A Chinese title cannot appear in the English gallery index: translate it
    # through the local catalog first, then search with the English names. An
    # exact catalog hit wins outright; a weak fuzzy name is only tried when
    # nothing stronger exists, and never more than one of them.
    hints = name_suggestions.suggest(system, query) if name_suggestions.has_cjk(query) else []
    strong = [hint for hint in hints if hint['tier'] != 'fuzzy']
    if strong:
        expansion = strong[:4]
    else:
        close = [hint for hint in hints if (hint['score'] or 0) >= 80]
        expansion = (close or hints)[:2]
    queries = list(search_names(system, query)) + [hint['english_name'] for hint in expansion]
    if payload.get('automatic'):
        keys = {gallery_title_key(system, value) for value in queries}
        graded = [(name, 'exact' if name.casefold() == query else 'words', 100 if name.casefold() == query else 90)
                  for name in names if gallery_title_key(system, name) in keys]
        graded.sort(key=lambda row: (TIER_ORDER[row[1]], row[0]))
    else:
        graded = gallery_matches(names, queries, query, fuzzy=True)
    shown = graded[:24]
    hinted = {title_key(hint['english_name']): hint for hint in hints}
    candidates = []
    for name, grade, score in shown:
        hint = hinted.get(title_key(name))
        # A Chinese query can only reach the English index through the catalog,
        # so say so instead of claiming keyword matches the user did not type.
        tier = 'catalog' if hint and name_suggestions.has_cjk(query) else grade
        candidates.append({'name': name, 'tier': tier, 'score': hint['score'] if tier == 'catalog' else score,
                           'exact': grade == 'exact', 'hint': hint,
                           'image_url': '/api/artwork/thumbnail?system=' + quote(system, safe='') + '&kind=' + kind + '&name=' + quote(name, safe=''),
                           'provider': 'libretro', 'provider_label': 'Libretro · 官方图库', 'platform': system, 'version': name})
    # Nothing matched: still offer the catalog names so a Chinese-only title has a way in.
    suggestions = []
    if not graded:
        label = str(payload.get('label') or '').strip()
        suggestions = hints or (name_suggestions.suggest(system, label)
                                if name_suggestions.has_cjk(label) and title_key(label) != title_key(query) else [])
    return {'names': [candidate['name'] for candidate in candidates], 'total': len(graded),
            'provider': 'libretro', 'candidates': candidates, 'suggestions': suggestions}


def normalize_image(content):
    if len(content) > LIMIT:
        raise ValueError('图片不能超过 12 MiB')
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > 32_000_000:
                raise ValueError('请选择不超过 3200 万像素的 PNG、JPEG 或 WebP 图片')
            image = ImageOps.exif_transpose(image).convert('RGBA')
            output = io.BytesIO()
            image.save(output, format='PNG')
            result = output.getvalue()
            if len(result) > LIMIT:
                raise ValueError('转换后的 PNG 超过 12 MiB，请先缩小图片')
            return result, image.size
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('图片无法读取或已损坏') from error


def load_entry(payload):
    path = str(payload.get('playlist_path') or '')
    if not path:
        raise ValueError('请选择游戏列表')
    with TemporaryDirectory(prefix='plcn-artwork-list-') as temporary:
        local = materialize_adb_file(path, cache_dir=temporary) if is_adb_uri(path) else Path(path).expanduser()
        playlist = PlaylistManager(local)
    index = payload.get('index')
    if type(index) is not int or not 0 <= index < len(playlist.items):
        raise ValueError('游戏条目已改变，请重新选择')
    entry = playlist.items[index]
    if not entry.get('label') or entry.get('label') != payload.get('label') or str(entry.get('path') or '') != payload.get('rom_path'):
        raise ValueError('游戏名称或路径已改变，请重新选择')
    return playlist, entry


def entry_context(payload):
    from rom_paths import rom_filename, rom_title
    playlist, entry = load_entry(payload)
    filename = sanitize_filename(entry['label']).casefold()
    shared = [{'index': i, 'label': item.get('label'), 'rom_name': rom_filename(item.get('path'))}
              for i, item in enumerate(playlist.items)
              if sanitize_filename(item.get('label')).casefold() == filename]
    suggested = rom_title(entry.get('path')) or entry['label']
    used = {sanitize_filename(item.get('label')).casefold() for item in playlist.items}
    artwork = {}
    root = str(payload.get('thumbnails') or '').strip()
    if root:
        from playlist_browser import artwork_statuses, open_artwork_reader
        system = validate_system(payload.get('system', ''))
        resolver, remote_lookups, error = open_artwork_reader(root, system)
        if error:
            artwork = {kind: {'status': 'unreadable', 'message': error} for kind in THUMBNAIL_TYPES}
        else:
            artwork = artwork_statuses(entry['label'], entry.get('path'), resolver=resolver,
                                       remote_lookups=remote_lookups, thumbnails=root, system=system)
            if len(shared) > 1:
                from playlist_browser import artwork_filenames
                for kind in THUMBNAIL_TYPES:
                    used.update(name[:-4].casefold() for name in artwork_filenames(root, system, kind, remote_lookups)
                                if name.casefold().endswith('.png'))
    base = suggested
    number = 2
    while sanitize_filename(suggested).casefold() in used:
        suggested = f'{base} ({number})'
        number += 1
    return {'shared': shared if len(shared) > 1 else [], 'suggested_label': suggested, 'artwork': artwork}


def read_entry(payload):
    playlist, entry = load_entry(payload)
    label = str(payload.get('new_label') or entry['label']).strip()
    if not label or len(label.encode('utf-8')) > 220 or any(ord(c) < 32 for c in label):
        raise ValueError('请输入有效的独立游戏名称（不超过 220 字节）')
    filename = sanitize_filename(label) + '.png'
    if any(i != payload['index'] and (sanitize_filename(item.get('label')) + '.png').casefold() == filename.casefold()
           for i, item in enumerate(playlist.items)):
        raise ValueError('此图片名称仍被其他游戏共用，请输入独立名称后重新预览')
    return playlist.loaded_digest, filename


def read_target(target):
    if not is_adb_uri(target):
        path = Path(target)
        if not path.exists():
            return None
        if path.stat().st_size > LIMIT:
            raise ValueError('已有图片超过 12 MiB，无法安全备份')
        return path.read_bytes()
    serial, remote = parse_adb_uri(target)
    name = shlex.quote(remote)
    script = f'if test -f {name}; then test "$(wc -c < {name})" -le {LIMIT} && cat {name}; elif test ! -e {name}; then exit 44; else exit 1; fi'
    # shell -T keeps binary bytes intact and propagates the remote exit status;
    # exec-out can report success for an absent file and hide disconnect errors.
    result = subprocess.run([adb_executable(), '-s', serial, 'shell', '-T', script], capture_output=True, timeout=25, **subprocess_options())
    if result.returncode == 44:
        return None
    if result.returncode or len(result.stdout) > LIMIT:
        raise RuntimeError('无法读取设备图片，请检查 ADB 连接、目录权限和文件大小')
    return result.stdout


def adb_command(serial, script):
    result = subprocess.run([adb_executable(), '-s', serial, 'shell', script], capture_output=True, text=True, timeout=25, **subprocess_options())
    if result.returncode:
        raise RuntimeError('设备操作失败：' + (result.stderr.strip() or result.stdout.strip() or '请检查连接与权限'))
    return result.stdout


def remote_inventory(root, system, kind):
    serial, remote = parse_adb_uri(root)
    path = remote.rstrip('/') + '/' + system + '/' + kind
    quoted = shlex.quote(path)
    output = adb_command(serial, f'if test -d {quoted}; then ls -1 {quoted}; elif test ! -e {quoted}; then exit 0; else exit 1; fi')
    return {'type': 'adb', 'serial': serial, 'base_path': path, 'filenames': set(output.splitlines())}


def image_status(path):
    try:
        content = read_target(path)
        return {'status': 'missing' if content is None else 'exists' if valid_png(content) else 'invalid'}
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return {'status': 'unreadable'}


def existing_rom_target(payload, target):
    """RetroArch 1.20 tries the ROM basename before the playlist label."""
    name = sanitize_filename(rom_title(payload.get('rom_path')))
    if not name:
        return None
    if is_adb_uri(target):
        alias = target.rsplit('/', 1)[0] + '/' + name + '.png'
        if alias == target:
            return None
        content = read_target(alias)
    else:
        alias_path = Path(target).parent / (name + '.png')
        alias = str(alias_path)
        if alias_path == Path(target):
            return None
        content = read_target(alias)
    if content is None:
        return None
    playlist, _ = load_entry(payload)
    for index, item in enumerate(playlist.items):
        if index == payload['index']:
            continue
        keys = (sanitize_filename(rom_title(item.get('path'))), sanitize_filename(item.get('label')))
        if name.casefold() in {key.casefold() for key in keys}:
            raise ValueError('ROM 图片文件也被其他条目使用，无法单独更换；请先区分 ROM 文件名')
    return {'target': alias, 'original_digest': digest(content)}


def target_path(root, system, kind, filename):
    if is_adb_uri(root):
        return root.rstrip('/') + '/' + system + '/' + kind + '/' + filename
    return str(Path(root).expanduser().resolve() / system / kind / filename)


def candidate_source(payload, system, kind, allow_missing=False):
    """Return (content, source_name, provenance, online) for one image type."""
    if payload.get('candidate_id'):
        if kind != 'Named_Boxarts':
            raise ValueError('备用来源只提供封面')
        from secondary_artwork import content as secondary_content
        content, entry = secondary_content(payload['candidate_id'], system, kind)
        provenance = {key: entry[key] for key in ('provider', 'provider_label', 'source_page', 'platform', 'version') if key in entry}
        return content, entry['name'], provenance, False
    if payload.get('upload'):
        try:
            content = base64.b64decode(payload['upload'], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError('无法读取所选图片') from error
        return content, str(payload.get('filename') or '本地图片'), {}, False
    source = str(payload.get('source') or '').strip()
    if not source:
        raise ValueError('请输入图片源名称，或导入本地图片')
    url = f'{BASE}/{quote(system, safe="")}/{kind}/{quote(sanitize_filename(source) + ".png", safe="")}'
    return download(url, allow_missing=allow_missing), source, {}, True


def image_cache(directory, token, image):
    return directory / (image.get('cache') or (token + '.png'))


def manifest_images(manifest):
    """Every staged image in a receipt; receipts written before multi-type previews hold one."""
    images = manifest.get('images')
    if images:
        return images
    return [{'kind': manifest['kind'], 'target': manifest['target'], 'original_digest': manifest['original_digest'],
             'image_digest': manifest['image_digest'], 'cache': None, 'rom_target': manifest.get('rom_target'),
             'source': manifest.get('source'), 'online': manifest.get('online')}]


def remember_sources(manifest):
    """Persist each confirmed online source per type; never fail the write over memory."""
    from artwork_identity import remember
    context = {**manifest, 'label': manifest.get('new_label') or manifest['label']}
    failed = []
    for image in manifest_images(manifest):
        if not image.get('online') or not image.get('source'):
            continue
        try:
            remember(context, image['source'], image['kind'])
        except (OSError, ValueError, RuntimeError):
            failed.append(KIND_LABELS[image['kind']])
    return ('部分图片源未能保存供下次使用（' + '、'.join(failed) + '）') if failed else ''


def write_selected_images(manifest, directory, token, receipt):
    """Validate both names before mutation and recover interrupted multi-file writes."""
    images = manifest_images(manifest)
    assets = []
    for image in images:
        content = image_cache(directory, token, image).read_bytes()
        if digest(content) != image['image_digest']:
            raise RuntimeError('候选图片已改变，请重新预览')
        assets.append({'kind': image['kind'], 'target': image['target'], 'content': content,
                       'digest': image['image_digest'], 'original_digest': image['original_digest']})
        if image.get('rom_target'):
            assets.append({'kind': image['kind'], 'target': image['rom_target']['target'], 'content': content,
                           'digest': image['image_digest'], 'original_digest': image['rom_target']['original_digest']})
    for asset in assets:
        current = digest(read_target(asset['target']))
        if current != asset['original_digest'] and not (manifest.get('image_writes_started') and current == asset['digest']):
            raise RuntimeError('目标图片已改变，请重新预览后确认')
    manifest['image_writes_started'] = True
    atomic_write_json(receipt, manifest)
    backups = []
    for asset in assets:
        backup = asset['target'] + '.bak-' + token if asset['original_digest'] is not None else None
        if digest(read_target(asset['target'])) != asset['digest']:
            backup = write_target(asset['target'], asset['content'], asset['original_digest'], suffix=token)
        if backup and read_target(backup) is not None:
            backups.append({'kind': asset['kind'], 'target': asset['target'], 'backup': backup})
    return backups


def preview(payload):
    playlist_digest, filename = read_entry(payload)
    system = validate_system(payload.get('system', ''))
    kinds = requested_kinds(payload)
    root = str(payload.get('thumbnails') or '').strip()
    if not root:
        raise ValueError('请先在路径设置中指定图片目录')
    if is_adb_uri(root):
        serial, remote = parse_adb_uri(root)
        if not serial or not remote.strip('/'):
            raise ValueError('请选择设备上的图片目录')
    new_label = str(payload.get('new_label') or payload['label']).strip()
    renaming = new_label != payload['label']

    plans = []
    for kind in kinds:
        target = target_path(root, system, kind, filename)
        existing = read_target(target)
        if renaming and existing is not None:
            raise ValueError(f'独立名称对应的{KIND_LABELS[kind]}图片已存在，请换一个名称，避免覆盖其他图片')
        rom_target = existing_rom_target(payload, target)
        current_target = rom_target['target'] if rom_target else (
            target.rsplit('/', 1)[0] + '/' + sanitize_filename(payload['label']) + '.png' if renaming else target)
        plans.append({'kind': kind, 'target': target, 'existing': existing,
                      'rom_target': rom_target, 'current_target': current_target})

    staged, skipped = [], []
    for plan in plans:
        content, source, provenance, online = candidate_source(payload, system, plan['kind'], allow_missing=len(plans) > 1)
        if content is None:
            skipped.append({'kind': plan['kind'], 'label': KIND_LABELS[plan['kind']], 'reason': '在线图库未收录此类型图片'})
            continue
        content, size = normalize_image(content)
        staged.append({**plan, 'content': content, 'size': size, 'source': source, 'provenance': provenance, 'online': online})
    if not staged:
        raise ValueError('所选类型在在线图库都没有对应图片，请修改名称或导入本地图片')

    token = uuid.uuid4().hex
    directory = app_paths.cache_dir() / 'artwork-previews'
    directory.mkdir(parents=True, exist_ok=True)
    # Expired previews and receipts are disposable; backups live beside targets.
    for old in directory.iterdir():
        if old.is_file() and old.suffix in {'.json', '.png', '.lpl'} and time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)

    images, public = [], []
    for item in staged:
        # A single type keeps the original staged filename; several types need one file each.
        cache_name = f'{token}.png' if len(staged) == 1 else f'{token}-write-{item["kind"]}.png'
        atomic_write_bytes(directory / cache_name, item['content'])
        current_image = read_target(item['current_target'])
        has_current = current_image is not None and valid_png(current_image)
        images.append({'kind': item['kind'], 'cache': cache_name, 'target': item['target'],
                       'original_digest': digest(item['existing']), 'image_digest': digest(item['content']),
                       'rom_target': item['rom_target'], 'source': item['source'], 'online': item['online']})
        public.append({'kind': item['kind'], 'label': KIND_LABELS[item['kind']], 'target': item['target'],
                       'rom_target': item['rom_target']['target'] if item['rom_target'] else None,
                       'image_url': '/api/thumbnail/preview?path=' + quote(str(directory / cache_name), safe='') + '&v=after-' + token,
                       'current_image_url': '/api/thumbnail/preview?path=' + quote(item['current_target'], safe='') + '&v=before-' + token if has_current else None,
                       'current_status': 'missing' if current_image is None else 'exists' if has_current else 'invalid',
                       'replacing': item['existing'] is not None or item['rom_target'] is not None,
                       'source': item['source'], 'provenance': item['provenance'],
                       'width': item['size'][0], 'height': item['size'][1]})

    manifest = {key: payload.get(key) for key in ('playlist_path', 'index', 'label', 'rom_path', 'system')}
    manifest.update({'created': time.time(), 'playlist_digest': playlist_digest, 'images': images})
    playlist, _ = load_entry(payload)
    cleaned_items, removed = remove_disc_companions(playlist.items, [payload['rom_path']])
    if renaming or removed:
        playlist, _ = load_entry(payload)
        if playlist.loaded_digest != playlist_digest:
            raise RuntimeError('游戏列表已改变，请重新预览')
        playlist.items[payload['index']]['label'] = new_label
        playlist.data['items'], _ = remove_disc_companions(playlist.items, [payload['rom_path']])
        updated = (json.dumps(playlist.data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if len(updated) > LIMIT:
            raise ValueError('此游戏列表过大，请先通过批量整理区分名称')
        atomic_write_bytes(directory / (token + '.lpl'), updated)
        manifest.update({'new_label': new_label, 'updated_playlist_digest': digest(updated), 'companions': [], 'cleanup_only': not renaming})
        written_kinds = {image['kind'] for image in images}
        for other_kind in THUMBNAIL_TYPES:
            if not renaming or other_kind in written_kinds:
                continue
            other_root = plans[0]['target'].rsplit('/', 2)[0]
            other_target = other_root + '/' + other_kind + '/' + filename
            old_target = other_root + '/' + other_kind + '/' + sanitize_filename(payload['label']) + '.png'
            if read_target(other_target) is not None:
                raise ValueError('独立名称对应的其他类型图片已存在，请换一个名称')
            old_content = read_target(old_target)
            if old_content is not None:
                cache_name = token + '-' + other_kind + '.png'
                atomic_write_bytes(directory / cache_name, old_content)
                manifest['companions'].append({'kind': other_kind, 'target': other_target, 'cache': cache_name, 'digest': digest(old_content)})
    atomic_write_json(directory / (token + '.json'), manifest)
    primary = public[0]
    return {'token': token, 'new_label': new_label if renaming else None, 'images': public, 'skipped': skipped,
            'source': primary['source'], 'width': primary['width'], 'height': primary['height'],
            'provenance': primary['provenance'], 'replacing': primary['replacing'],
            'target': primary['target'], 'rom_target': primary['rom_target'],
            'image_url': '/api/thumbnail/preview?path=' + quote(str(directory / images[0]['cache']), safe=''),
            'current_image_url': primary['current_image_url'], 'current_status': primary['current_status']}


def backup_location(target, suffix):
    if target.lower().endswith('.lpl'):
        root = app_paths.user_data_dir() / 'playlist-backups'
        root.mkdir(parents=True, exist_ok=True)
        return str(root / (target.replace('\\', '/').rsplit('/', 1)[-1] + '.bak-' + suffix))
    return target + '.bak-' + suffix


def write_target(target, content, expected, suffix=None):
    before = read_target(target)
    if digest(before) != expected:
        raise RuntimeError('目标图片已改变，请重新预览后确认')
    suffix = suffix or uuid.uuid4().hex
    backup = backup_location(target, suffix) if before is not None else None
    if not is_adb_uri(target):
        if backup:
            atomic_write_bytes(backup, before)
            atomic_write_bytes(target, content, expected)
        else:
            # An external creator must not be overwritten between review and write.
            temporary = Path(target + '.plcn-' + suffix + '.tmp')
            atomic_write_bytes(temporary, content)
            try:
                try:
                    os.link(temporary, target)
                except OSError as error:
                    if error.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP):
                        raise
                    # FAT/exFAT SD cards do not support hard links. Reserve a new
                    # file exclusively, then replace only that empty reservation.
                    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                    try:
                        atomic_write_bytes(target, content, digest(b''))
                    except Exception:
                        if read_target(target) == b'':
                            Path(target).unlink(missing_ok=True)
                        raise
            finally:
                temporary.unlink(missing_ok=True)
    else:
        serial, remote = parse_adb_uri(target)
        staged = target + '.plcn-' + suffix + '.tmp'
        _, remote_stage = parse_adb_uri(staged)
        try:
            adb_command(serial, 'mkdir -p ' + shlex.quote(remote.rsplit('/', 1)[0]))
            with TemporaryDirectory(prefix='plcn-artwork-push-') as temporary:
                image = Path(temporary) / 'image.png'
                image.write_bytes(content)
                push_adb_file(str(image), staged)
            if digest(read_target(staged)) != digest(content):
                raise RuntimeError('设备暂存图片校验失败，原图未替换')
            if digest(read_target(target)) != expected:
                raise RuntimeError('设备图片已改变，请重新预览')
            if backup:
                if is_adb_uri(backup):
                    _, remote_backup = parse_adb_uri(backup)
                    adb_command(serial, f'cp {shlex.quote(remote)} {shlex.quote(remote_backup)}')
                else:
                    atomic_write_bytes(backup, before)
                if digest(read_target(backup)) != expected:
                    raise RuntimeError('旧图片备份校验失败，原图未替换')
            adb_command(serial, f'mv {shlex.quote(remote_stage)} {shlex.quote(remote)}')
        finally:
            try:
                adb_command(serial, f'rm -f {shlex.quote(remote_stage)}')
            except Exception:
                pass
    if digest(read_target(target)) != digest(content):
        raise RuntimeError('图片写入后校验失败，请重新读取；旧图备份：' + str(backup or '无'))
    return backup


def written_images(manifest, directory, token, backups):
    """Report one URL and backup per staged image, in the order they were previewed."""
    by_kind = {}
    for entry in backups:
        by_kind.setdefault(entry['kind'], entry)
    return [{'kind': image['kind'], 'target': image['target'], 'backup': by_kind.get(image['kind'], {}).get('backup'),
             'image_url': '/api/thumbnail/preview?path=' + quote(image['target'], safe='') + '&v=after-' + token}
            for image in manifest_images(manifest)]


def apply(token):
    if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
        raise ValueError('无效的图片预览，请重新选择')
    directory = app_paths.cache_dir() / 'artwork-previews'
    path = directory / (token + '.json')
    with file_lock(path):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest.get('result'):
            return manifest['result']
        if time.time() - manifest['created'] > 1800:
            raise ValueError('预览已过期，请重新核对图片')
        with file_lock(app_paths.cache_dir() / 'locks' / ('artwork-' + digest(manifest_images(manifest)[0]['target'].encode()))):
            if manifest.get('new_label'):
                result = apply_independent(manifest, directory, token, path)
            else:
                current_digest, _ = read_entry(manifest)
                if current_digest != manifest['playlist_digest']:
                    raise RuntimeError('游戏列表已改变，请重新预览图片')
                for image in manifest_images(manifest):
                    content = image_cache(directory, token, image).read_bytes()
                    if digest(content) != image['image_digest']:
                        raise RuntimeError('候选图片已改变，请重新预览')
                written = written_images(manifest, directory, token, write_selected_images(manifest, directory, token, path))
                result = {'images': written, 'target': written[0]['target'], 'backup': written[0]['backup'],
                          'index': manifest['index'], 'playlist_path': manifest['playlist_path'],
                          'label': manifest['label'], 'kind': written[0]['kind'], 'image_url': written[0]['image_url']}
            manifest['result'] = result
            atomic_write_json(path, manifest)
            warning = remember_sources(manifest)
            if warning:
                result['memory_warning'] = warning
            return result


def apply_independent(manifest, directory, token, receipt):
    """Create independent images first; publish the one-row label change last.

    A deterministic backup and recorded write progress allow a retry after a
    lost response. Unchanged shared images are never overwritten or deleted.
    """
    playlist_path = manifest['playlist_path']
    lock_path = app_paths.cache_dir() / 'locks' / ('playlist-' + digest(playlist_path.encode())) if is_adb_uri(playlist_path) else Path(playlist_path)
    with file_lock(lock_path):
        updated = (directory / (token + '.lpl')).read_bytes()
        if digest(updated) != manifest['updated_playlist_digest']:
            raise RuntimeError('候选游戏列表已改变，请重新预览')
        current = read_target(playlist_path)
        completed = digest(current) == manifest['updated_playlist_digest']
        if not completed:
            current_digest, _ = read_entry(manifest)
            if current_digest != manifest['playlist_digest']:
                raise RuntimeError('游戏列表已改变，请重新预览')
        images = manifest_images(manifest)
        own = {image['target']: image for image in images}
        assets = [{'target': image['target'], 'cache': image.get('cache') or token + '.png', 'digest': image['image_digest']}
                  for image in images] + manifest['companions']
        for asset in assets:
            content = (directory / asset['cache']).read_bytes()
            if digest(content) != asset['digest']:
                raise RuntimeError('候选图片已改变，请重新预览')
            existing = read_target(asset['target'])
            if manifest.get('writes_started') and digest(existing) == asset['digest']:
                continue
            original = own.get(asset['target'], {}).get('original_digest')
            expected_existing = manifest.get('cleanup_only') and original is not None and digest(existing) == original
            if completed or (existing is not None and not expected_existing):
                raise RuntimeError('独立图片位置已改变，请重新预览')
        for image in images:
            alias = image.get('rom_target')
            if not alias:
                continue
            current_alias = digest(read_target(alias['target']))
            if current_alias != alias['original_digest'] and not (manifest.get('image_writes_started') and current_alias == image['image_digest']):
                raise RuntimeError('ROM 图片已改变，请重新预览')
        manifest['writes_started'] = True
        atomic_write_json(receipt, manifest)
        # Every selected image is managed with its existing ROM alias as one resumable operation.
        backups = write_selected_images(manifest, directory, token, receipt)
        companion_errors = []
        for asset in manifest['companions']:
            if digest(read_target(asset['target'])) != asset['digest']:
                try:
                    write_target(asset['target'], (directory / asset['cache']).read_bytes(), None)
                except (OSError, RuntimeError) as error:
                    # Keep the selected image and name update; report unwritten companion images.
                    companion_errors.append(str(error))
        if companion_errors:
            print('Warning: Could not copy companion artwork: ' + ' | '.join(companion_errors))
        playlist_backup = backup_location(playlist_path, token)
        if not completed:
            try:
                write_target(playlist_path, updated, manifest['playlist_digest'], suffix=token)
            except Exception as error:
                raise RuntimeError('独立图片已准备，游戏列表写入未确认；可重试查询。备份位置：' + playlist_backup) from error
        written = written_images(manifest, directory, token, backups)
        result = {'images': written, 'target': written[0]['target'], 'backup': written[0]['backup'], 'playlist_backup': playlist_backup,
                  'index': manifest['index'], 'playlist_path': playlist_path, 'label': manifest['label'],
                  'new_label': manifest['new_label'], 'kind': written[0]['kind'], 'companion_warnings': companion_errors,
                  'image_url': written[0]['image_url']}
        warning = remember_sources(manifest)
        if warning:
            result['memory_warning'] = warning
        return result
