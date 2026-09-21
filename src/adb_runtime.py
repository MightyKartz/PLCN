"""Resolve the bundled Android bridge without relying on shell PATH setup."""
import shutil
import sys
import subprocess
import app_paths


def bundled_adb():
    return app_paths.resource_root() / 'platform-tools' / ('adb.exe' if sys.platform == 'win32' else 'adb')


def adb_executable():
    bundled = bundled_adb()
    if bundled.is_file():
        return str(bundled)
    if getattr(sys, 'frozen', False) and sys.platform in ('darwin', 'win32'):
        raise FileNotFoundError('安装包缺少 ADB，请重新下载完整的 PLCN 安装包')
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
