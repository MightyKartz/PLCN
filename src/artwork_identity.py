"""Resolve artwork names without changing playlist identity or guessing a sequel."""
import json
import re
from pathlib import Path
import hashlib

import app_paths
from rom_paths import rom_title
from safe_io import atomic_write_json, file_lock

# Curated title absent from the bundled translation catalog.
CURATED_NAMES = {'Nintendo - Game Boy Advance': {'好狗狗星系': 'Goodboy Galaxy'}}

# Numbered Chinese ROM names used by SNES collections. These are search aliases,
# not verified ROM identities; region/revision is still chosen from the gallery.
# Series order: https://www.nintendo.com/jp/fe/en/history/index.html
# Gallery spelling: https://thumbnails.libretro.com/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/Named_Boxarts/
SNES_FIRE_EMBLEM = {
    '3': 'Fire Emblem - Monshou no Nazo',
    '4': 'Fire Emblem - Seisen no Keifu',
    '5': 'Fire Emblem - Thracia 776',
}


def rom_search_alias(system, filename):
    if system not in {'Nintendo - Super Nintendo Entertainment System', 'SNES', 'SFC'}:
        return None
    match = re.fullmatch(r'(?:火焰之?[纹紋]章|火焰[纹紋]章|火[纹紋])([345])', title_key(filename))
    return SNES_FIRE_EMBLEM[match[1]] if match else None


def base_title(name):
    return re.sub(r'\s*[\(\[].*?[\)\]]', '', name).strip()


def title_key(name):
    return ''.join(c for c in base_title(str(name)).casefold() if c.isalnum())


def memory_key(context):
    values = [context.get(k, '') for k in ('system', 'playlist_path', 'rom_path', 'label')]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def remembered(context):
    path = app_paths.user_data_dir() / 'artwork-sources.json'
    try:
        return json.loads(path.read_text()).get(memory_key(context), {})
    except (OSError, ValueError):
        return {}


def remember(context, source, kind):
    path = app_paths.user_data_dir() / 'artwork-sources.json'
    with file_lock(path):
        data = json.loads(path.read_text()) if path.exists() else {}
        entry = data.setdefault(memory_key(context), {})
        entry['name'] = source
        entry.setdefault('sources', {})[kind] = source
        atomic_write_json(path, data)


def resolution(names, reason):
    names = sorted(set(n for n in names if n and re.search('[A-Za-z]', n)))
    if not names:
        return {'status': 'unresolved', 'reason': 'unknown', 'names': [], 'query': ''}
    groups = {title_key(n) for n in names}
    return {'status': 'resolved' if len(groups) == 1 else 'ambiguous', 'reason': reason,
            'names': names, 'query': names[0] if len(names) == 1 else base_title(names[0]) if len(groups) == 1 else ''}


def resolve(context, config_path=None):
    from artwork_resolver import validate_system
    from data_pack import open_database
    from manual_overrides import load_overrides, find_override, default_overrides_path
    system = validate_system(context.get('system', ''))
    saved = remembered(context)
    if saved.get('name'):
        name = saved.get('sources', {}).get(context.get('kind'), saved['name'])
        return resolution([name], 'remembered')
    # This browser context has no verified ROM checksum. CRC-specific rules must
    # not be promoted to a confirmed match using only a shared filename.
    rules = [entry for entry in load_overrides(default_overrides_path()) if not entry.get('crc32')]
    override = find_override(rules, system, {'path': context.get('rom_path')})
    if override and override.get('thumbnail_source'):
        return resolution([override['thumbnail_source']], 'confirmed')
    label = context.get('label', '')
    filename = rom_title(context.get('rom_path'))
    rom_alias = rom_search_alias(system, filename)
    if rom_alias:
        return resolution([rom_alias], 'rom_alias')
    curated = CURATED_NAMES.get(system, {})
    known = {curated[n] for n in (label, filename) if n in curated}
    if known:
        return resolution(known, 'curated')
    config = Path(config_path or app_paths.config_path())
    settings = json.loads(config.read_text()) if config.exists() else {}
    db = open_database(settings.get('rom_name_cn_path') or app_paths.default_source())
    try:
        systems = db.expand_system_mapping(system)
        placeholders = ','.join('?' for _ in systems)
        conn = db.get_connection()
        rows = conn.execute(f'SELECT english_name, chinese_name FROM translations WHERE system_base(system) IN ({placeholders})', systems).fetchall()
        rom_exact = {r['english_name'] for r in rows if filename.casefold() == r['english_name'].casefold()}
        if rom_exact:
            return resolution(rom_exact, 'database')
        exact = {r['english_name'] for r in rows if any(n and n.casefold() in (r['english_name'].casefold(), (r['chinese_name'] or '').casefold()) for n in (label, filename))}
        if exact:
            return resolution(exact, 'database')
        keys = {title_key(n) for n in (label, filename) if title_key(n)}
        matches = {r['english_name'] for r in rows if title_key(r['english_name']) in keys or title_key(r['chinese_name']) in keys}
        aliases = conn.execute(f'SELECT english_name, alias FROM aliases WHERE system_base(system) IN ({placeholders})', systems).fetchall()
        matches.update(r['english_name'] for r in aliases if title_key(r['alias']) in keys)
        if matches:
            return resolution(matches, 'alias')
    finally:
        db.close()
    # A supplied English ROM title is a search term, not a confirmed identity.
    english = [n for n in (filename, label) if re.search('[A-Za-z]', n) and not re.search('[\u3400-\u9fff]', n)]
    return resolution(english, 'filename')
