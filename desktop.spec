# Desktop bundle. Build independently on each target OS/architecture.
import os
import sys

a = Analysis(
    ['src/desktop.py'], pathex=['src'], binaries=[],
    datas=[('src/templates', 'src/templates'), ('data/rom-name-cn', 'data/rom-name-cn')],
    hiddenimports=['tkinter', 'tkinter.filedialog', 'tkinter.messagebox'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='PLCN', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    target_arch=os.environ.get('PLCN_TARGET_ARCH') or None,
    codesign_identity=os.environ.get('PLCN_CODESIGN_IDENTITY') or None,
    entitlements_file='packaging/macos-entitlements.plist' if sys.platform == 'darwin' else None,
)
bundle = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PLCN')
if sys.platform == 'darwin':
    app = BUNDLE(
        bundle, name='PLCN.app', bundle_identifier='io.github.mightykartz.plcn',
        info_plist={
            'CFBundleName': 'PLCN', 'CFBundleDisplayName': 'PLCN',
            'CFBundleShortVersionString': os.environ.get('PLCN_VERSION', '3.2.0'),
            'CFBundleVersion': os.environ.get('PLCN_VERSION', '3.2.0'),
            'NSHighResolutionCapable': True,
        },
    )
