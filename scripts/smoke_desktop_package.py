"""Exercise distributed packages in isolated, disposable profiles.

Windows refuses to run if an existing installer registration would be affected.
macOS mounts the DMG read-only and tests a copied app, as a user would install it.
This checks executable/service lifecycle, not Gatekeeper or native dialog UX.
"""
import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import requests


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=180, **kwargs)


def process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


@contextmanager
def service(binary, profile):
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PLCN_HOME=str(profile))
    process = subprocess.Popen([str(binary), '--no-browser'], cwd=profile, env=env, **process_options())
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
                client.get(candidate, timeout=2).raise_for_status()
                reply = client.get(candidate + '/api/instance', timeout=2)
                reply.raise_for_status()
                assert reply.json()['instance_id'] == state['instance_id'], 'Port reached the wrong profile'
                url = candidate
                break
            except (OSError, ValueError, requests.RequestException):
                time.sleep(.2)
        if url is None:
            raise TimeoutError('Desktop did not become ready within 45 seconds')
        for asset in ('desktop.js', 'workflow.js', 'desktop.css'):
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


def check_binary(binary, workspace):
    binary = binary.resolve()
    profile = workspace / 'user data 中文'
    profile.mkdir()
    marker = profile / 'keep-user-data.txt'
    marker.write_text('Keep settings when uninstalling', encoding='utf-8')
    env = dict(os.environ, PLCN_HOME=str(profile))
    run([str(binary), '--self-check'], cwd=profile, env=env, **process_options())
    assert json.loads((profile / 'self-check.json').read_text())['ok']
    with ExitStack() as stack:
        first_url = stack.enter_context(service(binary, profile))
        # Launching the same profile must reuse it and exit, leaving it running.
        run([str(binary), '--no-browser'], cwd=profile, env=env, **process_options())
        second_url = stack.enter_context(service(binary, workspace / 'second profile'))
        assert first_url != second_url, 'Two profiles shared one server port'
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


def check_installer(package, workspace):
    if installer_registration_exists():
        raise RuntimeError('PLCN already has an installer registration; use a clean Windows runner for this test')
    destination = workspace / 'installed app 中文'
    uninstaller = destination / 'unins000.exe'
    flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-']
    try:
        run([str(package), *flags, '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS',
             '/NOICONS', '/TASKS=', '/DIR=' + str(destination), '/LOG=' + str(workspace / 'install.log')])
        assert installer_registration_exists(), 'Installer did not register the app'
        marker = check_binary(destination / 'PLCN.exe', workspace)
    finally:
        if uninstaller.exists():
            run([str(uninstaller), *flags, '/LOG=' + str(workspace / 'uninstall.log')], cwd=workspace)
    assert not (destination / 'PLCN.exe').exists(), 'Uninstaller left the executable behind'
    assert not installer_registration_exists(), 'Uninstaller left its registry entry behind'
    assert marker.read_text(encoding='utf-8') == 'Keep settings when uninstalling', 'Uninstall removed user data'


def check_dmg(package, workspace):
    mount = workspace / 'mounted dmg'
    mount.mkdir()
    run(['hdiutil', 'attach', str(package), '-readonly', '-nobrowse', '-mountpoint', str(mount)])
    try:
        bundle = workspace / 'installed app 中文' / 'PLCN.app'
        bundle.parent.mkdir()
        run(['ditto', str(mount / 'PLCN.app'), str(bundle)])
    finally:
        run(['hdiutil', 'detach', str(mount)])
    run(['codesign', '--verify', '--deep', '--strict', str(bundle)])
    check_binary(bundle / 'Contents/MacOS/PLCN', workspace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--installer', type=Path)
    group.add_argument('--dmg', type=Path)
    group.add_argument('--binary', type=Path)
    args = parser.parse_args()
    package = (args.installer or args.dmg or args.binary).resolve(strict=True)
    if args.installer and sys.platform != 'win32' or args.dmg and sys.platform != 'darwin':
        parser.error('Run the package check on its target operating system')
    # Retain failure logs for local/CI diagnosis; remove successful temporary data.
    workspace = Path(tempfile.mkdtemp(prefix='plcn-package-smoke-')).resolve()
    print('Package smoke workspace:', workspace, flush=True)
    if args.installer:
        check_installer(package, workspace)
    elif args.dmg:
        check_dmg(package, workspace)
    else:
        check_binary(package, workspace)
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
