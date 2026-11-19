# Desktop bundle. Build independently on each target OS/architecture.
import os
import ctypes.util
import sys
from pathlib import Path

sys.path.insert(0, 'src')
from app_version import MACOS_BUNDLE_VERSION
from app_brand import NAME, BINARY_NAME, BUNDLE_NAME

adb_root = Path("build/platform-tools")
if not (adb_root / ("adb.exe" if sys.platform == "win32" else "adb")).is_file():
    raise RuntimeError("Run scripts/prepare_adb.py before packaging")
adb_binaries = [(str(p), "platform-tools") for p in adb_root.iterdir() if p.name == "adb" or p.suffix.lower() in (".exe", ".dll")]
adb_notices = [(str(adb_root / name), "platform-tools") for name in ("NOTICE.txt", "source.properties")]

mtp_binaries = []
mtp_notices = []
if sys.platform == 'darwin':
    mtp_library = Path('build/libmtp/lib/libmtp.dylib')
    if not mtp_library.is_file():
        raise RuntimeError('Run scripts/prepare_mtp.py before packaging on macOS')
    mtp_binaries = [(str(mtp_library), '.')]
    mtp_notices = [('build/libmtp/COPYING', 'licenses/libmtp'),
                   ('packaging/patches/libmtp-1.1.23-unlock-recovery.patch', 'licenses/libmtp')]
    for dependency in ('libusb',):
        for prefix in ('/opt/homebrew/opt', '/usr/local/opt'):
            license_file = Path(prefix) / dependency / 'COPYING'
            if license_file.exists():
                mtp_notices.append((str(license_file), 'licenses/' + dependency))
                break

a = Analysis(
    ['src/desktop.py'], pathex=['src'], binaries=adb_binaries + mtp_binaries,
    # Bundle the complete UI directory, including the split CSS and domain scripts.
    datas=[('src/templates', 'src/templates'), ('data/rom-name-cn', 'data/rom-name-cn'), ('data/libretro-db', 'data/libretro-db')] + adb_notices + mtp_notices,
    hiddenimports=['tkinter', 'tkinter.filedialog', 'tkinter.messagebox'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=BINARY_NAME, debug=False,
    icon='packaging/icons/app-icon.ico' if sys.platform == 'win32' else None,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    target_arch=os.environ.get('RETROARCH_ASSISTANT_TARGET_ARCH') or None,
    codesign_identity=os.environ.get('RETROARCH_ASSISTANT_CODESIGN_IDENTITY') or None,
    entitlements_file='packaging/macos-entitlements.plist' if sys.platform == 'darwin' else None,
)
bundle = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=BINARY_NAME)
if sys.platform == 'darwin':
    app = BUNDLE(
        bundle, name=BUNDLE_NAME, bundle_identifier='io.github.mightykartz.retroarchassistant',
        icon='packaging/icons/app-icon.icns',
        info_plist={
            'CFBundleName': NAME, 'CFBundleDisplayName': NAME,
            'CFBundleShortVersionString': MACOS_BUNDLE_VERSION,
            'CFBundleVersion': MACOS_BUNDLE_VERSION,
            'NSHighResolutionCapable': True,
        },
    )
