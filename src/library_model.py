"""Persistent local identities for playlist entries; never rewrite source playlists.

Paths bind UUIDs to today's files. Future move/conversion operations must explicitly
rebind these identities; equal labels and similar filenames are never identity proof.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import PurePosixPath, Path
import threading
from urllib.parse import unquote, urlsplit
import uuid
from typing import Optional

import app_paths
from rom_paths import DISC_MARKER, rom_filename, rom_title
from safe_io import atomic_write_json, file_lock


_index_lock = threading.RLock()
DISC_FORMATS = {'cue', 'chd', 'iso', 'ccd', 'toc', 'gdi'}
OPTICAL_SYSTEMS = {'Sega - Saturn', 'Sony - PlayStation', 'SS', 'PS1'}


@dataclass(frozen=True)
class ContentFile:
    id: str
    path: str
    format: str


@dataclass(frozen=True)
class Disc:
    id: str
    game_id: str
    content_id: str
    number: Optional[int]
    number_source: str


@dataclass(frozen=True)
class Game:
    id: str
    system: str
    display_name: str
    launch_content_id: str
    identity_source: str = 'playlist_entry'


def _source_path(path):
    # Device URIs are not host paths. Do not resolve Android paths on the host.
    if str(path).startswith(('mtp://', 'adb://')):
        parsed = urlsplit(path)
        return parsed.scheme + '://' + parsed.netloc + unquote(parsed.path)
    return str(Path(path).expanduser().resolve()).replace('\\', '/')


def _read_index(path):
    if not path.exists():
        return {'version': 1, 'content_ids': {}, 'game_ids': {}, 'disc_ids': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('无法读取本地游戏标识索引；请保留文件并检查：' + str(path)) from error
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('本地游戏标识索引版本无效：' + str(path))
    for field in ('content_ids', 'game_ids', 'disc_ids'):
        if not isinstance(data.get(field), dict):
            raise ValueError('本地游戏标识索引字段无效：' + field)
        for value in data[field].values():
            if not isinstance(value, str):
                raise ValueError('本地游戏标识不是 UUID：' + field)
            try:
                uuid.UUID(value)
            except ValueError as error:
                raise ValueError('本地游戏标识不是 UUID：' + field) from error
    return data


def disc_groups():
    path = app_paths.user_data_dir() / 'library-disc-groups.json'
    if not path.exists(): return {'version':1,'groups':{}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('version') != 1 or not isinstance(data.get('groups'),dict):
        raise ValueError('多盘关联索引无效，请保留文件并检查')
    return data


def build_library_model(playlist_path, system, items):
    """Assign identities to validated playlist rows and return an additive read model.

    One distinct playlist launch path is one game for now. Multi-disc grouping and
    parsing M3U references belong to stage two, not this migration.
    """
    source = _source_path(playlist_path)
    scope = source.rsplit('/', 1)[0]
    index_path = app_paths.user_data_dir() / 'library-identities.json'
    contents, discs, games, entries = {}, {}, {}, []
    with _index_lock, file_lock(index_path):
        index = _read_index(index_path)
        changed = False

        def identify(field, parts):
            nonlocal changed
            key = json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
            if key not in index[field]:
                index[field][key] = str(uuid.uuid4())
                changed = True
            return index[field][key]

        for row_index, item in enumerate(items):
            path = str(item.get('path') or '')
            # Empty/DETECT rows cannot identify a file. Keep them in the existing
            # browser response, without assigning an invented game identity.
            if not path or path == 'DETECT':
                entries.append({'index': row_index, 'game_id': None, 'content_id': None, 'disc_id': None})
                continue
            locator = path.replace('\\', '/')
            content_id = identify('content_ids', [scope, locator])
            game_id = identify('game_ids', [source, system, locator])
            extension = PurePosixPath(rom_filename(path)).suffix.lower().lstrip('.')
            contents[content_id] = ContentFile(content_id, path, extension)
            games.setdefault(game_id, Game(game_id, system, str(item.get('label') or ''), content_id))
            disc_id = None
            if system in OPTICAL_SYSTEMS and extension in DISC_FORMATS:
                disc_id = identify('disc_ids', [game_id, content_id])
                marker = DISC_MARKER.search(rom_title(path))
                number = int(marker[1] or marker[2]) if marker else None
                discs[disc_id] = Disc(disc_id, game_id, content_id, number, 'filename' if marker else 'unknown')
            entries.append({'index': row_index, 'game_id': game_id, 'content_id': content_id, 'disc_id': disc_id,
                            'core': {'path': item.get('core_path', ''), 'name': item.get('core_name', '')}})
        if changed:
            atomic_write_json(index_path, index)
    for group in disc_groups()['groups'].values():
        if group['playlist'] != source or group['game_id'] not in games:
            continue
        if games[group['game_id']].launch_content_id != group['launch_content_id']:
            continue
        for member in group['discs']:
            entry = member['entry']
            contents[entry['content_id']] = ContentFile(entry['content_id'], member['path'], member['format'])
            if entry['disc_id']:
                discs[entry['disc_id']] = Disc(entry['disc_id'], group['game_id'], entry['content_id'], member['number'], 'confirmed_group')
    return {'version': 1, 'scope': scope,
            'games': [asdict(value) for value in games.values()],
            'discs': [asdict(value) for value in discs.values()],
            'contents': [asdict(value) for value in contents.values()], 'entries': entries}
