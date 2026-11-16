"""Recognize arcade support ROMs without treating their files as games."""
import re

from rom_paths import rom_title


def is_system_resource(item, system):
    system = item.get('db_name') or system
    if not any(name in system.casefold() for name in ('arcade', 'fbneo', 'mame')):
        return False
    # These identifiers also cover translated or renamed playlist labels.
    if rom_title(item.get('path') or '').casefold() in {'neogeo', 'pgm', 'skns', 'nmk004'}:
        return True
    return bool(re.search(r'\b(?:BIOS|Internal ROM)\s*$', item.get('label') or '', re.I))
