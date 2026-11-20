"""Fetch only ADB and its dependencies from a checksum-pinned Google archive."""
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

ARCHIVES = {
    'darwin': ('darwin', 'df21339b9371fef9b19264404338dc686f59a88a1dce634b963da344909001d6'),
    'win32': ('windows', '89d108360a3bf2924d3bea837239edaccc22fd6ff5befd3787c4348a9fe4f09d'),
}


def main():
    host, expected = ARCHIVES[sys.platform]
    url = f'https://dl.google.com/android/repository/platform-tools-latest-{host}.zip'
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError('Google archive changed: review the new release and update the pinned SHA256 before building')
    files = ['NOTICE.txt', 'source.properties']
    files += ['adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'libwinpthread-1.dll'] if sys.platform == 'win32' else ['adb']
    root = Path(__file__).resolve().parents[1] / 'build' / 'platform-tools'
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in files:
            target = root / name
            target.write_bytes(archive.read('platform-tools/' + name))
            if name == 'adb':
                target.chmod(0o755)
    print('Prepared ADB 37.0.3:', root)


if __name__ == '__main__':
    main()
