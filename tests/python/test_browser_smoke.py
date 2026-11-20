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
import playlist_service
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
    if os.environ.get('RETROARCH_ASSISTANT_REQUIRE_BROWSER') == '1':
        pytest.fail(message)
    pytest.skip(message)


@pytest.mark.parametrize('viewport', [(1440, 900), (1100, 700)], ids=['wide', 'compact'])
def test_home_to_library_to_preview(tmp_path, monkeypatch, chrome_binary, viewport):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('RETROARCH_ASSISTANT_HOME', str(home))
    monkeypatch.setattr(server, 'CONFIG_FILE', str(home / 'config.json'))
    monkeypatch.setattr(DatabaseManager, 'DB_FILE', str(home / 'cache/library.db'))
    monkeypatch.setattr(retroarch_scanner, 'list_adb_devices', lambda **kwargs: [])
    monkeypatch.setattr(retroarch_scanner, 'default_scan_candidates', lambda: [])
    monkeypatch.setattr(single_artwork, 'catalog_names', lambda *args: ['Shadowrun (USA)'])
    import io
    from PIL import Image
    png = io.BytesIO()
    Image.new('RGB', (12, 16), (30, 100, 200)).save(png, format='PNG')
    monkeypatch.setattr(single_artwork, 'catalog_image', lambda *args, **kwargs: png.getvalue())
    monkeypatch.setattr(single_artwork, 'download', lambda *args, **kwargs: png.getvalue())
    import core_catalog
    monkeypatch.setattr(core_catalog, 'info', lambda core: {'extensions':['cue','chd','m3u'], 'source':'https://fixture.invalid/core-info'})
    import library_sources
    monkeypatch.setattr(library_sources, 'usb_android_devices', lambda: [{'serial':'test-handheld','label':'Android handheld USB'}])
    monkeypatch.setattr(server, 'job_manager', server.JobManager())
    jobs = server.job_manager
    failed = jobs.create_job()
    jobs.contexts[failed] = {'thumbnails_dir': str(home / 'retry-images')}
    jobs.update_job(failed, 0, 3, '浏览器任务记录：开始补图')
    jobs.update_job(failed, 3, 3, '浏览器任务记录：部分完成')
    jobs.complete_job(failed, {'applied_count': 1, 'errors': ['NES：列表已变化，请重新预览'], 'download_summary': {
        'total': {'success': 1, 'failed': 1, 'skipped': 1},
        'types': {'Named_Boxarts': {'success': 1, 'failed': 0, 'skipped': 0},
                  'Named_Snaps': {'success': 0, 'failed': 1, 'skipped': 0},
                  'Named_Titles': {'success': 0, 'failed': 0, 'skipped': 1}},
        'details': [{'system': 'NES', 'source': 'Game', 'game': '游戏', 'type': 'Named_Snaps',
                     'status': 'failed', 'reason': 'network_error', 'message': '测试图片网络失败'}]}})
    from thumbnail_downloader import ThumbnailDownloader
    monkeypatch.setattr(ThumbnailDownloader, 'download_batch', lambda *args, **kwargs: ThumbnailDownloader.empty_summary())
    original_analyze = playlist_service.analyze_playlist
    def slow_analyze(*args, **kwargs):
        time.sleep(0.3)
        return original_analyze(*args, **kwargs)
    monkeypatch.setattr(playlist_service, 'analyze_playlist', slow_analyze)
    # Hold the first batch preview until the UI cancels it. A fixed sleep lets
    # faster runners finish the job before the real pointer reaches Cancel.
    import batch_review
    original_review = batch_review.prepare_review
    first_review = [True]
    def cancellable_review(*args, **kwargs):
        if first_review[0]:
            first_review[0] = False
            cancel_check = kwargs.get('cancel_check') or args[6]
            deadline = time.monotonic() + 30
            while not cancel_check() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert cancel_check(), 'Browser did not cancel its first batch preview'
        return original_review(*args, **kwargs)
    monkeypatch.setattr(batch_review, 'prepare_review', cancellable_review)

    import native_dialog
    incoming = tmp_path / 'incoming'; incoming.mkdir()
    (incoming / 'Imported demo.sfc').write_bytes(b'game import fixture')
    (incoming / 'Updated demo.sfc').write_bytes(b'new version fixture')
    browse = tmp_path / 'browse'
    (browse / 'Subfolder').mkdir(parents=True)
    (browse / 'Subfolder' / 'inner.txt').write_bytes(b'inner')
    home = str(Path.home())

    def fake_pick(kind='directory', initial=''):
        if kind == 'files':
            return [str(incoming / 'Imported demo.sfc')]
        if kind == 'rom':
            return str(incoming / 'Updated demo.sfc')
        if initial == home:
            return str(browse)
        return initial if initial and Path(initial).is_dir() else str(tmp_path / '游戏库/rom-samples/RetroArch/Roms')

    monkeypatch.setattr(native_dialog, 'pick', fake_pick)
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
                    '--disable-background-networking', '--disable-renderer-backgrounding',
                    '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', 'about:blank',
                ], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 45
                    active_port = profile / 'DevToolsActivePort'
                    while True:
                        assert chrome.poll() is None, f'Chrome exited; see {artifacts / "chrome.log"}'
                        assert time.monotonic() < deadline, f'Chrome startup timed out; see {artifacts / "chrome.log"}'
                        if active_port.is_file():
                            try:
                                port = int(active_port.read_text(encoding='utf-8').splitlines()[0])
                                break
                            except PermissionError:
                                # Windows can keep this file locked while Chrome writes it.
                                time.sleep(0.05)
                                continue
                        time.sleep(0.05)
                    response = requests.get(f'http://127.0.0.1:{port}/json/list', timeout=15)
                    response.raise_for_status()
                    targets = response.json()
                    websocket = next(target['webSocketDebuggerUrl'] for target in targets if target['type'] == 'page')
                    result = subprocess.run([
                        'node', str(ROOT / 'tests/browser_smoke.cjs'), websocket,
                        f'http://127.0.0.1:{httpd.server_address[1]}', str(playlists.parent),
                        str(viewport[0]), str(viewport[1]), str(artifacts), str(browse),
                    ], capture_output=True, text=True, encoding='utf-8', timeout=180)
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
