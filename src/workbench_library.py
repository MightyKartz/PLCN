"""Read-only overview built from the same game rows as the library browser."""
import re

import mtp_runtime as mtp
from playlist_browser import read_playlist
from retroarch_scanner import scan_retroarch_target


def storage_kind(path):
    if path.startswith(('/storage/emulated/', '/sdcard/', '/storage/self/')):
        return 'internal'
    return 'card' if path.startswith('/storage/') else 'local'


def overview(root):
    scan = mtp.scan(root) if mtp.is_mtp(root) else scan_retroarch_target(root)
    return {'playlists': [playlist_overview(playlist, scan.get('directories', {}).get('thumbnails', ''))
                          for playlist in scan['playlists'] if playlist.get('valid')]}


def playlist_overview(playlist, thumbnails):
    library = read_playlist(playlist['path'], playlist['system'], thumbnails)
    locations = {}
    for item in library['items']:
        kind = storage_kind(item['rom_path'])
        location = locations.setdefault(kind, {'count': 0, 'covers': [], 'missing': 0, 'non_chinese_names': 0})
        location['count'] += 1
        if not re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]', item['label']):
            location['non_chinese_names'] += 1
        if item['image_url'] and item['artwork_status'].get('Named_Boxarts') == 'exists':
            covers = location['covers']
            if len(covers) < 5 and not any(cover['url'] == item['image_url'] for cover in covers):
                covers.append({'url': item['image_url'], 'label': item['label']})
        if item['artwork_status'].get('Named_Boxarts') != 'exists':
            location['missing'] += 1
    return {'system': playlist['system'], 'path': playlist['path'], 'locations': locations}
