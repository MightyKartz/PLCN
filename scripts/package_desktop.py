"""Build on the host platform; validate the actual architecture and package entry."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app_version import VERSION as APP_VERSION
from app_brand import ENGLISH_NAME, BINARY_NAME, BUNDLE_NAME


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=['x64', 'arm64'], required=True)
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--installer', action='store_true')
    args = parser.parse_args()
    actual = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x64'
    if actual != args.arch:
        raise RuntimeError(f'Runner architecture {actual} does not match artifact label {args.arch}')
    os.chdir(Path(__file__).resolve().parents[1])
    if not args.skip_build:
        run([sys.executable, 'scripts/prepare_adb.py'])
        run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'desktop.spec'])
    if sys.platform == 'win32':
        binary = (Path('dist') / BINARY_NAME / (BINARY_NAME + '.exe')).resolve()
    elif sys.platform == 'darwin':
        binary = (Path('dist') / BUNDLE_NAME / 'Contents/MacOS' / BINARY_NAME).resolve()
        run(['plutil', '-lint', str(Path('dist') / BUNDLE_NAME / 'Contents/Info.plist')])
        run(['codesign', '--verify', '--deep', '--strict', str(Path('dist') / BUNDLE_NAME)])
    else:
        binary = (Path('dist') / BINARY_NAME / BINARY_NAME).resolve()
    with tempfile.TemporaryDirectory(prefix='plcn-bundle-check-') as temp:
        env = dict(os.environ, PLCN_HOME=temp)
        run([str(binary), '--self-check'], env=env, cwd=temp, timeout=60)
        assert json.loads((Path(temp) / 'self-check.json').read_text())['ok']
    if sys.platform == 'darwin':
        staging = Path('dist/RetroArchAssistant-dmg-staging')
        if staging.exists():
            raise RuntimeError('DMG staging already exists; use a clean build directory')
        staging.mkdir()
        # ditto preserves symlinks and bundle metadata.
        run(['ditto', str(Path('dist') / BUNDLE_NAME), str(staging / BUNDLE_NAME)])
        (staging / 'Applications').symlink_to('/Applications')
        run(['hdiutil', 'create', '-volname', ENGLISH_NAME, '-srcfolder', str(staging), '-ov', '-format', 'UDZO', f'dist/{BINARY_NAME}-macOS-{args.arch}.dmg'])
    elif sys.platform == 'win32':
        # Keep old desktop shortcuts usable after upgrading the existing install.
        shutil.copy2(binary, binary.with_name('PLCN.exe'))
        shutil.make_archive(f'dist/{BINARY_NAME}-Windows-{args.arch}-Portable', 'zip', 'dist', BINARY_NAME)
        if args.installer:
            compiler = shutil.which('ISCC') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
            run([compiler, '/DAppVersion=' + APP_VERSION, 'packaging/windows.iss'])


if __name__ == '__main__':
    main()
