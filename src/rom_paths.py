"""Display and identify the actual ROM, including RetroArch archive members."""
from pathlib import PurePosixPath
import re


def rom_filename(path):
    normalized = str(path or '').replace('\\', '/')
    member = re.split(r'\.(?:zip|7z|rar)#', normalized, flags=re.IGNORECASE)[-1]
    return member.rsplit('/', 1)[-1]


def rom_title(path):
    return PurePosixPath(rom_filename(path)).stem


def artwork_titles(system, path, label=''):
    """DOS launch programs are not game titles; keep ROM display paths intact."""
    if system != 'DOS':
        return [rom_title(path), label]
    normalized = str(path or '').replace('\\', '/')
    archive = re.split(r'\.(?:zip|7z|rar)#', normalized, flags=re.IGNORECASE)
    if len(archive) > 1:
        title = archive[0].rsplit('/', 1)[-1]
    elif PurePosixPath(normalized).suffix.lower() in {'.exe', '.com', '.bat', '.conf'}:
        title = PurePosixPath(normalized).parent.name
        if title.casefold() in {'dos', 'roms', 'games', 'bin', 'dosbox', '.'}:
            title = ''
    else:
        title = rom_title(path)
    launch = PurePosixPath(rom_filename(path))
    if launch.suffix.lower() in {'.exe', '.com', '.bat', '.conf'} and str(label).casefold() == launch.stem.casefold():
        label = ''
    return list(dict.fromkeys(value for value in (label, title) if value))


DISC_SUFFIXES = {'.cue', '.chd', '.iso', '.bin', '.img', '.gdi', '.m3u'}
DISC_DESCRIPTORS = {'.m3u', '.cue', '.chd', '.iso', '.gdi'}
DISC_PRIORITY = {'.m3u': 0, '.cue': 1, '.chd': 2, '.iso': 3, '.gdi': 3, '.bin': 4, '.img': 4}


def _disc_title(path):
    """Title of one disc: track/side markers go, the disc number stays."""
    return re.sub(r'\s*\((?:Track|Side)\s+\d+[^)]*\)$', '', rom_title(path), flags=re.IGNORECASE).strip()


def _game_title(path):
    """Title of the whole game: disc markers go so an .m3u can own its disc files."""
    title = _disc_title(path)
    return re.sub(r'\s*[\(\[](?:Disc|Disk|CD)\s*\d+(?:\s*of\s*\d+)?[^\)\]]*[\)\]]$', '', title,
                  flags=re.IGNORECASE).strip()


def _suffix_of(item):
    return PurePosixPath(str(item.get('path', '')).replace('\\', '/')).suffix.lower()


def _game_key(path):
    normalized = str(path or '').replace('\\', '/')
    return str(PurePosixPath(normalized).parent) + '/' + _game_title(normalized).casefold()


def disc_group(path, label='', sibling_paths=None):
    """Group the files of one disc (cue with its tracks); different discs stay separate.

    Multi-disc titles only collapse when an .m3u is present, which is also what
    RetroArch does: without one, every disc is its own playlist entry.
    """
    normalized = str(path or '').replace('\\', '/')
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in DISC_SUFFIXES:
        return None
    parent = str(PurePosixPath(normalized).parent)
    return parent + '/' + _disc_title(path).casefold()


def preferred_disc_entry(entries):
    groups = {}
    for index, item in enumerate(entries):
        key = disc_group(item.get('path'), item.get('label'))
        if key:
            groups.setdefault(key, []).append((index, item))
    preferred = {}
    for key, group in groups.items():
        suffixes = {_suffix_of(item) for _, item in group}
        if len(group) < 2 or not suffixes & DISC_DESCRIPTORS:
            continue
        candidates = [pair for pair in group if _suffix_of(pair[1]) in DISC_DESCRIPTORS]
        selected = min(candidates, key=lambda pair: (DISC_PRIORITY.get(_suffix_of(pair[1]), 9), pair[0]))
        preferred[key] = selected[0]

    # An .m3u stands for its whole disc set, so the listed discs are not listed twice.
    m3u_owner = {}
    for index, item in enumerate(entries):
        if _suffix_of(item) == '.m3u':
            m3u_owner.setdefault(_game_key(item.get('path')), index)
    if m3u_owner:
        for index, item in enumerate(entries):
            if _suffix_of(item) == '.m3u':
                continue
            key = disc_group(item.get('path'), item.get('label'))
            owner = m3u_owner.get(_game_key(item.get('path')))
            if key and owner is not None and owner != index:
                preferred[key] = owner
    return preferred


def remove_disc_companions(items, selected_paths):
    """Remove raw-image playlist entries owned by selected same-disc descriptors.

    Retain actual files, other revisions and disc numbers. Labels are not identity.
    """
    selected = set(selected_paths)
    owners = {}
    for item in items:
        path = str(item.get('path') or '').replace('\\', '/')
        suffix = PurePosixPath(path).suffix.lower()
        if item.get('path') in selected and suffix in {'.cue', '.ccd', '.gdi'}:
            owners[str(PurePosixPath(path).with_suffix('')).casefold()] = suffix
    kept, removed = [], []
    for item in items:
        path = str(item.get('path') or '').replace('\\', '/')
        suffix = PurePosixPath(path).suffix.lower()
        stem = str(PurePosixPath(path).with_suffix('')).casefold()
        owner = owners.get(stem)
        if not owner and suffix == '.bin':
            owner = owners.get(re.sub(r'\s*\(track\s+\d+\)$', '', stem, flags=re.I))
        if (owner == '.cue' and suffix in {'.bin', '.img'}) or (owner == '.ccd' and suffix in {'.img', '.sub'}) or (owner == '.gdi' and suffix in {'.bin', '.raw'}):
            removed.append(item)
        else:
            kept.append(item)
    return kept, removed
