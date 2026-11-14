"""Exercise the real service and rendered UI with an isolated Chromium profile."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest
import requests

import app_paths
from database import DatabaseManager
import retroarch_scanner
import server
import single_artwork


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def chrome_binary():
    configured = os.environ.get('CHROME_BIN')
    if configured:
        assert Path(configured).is_file(), f'CHROME_BIN does not exist: {configured}'
        return configured
    candidates = [
        shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome')
    ]
    candidates.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable]) / 'Google/Chrome/Application/chrome.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    message = 'Browser smoke requires Chrome/Chromium; set CHROME_BIN to its executable'
    if os.environ.get('PLCN_REQUIRE_BROWSER') == '1':
        pytest.fail(message)
    pytest.skip(message)


@pytest.mark.parametrize('viewport', [(1440, 900), (1100, 700)], ids=['wide', 'compact'])
def test_home_to_library_to_preview(tmp_path, monkeypatch, chrome_binary, viewport):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('PLCN_HOME', str(home))
    monkeypatch.setattr(server, 'CONFIG_FILE', str(home / 'config.json'))
    monkeypatch.setattr(DatabaseManager, 'DB_FILE', str(home / 'cache/plcn.db'))
    monkeypatch.setattr(retroarch_scanner, 'list_adb_devices', lambda **kwargs: [])
    monkeypatch.setattr(retroarch_scanner, 'default_scan_candidates', lambda: [])
    monkeypatch.setattr(single_artwork, 'catalog_names', lambda *args: [])
    monkeypatch.setattr(server, 'job_manager', server.JobManager())
    source = tmp_path / 'names'
    source.mkdir()
    playlists = tmp_path / '游戏库/playlists'
    playlists.mkdir(parents=True)
    for fixture, system, english, chinese in [
        ('gba_polluted_label.lpl', 'Nintendo - Game Boy Advance', 'F-Zero - Maximum Velocity (USA, Europe)', '极速传说'),
        ('same_title_snes_shadowrun.lpl', 'Nintendo - Super Nintendo Entertainment System', 'Shadowrun (USA)', '暗影狂奔'),
    ]:
        shutil.copyfile(ROOT / 'tests/fixtures/playlists' / fixture, playlists / (system + '.lpl'))
        (source / (system + '.csv')).write_text(f'Name EN,Name CN\n"{english}",{chinese}\n', encoding='utf-8')
    app_paths.config_path().write_text(json.dumps({'rom_name_cn_path': str(source)}), encoding='utf-8')
    originals = {file: file.read_bytes() for file in playlists.iterdir()}

    artifacts = ROOT / 'output/playwright/browser-smoke' / f'{viewport[0]}x{viewport[1]}'
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in ('errors.json', 'failure.png', 'failure.html'):
        (artifacts / name).unlink(missing_ok=True)
    profile = tmp_path / 'chrome-profile'
    with server.LocalHTTPServer(('127.0.0.1', 0), server.ConfigHandler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with (artifacts / 'chrome.log').open('w', encoding='utf-8') as log:
                chrome = subprocess.Popen([
                    chrome_binary, '--headless=new', '--remote-debugging-port=0',
                    f'--user-data-dir={profile}', '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', 'about:blank',
                ], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 15
                    active_port = profile / 'DevToolsActivePort'
                    while not active_port.is_file():
                        assert chrome.poll() is None, f'Chrome exited; see {artifacts / "chrome.log"}'
                        assert time.monotonic() < deadline, f'Chrome startup timed out; see {artifacts / "chrome.log"}'
                        time.sleep(0.05)
                    port = int(active_port.read_text(encoding='utf-8').splitlines()[0])
                    response = requests.get(f'http://127.0.0.1:{port}/json/list', timeout=3)
                    response.raise_for_status()
                    targets = response.json()
                    websocket = next(target['webSocketDebuggerUrl'] for target in targets if target['type'] == 'page')
                    result = subprocess.run([
                        'node', str(ROOT / 'tests/browser_smoke.cjs'), websocket,
                        f'http://127.0.0.1:{httpd.server_address[1]}', str(playlists.parent),
                        str(viewport[0]), str(viewport[1]), str(artifacts),
                    ], capture_output=True, text=True, encoding='utf-8', timeout=45)
                    (artifacts / 'driver.log').write_text(result.stdout + result.stderr, encoding='utf-8')
                    assert result.returncode == 0, result.stdout + result.stderr
                finally:
                    chrome.terminate()
                    try:
                        chrome.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        chrome.kill()
                        chrome.wait()
        finally:
            httpd.shutdown()
            thread.join(2)
    assert {file: file.read_bytes() for file in playlists.iterdir()} == originals
