"""Fetch only ADB and its dependencies from a checksum-pinned Google archive."""
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

ARCHIVES = {
    'darwin': ('darwin', 'ee39ad5967e95c2a07f04dbcbde96b1a0c916ba376096db5d2f498b7727a5d1d'),
    'win32': ('windows', '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99'),
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
    print('Prepared ADB 37.0.1:', root)


if __name__ == '__main__':
    main()
