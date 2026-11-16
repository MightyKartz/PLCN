"""Exact title families: packaging and release metadata are not fuzzy matches."""
import re

from rom_paths import DISC_MARKER


METADATA = re.compile(
    r'(?:Japan|USA|Europe|Asia|World)(?:,\s*(?:Japan|USA|Europe|Asia|World))+|'
    r'Japan|USA|Europe|World|France|Germany|Italy|Spain|Taiwan|Korea|China|Australia|'
    r'J|U|E|CN|CHS|CHT|A|B|Leon-hen|Claire-hen|'
    r'(?:Disc|Disk|CD)\s*\d+(?:\s*of\s*\d+)?|Rev(?:ision)?\s*[\w.]+|\d+M(?:,\s*\d+M)*|'
    r'(?:En|Ja|Fr|De|Es|It|Zh|Ko|Pt|Nl|Sv|Ru)(?:,(?:En|Ja|Fr|De|Es|It|Zh|Ko|Pt|Nl|Sv|Ru))*|T[+-][^\[\]()]+', re.I)


def family_key(name):
    """Retain unknown edition/hack tags and all sequel/subtitle text."""
    name = DISC_MARKER.sub('', name).replace('（', '(').replace('）', ')')
    title = re.sub(r'\(([^()]*)\)|\[([^\[\]]*)\]',
                   lambda m: '' if METADATA.fullmatch(m[1] or m[2]) else m[0], name)
    title = DISC_MARKER.sub('', title)
    title = re.sub(r'\bCN\b', '', title, flags=re.I)
    return ''.join(c for c in title.casefold() if c.isalnum())


def keep_disc_marker(label, filename):
    disc = DISC_MARKER.search(filename)
    if disc and not DISC_MARKER.search(label):
        label += ' (Disc ' + (disc[1] or disc[2]) + ')'
    side = re.search(r'[（(]([AB])[）)]', filename, re.I)
    if side and not re.search(r'[（(][AB][）)]', label, re.I):
        label += ' (' + side[1].upper() + ')'
    return label


def recommend_source(names):
    return min(names, key=lambda n: (0 if '(Japan)' in n else 1 if '(USA)' in n else 2,
                                    [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', n)]))


def resolve_artwork(proposals, verify_artwork):
    """Choose a gallery image for known families without claiming ROM revision."""
    from gallery_names import release_tags
    from single_artwork import catalog_names
    catalogs = {}
    for row in proposals:
        if not row.get('default_recommendation') and (row.get('translation_match_source') != 'title_family' or (row['system'] == 'Sega - Saturn' and not row.get('automatic_name_match'))):
            continue
        if row.get('match_diagnostics', {}).get('conflicts'):
            continue
        if not row.get('thumbnail_source'):
            continue
        row['artwork_identity_status'] = 'resolved'
        if not verify_artwork:
            continue
        system = row['system']
        if system not in catalogs:
            try:
                catalogs[system] = catalog_names(system, 'Named_Boxarts')
            except (OSError, ValueError, RuntimeError) as error:
                catalogs[system] = error
        catalog = catalogs[system]
        if isinstance(catalog, Exception):
            row.update(thumbnail_source=None, artwork_gallery_status='unavailable', match_reason=str(catalog))
            continue
        source = row['thumbnail_source']
        row['artwork_query'] = source
        # A/B and translation tags are packaging, not a verified disc/region.
        constraints = {tag for tag in release_tags(source)
                       if tag not in {'a', 'b', 'chs', 'cht'}}
        families = {family_key(source)}
        if change_sources := row.get('chinese_title_sources'):
            families.update(family_key(name) for name in change_sources)
            constraints = set(row['chinese_title_constraints'])
        names = sorted(name for name in catalog if family_key(name) in families
                       and constraints <= release_tags(name))
        if not names:
            key = (system, 'Named_Snaps')
            if key not in catalogs:
                try:
                    catalogs[key] = catalog_names(system, 'Named_Snaps')
                except (OSError, ValueError, RuntimeError) as error:
                    catalogs[key] = error
            snapshots = catalogs[key]
            if not isinstance(snapshots, Exception):
                names = sorted(name for name in snapshots if family_key(name) in families
                               and constraints <= release_tags(name))
                if names:
                    row['artwork_cover_fallback'] = 'Named_Snaps'
        side = re.search(r'[（(]([AB])[）)]', source, re.I)
        if side:
            number = ord(side[1].upper()) - ord('A') + 1
            numbered = [name for name in names if (disc := DISC_MARKER.search(name)) and int(disc[1] or disc[2]) == number]
            names = numbered or [name for name in names if not DISC_MARKER.search(name)]
        row['artwork_candidates'] = names
        row['artwork_gallery_status'] = 'matched' if names else 'not_found'
        row['thumbnail_source'] = recommend_source(names) if names else None
        row['artwork_recommended'] = bool(names)
        row['match_reason'] = ('游戏名称已识别，已推荐匹配封面，可单独更换'
                               if names else '游戏名称已识别，图库未找到匹配封面')
        if row.get('artwork_cover_fallback'):
            row['match_reason'] = '缺少封面，默认使用同一游戏截图作为展示图，可单独更换'
