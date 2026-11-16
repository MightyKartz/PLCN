"""Read-only overview built from the same game rows as the library browser."""
import mtp_runtime as mtp
from playlist_browser import read_playlist
from retroarch_scanner import scan_retroarch_target


def storage_kind(path):
    if path.startswith(('/storage/emulated/', '/sdcard/', '/storage/self/')):
        return 'internal'
    return 'card' if path.startswith('/storage/') else 'local'


def overview(root):
    scan = mtp.scan(root) if mtp.is_mtp(root) else scan_retroarch_target(root)
    result = []
    for playlist in scan['playlists']:
        if not playlist.get('valid'):
            continue
        library = read_playlist(playlist['path'], playlist['system'], scan.get('directories', {}).get('thumbnails', ''))
        locations = {}
        for item in library['items']:
            kind = storage_kind(item['rom_path'])
            location = locations.setdefault(kind, {'count': 0, 'covers': [], 'missing': 0})
            location['count'] += 1
            if item['image_url'] and len(location['covers']) < 3:
                location['covers'].append({'url': item['image_url'], 'label': item['label']})
            if any(state != 'exists' for state in item['artwork_status'].values()):
                location['missing'] += 1
        result.append({'system': playlist['system'], 'path': playlist['path'], 'locations': locations})
    return {'playlists': result}
