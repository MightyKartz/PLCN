"""Read-only application resources and per-user writable state, independent of cwd."""
import os
from pathlib import Path
import sys



def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def user_data_dir(platform=None, environ=None, home=None):
    env = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    platform = platform or sys.platform
    if env.get('RETROARCH_ASSISTANT_HOME'):
        return Path(env['RETROARCH_ASSISTANT_HOME']).expanduser().resolve()
    if platform == 'win32':
        return Path(env.get('LOCALAPPDATA') or home / 'AppData' / 'Local') / 'RetroArchAssistant'
    if platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'RetroArchAssistant'
    return Path(env.get('XDG_DATA_HOME') or home / '.local' / 'share') / 'RetroArchAssistant'


def cache_dir():
    # Keep portable/test overrides entirely self-contained.
    if os.environ.get('RETROARCH_ASSISTANT_HOME') or sys.platform == 'win32':
        return user_data_dir() / 'cache'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'RetroArchAssistant'
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'RetroArchAssistant'


def config_path():
    return user_data_dir() / 'config.json'


def default_source():
    return resource_root() / 'data' / 'rom-name-cn'


def dat_storage():
    return cache_dir() / 'data'


def initialize():
    """Create the current application's writable directories."""
    user_data_dir().mkdir(parents=True, exist_ok=True)
    cache_dir().mkdir(parents=True, exist_ok=True)
