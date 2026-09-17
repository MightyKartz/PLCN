"""Local artwork resolution, shared naming rules, and image validation."""
import io
from rom_paths import rom_title
import os
from pathlib import Path
import re
from PIL import Image, UnidentifiedImageError

THUMBNAIL_TYPES = ('Named_Boxarts', 'Named_Snaps', 'Named_Titles')


def sanitize_filename(name):
    return re.sub(r'[&*/:`<>?\\|"\x00-\x1f]', '_', str(name or ''))


def validate_system(system):
    if not system or system in {'.', '..'} or any(c in system for c in '/\\:\x00'):
        raise ValueError('系统名必须是单个目录名称')
    return system


def artwork_path(root, system, label, kind='Named_Boxarts'):
    validate_system(system)
    if kind not in THUMBNAIL_TYPES or not label:
        raise ValueError('无效的图片类型或名称')
    return Path(root) / system / kind / (sanitize_filename(label) + '.png')


def valid_png(content):
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != 'PNG' or image.width * image.height > 32_000_000:
                return False
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
        return True
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return False


def valid_image_file(path):
    try:
        path = Path(path)
        return path.is_file() and path.stat().st_size <= 32 * 1024 * 1024 and valid_png(path.read_bytes())
    except OSError:
        return False


class ArtworkResolver:
    def __init__(self, root, system):
        self.root = root
        self.system = validate_system(system)
        self.files = {}
        for kind in THUMBNAIL_TYPES:
            directory = Path(root) / system / kind
            self.files[kind] = {p.name: p for p in directory.glob('*.png') if p.is_file()}
        self.validity = {}

    def resolve(self, label, kind='Named_Boxarts', source=None, rom_path=None, use_filename=True):
        names = []
        if use_filename and rom_path:
            names.append(rom_title(rom_path))
        names.append(label)
        # A short label can be used directly by RetroArch. A canonical source
        # image must be copied to the new label before it is reported as ready.
        short_label = str(label or '').split('(', 1)[0].rstrip()
        names.append(short_label)
        damaged = False
        for name in dict.fromkeys(names + [source]):
            if not name:
                continue
            candidate = self.files[kind].get(sanitize_filename(name) + '.png')
            if candidate:
                if candidate not in self.validity:
                    self.validity[candidate] = valid_image_file(candidate)
                if self.validity[candidate]:
                    return {'status': 'exists' if name in names else 'reusable', 'path': str(candidate), 'type': kind}
                damaged = True
        return {'status': 'invalid' if damaged else ('missing' if source else 'missing_source'), 'path': None, 'type': kind}

    def resolve_all(self, label, **kwargs):
        return {kind: self.resolve(label, kind, **kwargs) for kind in THUMBNAIL_TYPES}
