"""Read existing playlist entries and artwork without matching or writing names."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
import uuid

from artwork_resolver import ArtworkResolver, THUMBNAIL_TYPES, validate_system
from playlist_manager import PlaylistManager
from rom_paths import rom_filename, rom_title
from retroarch_scanner import is_adb_uri, materialize_adb_file


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
    resolver = None
    remote_lookups = {}
    image_error = ''
    if thumbnails:
        validate_system(system)
        if is_adb_uri(thumbnails):
            from single_artwork import remote_inventory
            try:
                remote_lookups = {kind: remote_inventory(thumbnails, system, kind) for kind in THUMBNAIL_TYPES}
            except Exception as error:
                image_error = str(error)
        else:
            resolver = ArtworkResolver(str(Path(thumbnails).expanduser()), system)

    entries = []
    read_version = uuid.uuid4().hex
    for index, item in enumerate(playlist.items):
        rom_path = str(item.get('path') or '')
        rom_name = rom_filename(rom_path)
        label = str(item.get('label') or '')
        image = None
        image_status = 'unreadable' if image_error else 'missing' if thumbnails else 'unconfigured'
        for kind in THUMBNAIL_TYPES:
            if resolver:
                resolved = resolver.resolve(label, kind, rom_path=rom_path)
                image = resolved['path']
                if resolved['status'] == 'invalid':
                    image_status = 'invalid'
            elif remote_lookups:
                from plcn import find_existing_boxart
                _, image = find_existing_boxart(thumbnails, system, rom_title(rom_path), label, label.split('(', 1)[0].rstrip(), lookup=remote_lookups[kind])
            if image:
                image_status = 'exists'
                break
        entries.append({'index': index, 'label': label, 'rom_name': rom_name, 'rom_path': rom_path,
                        'image_status': image_status, 'image_message': image_error, 'image_path': image,
                        'image_url': '/api/thumbnail/preview?path=' + quote(image, safe='') + '&v=read-' + read_version if image else None})
    return {'playlist_path': path, 'name': name, 'system': system, 'items': entries}
