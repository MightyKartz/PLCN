"""Display and identify the actual ROM, including RetroArch archive members."""
from pathlib import PurePosixPath
import re


def rom_filename(path):
    normalized = str(path or '').replace('\\', '/')
    member = re.split(r'\.(?:zip|7z|rar)#', normalized, flags=re.IGNORECASE)[-1]
    return member.rsplit('/', 1)[-1]


def rom_title(path):
    return PurePosixPath(rom_filename(path)).stem


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
