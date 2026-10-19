"""Read existing playlist entries and artwork without matching or writing names."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
import uuid

from artwork_resolver import ArtworkResolver, THUMBNAIL_TYPES, validate_system
from playlist_manager import PlaylistManager
from rom_paths import disc_group, preferred_disc_entry, rom_filename, rom_title
from retroarch_scanner import is_adb_uri, materialize_adb_file


def open_artwork_reader(thumbnails, system):
    """Prepare a shared reader for one artwork root; never raises for an unreadable device."""
    if not thumbnails:
        return None, {}, ''
    validate_system(system)
    if is_adb_uri(thumbnails):
        from single_artwork import remote_inventory
        try:
            return None, {kind: remote_inventory(thumbnails, system, kind) for kind in THUMBNAIL_TYPES}, ''
        except Exception as error:
            return None, {}, str(error)
    return ArtworkResolver(str(Path(thumbnails).expanduser()), system), {}, ''


def artwork_lookup_names(label, rom_path):
    """Names RetroArch itself tries, in the same order as ArtworkResolver."""
    return list(dict.fromkeys(value for value in
                             (rom_title(rom_path), label, str(label or '').split('(', 1)[0].rstrip()) if value))


def artwork_filenames(thumbnails, system, kind, remote_lookups=None):
    """Every filename present for one type, keeping the caller's case like RetroArch does."""
    if remote_lookups:
        return set(remote_lookups[kind]['filenames'])
    directory = Path(thumbnails).expanduser() / system / kind
    try:
        return {path.name for path in directory.iterdir() if path.is_file()}
    except OSError:
        return set()


def artwork_statuses(label, rom_path, resolver=None, remote_lookups=None, thumbnails='', system=''):
    """Per-type state for one entry; reads only, matches and writes nothing."""
    from plcn import find_existing_boxart
    statuses = {}
    for kind in THUMBNAIL_TYPES:
        status, path = 'missing', None
        if resolver is not None:
            resolved = resolver.resolve(label, kind, rom_path=rom_path)
            path = resolved['path']
            status = 'exists' if resolved['status'] in {'exists', 'reusable'} else 'invalid' if resolved['status'] == 'invalid' else 'missing'
        elif remote_lookups:
            _, path = find_existing_boxart(thumbnails, system, *artwork_lookup_names(label, rom_path), lookup=remote_lookups[kind])
            status = 'exists' if path else 'missing'
        statuses[kind] = {'status': status, 'path': path}
    return statuses


def read_playlist(path, system='', thumbnails=''):
    if not path:
        raise ValueError('请选择游戏列表')
    if is_adb_uri(path):
        # Rapid selections can overlap: never read another request's partial pull.
        with TemporaryDirectory(prefix='plcn-browse-') as temporary:
            playlist = PlaylistManager(materialize_adb_file(path, cache_dir=temporary))
    else:
        playlist = PlaylistManager(Path(path).expanduser())
    name = str(path).replace('\\', '/').rsplit('/', 1)[-1]
    system = system or name.removesuffix('.lpl')
    resolver, remote_lookups, image_error = open_artwork_reader(thumbnails, system)

    preferred = preferred_disc_entry(playlist.items)
    entries = []
    read_version = uuid.uuid4().hex
    for index, item in enumerate(playlist.items):
        disc_key = disc_group(item.get('path'), item.get('label'), [entry.get('path') for entry in playlist.items])
        if disc_key and disc_key in preferred and preferred[disc_key] != index:
            continue

        rom_path = str(item.get('path') or '')
        rom_name = rom_filename(rom_path)
        label = str(item.get('label') or '')
        statuses = artwork_statuses(label, rom_path, resolver=resolver, remote_lookups=remote_lookups,
                                    thumbnails=thumbnails, system=system)
        image = next((statuses[kind]['path'] for kind in THUMBNAIL_TYPES if statuses[kind]['path']), None)
        if image_error:
            image_status = 'unreadable'
        elif not thumbnails:
            image_status = 'unconfigured'
        elif image:
            image_status = 'exists'
        elif any(statuses[kind]['status'] == 'invalid' for kind in THUMBNAIL_TYPES):
            image_status = 'invalid'
        else:
            image_status = 'missing'
        entries.append({'index': index, 'label': label, 'rom_name': rom_name, 'rom_path': rom_path,
                        'image_status': image_status, 'image_message': image_error, 'image_path': image,
                        'artwork_status': {kind: statuses[kind]['status'] for kind in THUMBNAIL_TYPES},
                        'image_url': '/api/thumbnail/preview?path=' + quote(image, safe='') + '&v=read-' + read_version if image else None})
    return {'playlist_path': path, 'name': name, 'system': system, 'items': entries}
