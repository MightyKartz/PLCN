"""Exercise distributed packages in isolated, disposable profiles.

Windows refuses to run if an existing installer registration would be affected.
macOS mounts the DMG read-only and tests a copied app, as a user would install it.
This checks executable/service lifecycle, not Gatekeeper or native dialog UX.
"""
import argparse
from contextlib import ExitStack, contextmanager
import json
import os
import re
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app_brand import NAME, ENGLISH_NAME, BINARY_NAME, BUNDLE_NAME


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=180, **kwargs)


def process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


@contextmanager
def service(binary, profile, mode='--no-browser', *, extra_env=None):
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RETROARCH_ASSISTANT_HOME=str(profile))
    env.update(extra_env or {})
    command = [str(binary), mode] if mode else [str(binary)]
    process = subprocess.Popen(command, cwd=profile, env=env, **process_options())
    client = requests.Session()
    client.trust_env = False
    url = None
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Desktop exited before becoming ready; inspect its isolated desktop.log')
            try:
                state = json.loads((profile / 'instance.json').read_text(encoding='utf-8'))
                assert state['pid'] == process.pid, 'Instance state belongs to another process'
                candidate = state['url']
                page = client.get(candidate, timeout=2)
                page.raise_for_status()
                reply = client.get(candidate + '/api/instance', timeout=2)
                reply.raise_for_status()
                assert reply.json()['instance_id'] == state['instance_id'], 'Port reached the wrong profile'
                url = candidate
                break
            except (OSError, ValueError, requests.RequestException):
                time.sleep(.2)
        if url is None:
            raise TimeoutError('Desktop did not become ready within 45 seconds')
        assert ('<title>' + NAME + '</title>').encode('utf-8') in page.content
        assets = set(re.findall(r'(?:src|href)="/assets/([^"/]+)"', page.text))
        assert assets, 'Packaged page has no UI assets'
        for asset in sorted(assets):
            response = client.get(url + '/assets/' + asset, timeout=5)
            response.raise_for_status()
            assert response.content, 'Empty packaged asset: ' + asset
        state = client.get(url + '/api/desktop', timeout=5).json()
        assert Path(state['data_dir']).resolve() == profile.resolve()
        yield url
        response = client.post(url + '/api/desktop/shutdown', json={}, headers={'Origin': url}, timeout=5)
        response.raise_for_status()
        assert response.json()['stopped']
        assert process.wait(timeout=15) == 0
        assert not (profile / 'instance.json').exists(), 'Instance marker survived clean shutdown'
    finally:
        # Only the child created by this check may be terminated on failure.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        client.close()


@contextmanager
def isolated_adb(binary):
    # The launcher discovers Android devices on startup. Keep its ADB server
    # separate and reap it before the installer tries to remove adb.exe.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    address = f'tcp:localhost:{port}'
    adb = binary.parent / '_internal' / 'platform-tools' / 'adb.exe'
    process = subprocess.Popen(
        [str(adb), '-L', address, 'server', 'nodaemon'], **process_options(),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Isolated ADB server did not start')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.5):
                    break
            except OSError:
                time.sleep(.1)
        yield {'ADB_SERVER_SOCKET': address}
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def check_binary(binary, workspace, window_preview=False):
    binary = binary.resolve()
    profile = workspace / 'user data 中文'
    profile.mkdir()
    marker = profile / 'keep-user-data.txt'
    marker.write_text('Keep settings when uninstalling', encoding='utf-8')
    env = dict(os.environ, RETROARCH_ASSISTANT_HOME=str(profile))
    run([str(binary), '--self-check'], cwd=profile, env=env, **process_options())
    check = json.loads((profile / 'self-check.json').read_text(encoding='utf-8'))
    assert check['ok'] and check['product'] == NAME
    with ExitStack() as stack:
        first_url = stack.enter_context(service(binary, profile))
        # Launching the same profile must reuse it and exit, leaving it running.
        run([str(binary), '--no-browser'], cwd=profile, env=env, **process_options())
        second_url = stack.enter_context(service(binary, workspace / 'second profile'))
        assert first_url != second_url, 'Two profiles shared one server port'
    if window_preview:
        preview = workspace / 'window profile'
        with ExitStack() as stack:
            adb_env = stack.enter_context(isolated_adb(binary)) if sys.platform == 'win32' else {}
            stack.enter_context(service(binary, preview, mode=None, extra_env=adb_env))
            log = preview / 'logs' / 'desktop.log'
            deadline = time.monotonic() + 30
            while 'GET /api/library/sources HTTP/' not in log.read_text(encoding='utf-8'):
                if time.monotonic() >= deadline:
                    raise TimeoutError('The WebView did not start the workbench')
                time.sleep(.2)
            env = dict(os.environ, RETROARCH_ASSISTANT_HOME=str(preview), **adb_env)
            run([str(binary)], cwd=preview, env=env, **process_options())
            activation = '"POST /api/desktop/activate HTTP/1.1" 200'
            assert activation in log.read_text(encoding='utf-8'), 'Second launch did not activate the window'
    assert marker.read_text(encoding='utf-8') == 'Keep settings when uninstalling'
    return marker


def installer_registration_exists():
    import winreg
    name = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{5E9907D4-B062-4E6A-AEB0-223E3249D942}_is1'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, name, 0, winreg.KEY_READ | view):
                    return True
            except FileNotFoundError:
                pass
    return False


def windows_shell_folder(folder_id):
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, folder_id, None, 0, buffer)
    if result != 0:
        raise OSError('Cannot locate user shortcut directory')
    return Path(buffer.value)


