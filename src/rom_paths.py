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


def disc_group(path, label='', sibling_paths=None):
    normalized = str(path or '').replace('\\', '/')
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in {'.cue', '.chd', '.iso', '.bin', '.img', '.gdi', '.m3u'}:
        return None
    parent = str(PurePosixPath(normalized).parent)
    title = re.sub(r'\s*\((?:Track|Disc)\s+\d+[^)]*\)$', '', rom_title(path), flags=re.IGNORECASE).strip()
    sibling_suffixes = {PurePosixPath(str(value).replace('\\', '/')).suffix.lower() for value in sibling_paths or []}
    if suffix in {'.bin', '.img'} and '.cue' in sibling_suffixes:
        title = re.sub(r'\s*\(Track\s+\d+[^)]*\)$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\s*[\(\[](?:Disc)\s*\d+(?:\s*of\s*\d+)?[^\)\]]*[\)\]]$', '', title, flags=re.IGNORECASE).strip()
    return parent + '/' + title.casefold()


def preferred_disc_entry(entries):
    groups = {}
    sibling_paths = [entry.get('path') for entry in entries]
    for index, item in enumerate(entries):
        key = disc_group(item.get('path'), item.get('label'), sibling_paths)
        if key:
            groups.setdefault(key, []).append((index, item))
    preferred = {}
    priority = {'.m3u': 0, '.cue': 1, '.chd': 2, '.iso': 3, '.gdi': 3, '.bin': 4, '.img': 4}
    for key, group in groups.items():
        suffixes = {PurePosixPath(item.get('path', '')).suffix.lower() for _, item in group}
        if len(group) < 2 or not any(PurePosixPath(item.get('path', '')).suffix.lower() in {'.m3u', '.cue', '.chd', '.iso', '.gdi'} for _, item in group):
            continue
        candidates = [pair for pair in group if PurePosixPath(pair[1].get('path', '')).suffix.lower() in {'.m3u', '.cue', '.chd', '.iso', '.gdi'}]
        selected = min(candidates or group, key=lambda pair: (priority.get(PurePosixPath(pair[1].get('path', '')).suffix.lower(), 9), pair[0]))
        preferred[key] = selected[0]
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
