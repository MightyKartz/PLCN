"""Build the pinned macOS MTP runtime with lock/unlock session recovery."""
import hashlib
import io
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

SOURCE_URL = 'https://downloads.sourceforge.net/project/libmtp/libmtp/1.1.23/libmtp-1.1.23.tar.gz'
SOURCE_SHA256 = '74a2b6e8cb4a0304e95b995496ea3ac644c29371649b892b856e22f12a0bdeed'


def main():
    if sys.platform != 'darwin':
        raise RuntimeError('The bundled MTP runtime is built on macOS')
    root = Path(__file__).resolve().parents[1]
    patch = root / 'packaging/patches/libmtp-1.1.23-unlock-recovery.patch'
    prefix = root / 'build/libmtp'
    revision = SOURCE_SHA256 + ':' + hashlib.sha256(patch.read_bytes()).hexdigest() + ':' + platform.machine()
    marker = prefix / 'build-revision'
    if (prefix / 'lib/libmtp.dylib').is_file() and marker.is_file() and marker.read_text() == revision:
        print('Patched MTP runtime is current:', prefix)
        return
    archive = root / 'build/mtp-source/libmtp-1.1.23.tar.gz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        data = archive.read_bytes()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=90) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('libmtp source checksum differs from the reviewed archive')
    archive.write_bytes(data)
    source = archive.parent / 'libmtp-1.1.23'
    if source.exists():
        shutil.rmtree(source)
    # This exact archive is trusted only after verification against the pinned digest.
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        bundle.extractall(archive.parent)
    subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=source, check=True)
    subprocess.run(['./configure', '--prefix=' + str(prefix), '--disable-mtpz', '--disable-static', '--disable-doxygen'], cwd=source, check=True)
    subprocess.run(['make', '-C', 'src', '-j4'], cwd=source, check=True)
    subprocess.run(['make', '-C', 'src', 'install'], cwd=source, check=True)
    shutil.copyfile(source / 'COPYING', prefix / 'COPYING')
    marker.write_text(revision)
    print('Built MTP runtime with failed-session cleanup:', prefix)


if __name__ == '__main__':
    main()
