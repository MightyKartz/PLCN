"""One display-name policy for every system; original paths remain untouched."""
import re

from rom_paths import DISC_MARKER, rom_title, rom_filename

VERSION = re.compile(r'\s*[（(\[]?\s*(v(?:ersion)?\s*\d+(?:\.\d+)+|rev(?:ision)?\s*(?:[A-Z]|\d+(?:\.\d+)*))\s*[）)\]]?\s*$', re.I)
SIDE = re.compile(r'[（(]([AB])[）)]', re.I)


def base_display_title(label):
    title = SIDE.sub('', DISC_MARKER.sub('', label)).rstrip()
    version = VERSION.search(title)
    return (title[:version.start()].rstrip(' -_') or title) if version else title


def normalize_proposals(proposals):
    groups = {}
    for row in proposals:
        label = row['new_label']
        source = rom_title(row['path'])
        disc = DISC_MARKER.search(label) or DISC_MARKER.search(source)
        side = SIDE.search(label) or SIDE.search(source)
        title = SIDE.sub('', DISC_MARKER.sub('', label)).rstrip()
        version = VERSION.search(title)
        title = base_display_title(label)
        source_version = VERSION.search(SIDE.sub('', DISC_MARKER.sub('', source)).rstrip())
        marker = ''
        if not rom_filename(row['path']).lower().endswith('.m3u'):
            marker = '（第' + str(int(disc[1] or disc[2])) + '盘）' if disc else '（' + side[1].upper() + '）' if side else ''
        row['display_metadata'] = {'original_label': label,
                                   'version': (version or source_version)[1] if version or source_version else '',
                                   'disc': disc[1] or disc[2] if disc else '', 'side': side[1].upper() if side else ''}
        row['new_label'] = title + marker
        groups.setdefault((row['system'], row['new_label']), []).append(row)
    # Keep versions visible only when they distinguish simultaneously listed ROMs.
    for group in groups.values():
        if len({row['path'] for row in group}) > 1 and len({row['display_metadata']['version'] for row in group}) > 1:
            for row in group:
                if row['display_metadata']['version']:
                    row['new_label'] += '（' + row['display_metadata']['version'] + '）'
