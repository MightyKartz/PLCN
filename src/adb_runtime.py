"""Resolve the bundled Android bridge without relying on shell PATH setup."""
from functools import lru_cache
import hashlib
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import app_paths


def bundled_adb():
    return app_paths.resource_root() / 'platform-tools' / ('adb.exe' if sys.platform == 'win32' else 'adb')


@lru_cache(maxsize=4)
def cached_windows_adb(source, cache):
    # The adb server may outlive its client. Run it outside the installed
    # directory so Windows can replace or remove the application files.
    digest = hashlib.sha256()
    for file in sorted(source.iterdir()):
        digest.update(file.name.encode('utf-8'))
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    destination = cache / 'adb' / digest.hexdigest()
    if not destination.is_dir():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            staged = shutil.copytree(source, Path(temporary) / 'platform-tools')
            try:
                staged.rename(destination)
            except FileExistsError:
                # Another instance using the same cache published this bundle.
                pass
    return destination / 'adb.exe'


def adb_executable():
    bundled = bundled_adb()
    if bundled.is_file():
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            return str(cached_windows_adb(bundled.parent, app_paths.cache_dir()))
        return str(bundled)
    if getattr(sys, 'frozen', False) and sys.platform in ('darwin', 'win32'):
        raise FileNotFoundError('安装包缺少 ADB，请重新下载完整的 RetroArch 助手安装包')
    return shutil.which('adb') or 'adb'


def adb_available():
    return bundled_adb().is_file() or bool(shutil.which('adb'))


def subprocess_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


def check_bundled_adb():
    path = bundled_adb()
    if not path.is_file():
        raise RuntimeError('Packaged ADB is missing')
    result = subprocess.run([str(path), 'version'], capture_output=True, text=True,
                            check=True, timeout=15, **subprocess_options())
    if 'Android Debug Bridge version' not in result.stdout:
        raise RuntimeError('Packaged ADB version check failed')
    return result.stdout.strip()


def usb_android_devices():
    """Expose Google USB-mode Android hardware even before ADB is available on macOS."""
    if sys.platform != 'darwin':
        return []
    import plistlib
    result = subprocess.run(['ioreg', '-r', '-c', 'IOUSBHostDevice', '-a'], capture_output=True, timeout=8, check=True)
    if not result.stdout.strip():
        return []
    devices = plistlib.loads(result.stdout)
    return [{'serial': device.get('USB Serial Number', ''),
             'label': device.get('USB Product Name') or 'Android USB'}
            for device in devices if device.get('idVendor') == 0x18d1]
