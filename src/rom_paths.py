"""Display and identify the actual ROM, including RetroArch archive members."""
from pathlib import PurePosixPath
import re


def rom_filename(path):
    normalized = str(path or '').replace('\\', '/')
    member = re.split(r'\.(?:zip|7z|rar)#', normalized, flags=re.IGNORECASE)[-1]
    return member.rsplit('/', 1)[-1]


def rom_title(path):
    return PurePosixPath(rom_filename(path)).stem
