"""Read-only application resources and per-user writable state, independent of cwd."""
import json
import os
from pathlib import Path
import shutil
import sys

from safe_io import atomic_write_json, file_lock


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def user_data_dir(platform=None, environ=None, home=None):
    env = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    platform = platform or sys.platform
    if env.get('PLCN_HOME'):
        return Path(env['PLCN_HOME']).expanduser().resolve()
    if platform == 'win32':
        return Path(env.get('LOCALAPPDATA') or home / 'AppData' / 'Local') / 'PLCN'
    if platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'PLCN'
    return Path(env.get('XDG_DATA_HOME') or home / '.local' / 'share') / 'PLCN'


def cache_dir():
    # Keep portable/test overrides entirely self-contained.
    if os.environ.get('PLCN_HOME') or sys.platform == 'win32':
        return user_data_dir() / 'cache'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'PLCN'
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'PLCN'


def config_path():
    return user_data_dir() / 'config.json'


def default_source():
    return resource_root() / 'data' / 'rom-name-cn'


def dat_storage():
    return cache_dir() / 'data'


def legacy_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else resource_root()


def initialize(legacy=None):
    """Copy known legacy user files once; never remove or modify originals."""
    root = user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    cache_dir().mkdir(parents=True, exist_ok=True)
    marker = root / 'migration.json'
    if marker.exists():
        return
    old = Path(legacy) if legacy else legacy_root()
    with file_lock(marker):
        if marker.exists():
            return
        copied = []
        config = old / 'config.json'
        if not config_path().exists() and config.is_file() and config.resolve() != config_path().resolve():
            data = json.loads(config.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict):
                raise ValueError('旧配置必须是 JSON 对象；原文件已保留')
            for key, value in list(data.items()):
                if isinstance(value, str) and value and (key.endswith(('_path', '_dir', '_root')) or key == 'previous_rom_name_cn_path') and not value.startswith('adb://'):
                    if not Path(value).is_absolute():
                        candidate = old / value
                        data[key] = str(candidate.resolve())
            # Bundled data paths must not keep pointing into a onefile extraction.
            for key in ('rom_name_cn_path', 'single_rom_name_cn_path', 'batch_rom_name_cn_path'):
                value = data.get(key)
                if value and (not Path(value).exists() or Path(value) == old / 'data' / 'rom-name-cn'):
                    data.pop(key)
            old_override = Path(data.get('manual_overrides_path') or old / 'manual_overrides.json')
            new_override = root / 'manual_overrides.json'
            if old_override.is_file() and not new_override.exists():
                shutil.copy2(old_override, new_override)
                copied.append('manual_overrides.json')
            if old_override.is_file():
                data['manual_overrides_path'] = str(new_override)
            atomic_write_json(config_path(), data)
            copied.append('config.json')
        standalone = old / 'manual_overrides.json'
        if standalone.is_file() and not (root / standalone.name).exists():
            shutil.copy2(standalone, root / standalone.name)
            copied.append(standalone.name)
        atomic_write_json(marker, {'legacy_directory': str(old), 'copied': copied})