@contextmanager
def preserve_windows_shortcuts():
    # A portable install can have shortcuts without an installer registration.
    # Resolve actual shell folders (including redirected Desktop locations).
    paths = [windows_shell_folder(2) / ENGLISH_NAME / (ENGLISH_NAME + '.lnk'),
             windows_shell_folder(16) / (ENGLISH_NAME + '.lnk')]
    snapshots = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        yield
    finally:
        changed = []
        for path, before in snapshots.items():
            after = path.read_bytes() if path.exists() else None
            if after == before:
                continue
            changed.append(str(path))
            if before is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(before)
        if changed:
            raise AssertionError('Installer altered existing shortcuts; restored originals: ' + ', '.join(changed))


def check_installer(package, workspace, window_preview=False):
    if installer_registration_exists():
        raise RuntimeError('RetroArch Assistant already has an installer registration; use a clean Windows runner for this test')
    destination = workspace / 'installed app 中文'
    group = 'RetroArch Assistant smoke ' + workspace.name
    uninstaller = destination / 'unins000.exe'
    flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-']
    try:
        run([str(package), *flags, '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS',
             '/NOICONS', '/TASKS=', '/GROUP=' + group,
             '/DIR=' + str(destination), '/LOG=' + str(workspace / 'install.log')])
        assert installer_registration_exists(), 'Installer did not register the app'
        assert not (windows_shell_folder(2) / group / (ENGLISH_NAME + '.lnk')).exists(), 'Installer ignored /NOICONS'
        marker = check_binary(destination / (BINARY_NAME + '.exe'), workspace, window_preview)
    finally:
        if uninstaller.exists():
            run([str(uninstaller), *flags, '/LOG=' + str(workspace / 'uninstall.log')], cwd=workspace)
    assert not (destination / (BINARY_NAME + '.exe')).exists(), 'Uninstaller left the executable behind'
    assert not (destination / '_internal' / 'platform-tools' / 'adb.exe').exists(), 'Uninstaller left bundled ADB behind'
    assert not installer_registration_exists(), 'Uninstaller left its registry entry behind'
    assert marker.read_text(encoding='utf-8') == 'Keep settings when uninstalling', 'Uninstall removed user data'


def check_dmg(package, workspace, window_preview=False):
    mount = workspace / 'mounted dmg'
    mount.mkdir()
    run(['hdiutil', 'attach', str(package), '-readonly', '-nobrowse', '-mountpoint', str(mount)])
    try:
        bundle = workspace / 'installed app 中文' / BUNDLE_NAME
        bundle.parent.mkdir()
        run(['ditto', str(mount / BUNDLE_NAME), str(bundle)])
    finally:
        run(['hdiutil', 'detach', str(mount)])
    run(['codesign', '--verify', '--deep', '--strict', str(bundle)])
    check_binary(bundle / 'Contents/MacOS' / BINARY_NAME, workspace, window_preview)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--installer', type=Path)
    group.add_argument('--dmg', type=Path)
    group.add_argument('--binary', type=Path)
    parser.add_argument('--window-preview', action='store_true', help='Also launch and verify the embedded WebView')
    args = parser.parse_args()
    package = (args.installer or args.dmg or args.binary).resolve(strict=True)
    if args.installer and sys.platform != 'win32' or args.dmg and sys.platform != 'darwin':
        parser.error('Run the package check on its target operating system')
    # Retain failure logs for local/CI diagnosis; remove successful temporary data.
    workspace = Path(tempfile.mkdtemp(prefix='plcn-package-smoke-')).resolve()
    print('Package smoke workspace:', workspace, flush=True)
    if args.installer:
        with preserve_windows_shortcuts():
            check_installer(package, workspace, args.window_preview)
    elif args.dmg:
        check_dmg(package, workspace, args.window_preview)
    else:
        check_binary(package, workspace, args.window_preview)
    if args.window_preview:
        print('PASS: embedded WebView, activation and shutdown', flush=True)
    import shutil
    if workspace.parent == Path(tempfile.gettempdir()).resolve() and workspace.name.startswith('plcn-package-smoke-'):
        # Inno's detached cleanup process can briefly retain its uninstall log
        # after the uninstaller returns. Retry only Windows sharing/access errors.
        for attempt in range(50):
            try:
                shutil.rmtree(workspace)
                break
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in (5, 32) or attempt == 49:
                    raise
                time.sleep(.2)
    print('PASS: package resources, isolated profiles, single instance, port isolation, shutdown', flush=True)


if __name__ == '__main__':
    main()
