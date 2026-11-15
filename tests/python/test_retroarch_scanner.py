import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.getcwd(), "src"))

from retroarch_scanner import materialize_adb_file, push_adb_directory, scan_retroarch_target


def write_playlist(path, db_name="Nintendo - Super Nintendo Entertainment System.lpl"):
    path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/snes/Super Mario World (USA).sfc",
                        "label": "Super Mario World (USA)",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": db_name,
                    },
                    {
                        "path": "/roms/snes/Chrono Trigger (USA).sfc",
                        "label": "Chrono Trigger (USA)",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": db_name,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_scan_retroarch_root_lists_playlists(tmp_path):
    root = tmp_path / "RetroArch"
    playlists = root / "playlists"
    thumbnails = root / "thumbnails"
    playlists.mkdir(parents=True)
    thumbnails.mkdir()
    (root / "retroarch.cfg").write_text("menu_driver = \"ozone\"\n", encoding="utf-8")
    write_playlist(playlists / "Nintendo - Super Nintendo Entertainment System.lpl")

    scan = scan_retroarch_target(str(root))

    assert scan["connected"] is True
    assert scan["status"] == "ready"
    assert scan["root_path"] == str(root)
    assert scan["directories"]["playlists"] == str(playlists)
    assert scan["directories"]["thumbnails"] == str(thumbnails)
    assert scan["directories"]["thumbnails_exists"] is True
    assert scan["directories"]["config"] == str(root / "retroarch.cfg")
    assert scan["totals"] == {"playlists": 1, "items": 2}
    assert scan["playlists"][0]["system"] == "Nintendo - Super Nintendo Entertainment System"
    assert scan["playlists"][0]["item_count"] == 2
    assert scan["playlists"][0]["valid"] is True


def test_scan_playlist_directory_infers_root(tmp_path):
    root = tmp_path / "retroarch"
    playlists = root / "playlists"
    thumbnails = root / "thumbnails"
    playlists.mkdir(parents=True)
    thumbnails.mkdir()
    write_playlist(playlists / "SNES.lpl")

    scan = scan_retroarch_target(str(playlists))

    assert scan["connected"] is True
    assert scan["root_path"] == str(root)
    assert scan["directories"]["playlists"] == str(playlists)
    assert scan["directories"]["thumbnails"] == str(thumbnails)
    assert scan["playlists"][0]["name"] == "SNES.lpl"


def test_scan_keeps_malformed_playlist_as_invalid_entry(tmp_path):
    root = tmp_path / "RetroArch"
    playlists = root / "playlists"
    playlists.mkdir(parents=True)
    broken = playlists / "Broken.lpl"
    broken.write_text("{not valid json", encoding="utf-8")

    scan = scan_retroarch_target(str(root))

    assert scan["connected"] is True
    assert scan["status"] == "ready"
    assert scan["totals"] == {"playlists": 1, "items": 0}
    assert scan["playlists"][0]["valid"] is False
    assert scan["playlists"][0]["error"]


def test_auto_scan_detects_adb_retroarch_device():
    playlist_json = json.dumps(
        {
            "version": "1.5",
            "items": [
                {
                    "path": "/roms/snes/Super Mario World (USA).sfc",
                    "label": "Super Mario World (USA)",
                    "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
                }
            ],
        },
        ensure_ascii=False,
    )

    def fake_adb(args, timeout=10):
        if args == ["devices", "-l"]:
            return "List of devices attached\nRG476H01077813\tdevice usb:1-2 model:RG_476H device:ums9620\n"
        if args[:3] == ["-s", "RG476H01077813", "shell"]:
            script = args[3]
            if "/sdcard/RetroArch" in script and "playlists" in script and "find" not in script:
                return "/sdcard/RetroArch\n"
            if "find" in script and "/sdcard/RetroArch/playlists" in script:
                return "/sdcard/RetroArch/playlists/Nintendo - Super Nintendo Entertainment System.lpl\n"
            if "thumbnails" in script:
                return "/sdcard/RetroArch/thumbnails\n"
            if "retroarch.cfg" in script:
                return "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg\n"
            if "stat" in script:
                return "1780351333\n"
        if args[:4] == ["-s", "RG476H01077813", "exec-out", "cat"]:
            return playlist_json
        return ""

    scan = scan_retroarch_target(None, local_candidates=[], adb_runner=fake_adb)

    assert scan["connected"] is True
    assert scan["transport"] == "adb"
    assert scan["device"]["serial"] == "RG476H01077813"
    assert scan["root_path"] == "adb://RG476H01077813/sdcard/RetroArch"
    assert scan["directories"]["playlists"] == "adb://RG476H01077813/sdcard/RetroArch/playlists"
    assert scan["directories"]["thumbnails"] == "adb://RG476H01077813/sdcard/RetroArch/thumbnails"
    assert scan["directories"]["thumbnails_exists"] is True
    assert scan["totals"] == {"playlists": 1, "items": 1}
    assert scan["playlists"][0]["path"].startswith("adb://RG476H01077813/")
    assert scan["playlists"][0]["system"] == "Nintendo - Super Nintendo Entertainment System"


def test_materialize_adb_file_writes_remote_playlist_to_cache(tmp_path):
    def fake_adb(args, timeout=10):
        if args[:4] == ["-s", "RG476H01077813", "exec-out", "cat"]:
            return '{"version":"1.5","items":[]}'
        return ""

    local_path = materialize_adb_file(
        "adb://RG476H01077813/sdcard/RetroArch/playlists/SNES.lpl",
        cache_dir=str(tmp_path),
        adb_runner=fake_adb,
    )

    assert local_path.endswith("SNES.lpl")
    assert json.loads(open(local_path, encoding="utf-8").read()) == {"version": "1.5", "items": []}


def test_disconnected_adb_target_does_not_create_fake_playlist():
    calls = []
    def disconnected(args, timeout=10):
        calls.append(args)
        if args == ['devices', '-l']:
            return 'List of devices attached\n'
        return "adb: device 'offline' not found\n"
    scan = scan_retroarch_target('adb://offline/sdcard/RetroArch', local_candidates=[], adb_runner=disconnected)
    assert scan['connected'] is False
    assert scan['status'] == 'not_found'
    assert scan['playlists'] == []
    assert scan['totals']['items'] == 0
    assert all(call == ['devices', '-l'] for call in calls)


def test_adb_command_error_is_not_discovery_output(monkeypatch):
    from types import SimpleNamespace
    import retroarch_scanner
    monkeypatch.setattr(retroarch_scanner.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout='', stderr='adb: device not found'))
    assert retroarch_scanner._run_adb(['devices', '-l']) == ''


def test_root_probe_keeps_match_when_later_directories_are_absent(tmp_path, monkeypatch):
    import os
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import retroarch_scanner as scanner
    root = tmp_path / 'RetroArch with spaces'
    (root / 'playlists').mkdir(parents=True)
    monkeypatch.setattr(scanner, 'ADB_RETROARCH_ROOTS', [str(root), str(tmp_path / 'missing')])
    run = subprocess.run
    def run_probe(command, **kwargs):
        assert command[:4] == [scanner.adb_executable(), '-s', 'test-device', 'shell']
        # Exercise real shell exit status, not a canned successful ADB response.
        if os.name == 'nt':
            return SimpleNamespace(returncode=0, stdout=str(root) + '\n', stderr='')
        return run(['/bin/sh', '-c', command[4]], **kwargs)
    monkeypatch.setattr(scanner.subprocess, 'run', run_probe)
    found_root, found_playlists = scanner._find_adb_root('test-device')
    assert found_root == str(root)
    assert Path(found_playlists) == root / 'playlists'


def test_auto_scan_reports_connected_device_without_playlists():
    def no_library(args, timeout=10):
        if args == ['devices', '-l']:
            return 'List of devices attached\nserial\tdevice model:Handheld\n'
        return ''
    scan = scan_retroarch_target(local_candidates=[], adb_runner=no_library)
    assert scan['connected'] is True
    assert scan['status'] == 'no_playlists'
    assert scan['device']['serial'] == 'serial'
    assert scan['playlists'] == []
    assert '未找到 .lpl' in scan['message']


def test_scan_without_thumbnails_dir_reports_default_path(tmp_path):
    root = tmp_path / "RetroArch"
    playlists = root / "playlists"
    playlists.mkdir(parents=True)
    write_playlist(playlists / "Nintendo - Super Nintendo Entertainment System.lpl")

    scan = scan_retroarch_target(str(root))

    assert scan["directories"]["thumbnails"] == str(root / "thumbnails")
    assert scan["directories"]["thumbnails_exists"] is False
    assert not (root / "thumbnails").exists()


def test_adb_scan_defaults_thumbnails_to_library_root():
    playlist_json = json.dumps(
        {"version": "1.5", "items": [{"path": "/roms/snes/Game.sfc", "label": "Game",
                                      "db_name": "Nintendo - Super Nintendo Entertainment System.lpl"}]},
        ensure_ascii=False,
    )

    def fake_adb(args, timeout=10):
        if args == ["devices", "-l"]:
            return "List of devices attached\nRG476H01077813\tdevice usb:1-2 model:RG_476H device:ums9620\n"
        if args[:3] == ["-s", "RG476H01077813", "shell"]:
            script = args[3]
            if "/sdcard/RetroArch" in script and "playlists" in script and "find" not in script:
                return "/sdcard/RetroArch\n"
            if "find" in script and "/sdcard/RetroArch/playlists" in script:
                return "/sdcard/RetroArch/playlists/Nintendo - Super Nintendo Entertainment System.lpl\n"
            if "thumbnails" in script or "retroarch.cfg" in script:
                return ""
            if "stat" in script:
                return "1780351333\n"
        if args[:4] == ["-s", "RG476H01077813", "exec-out", "cat"]:
            return playlist_json
        return ""

    scan = scan_retroarch_target(None, local_candidates=[], adb_runner=fake_adb)

    assert scan["connected"] is True
    assert scan["directories"]["thumbnails"] == "adb://RG476H01077813/sdcard/RetroArch/thumbnails"
    assert scan["directories"]["thumbnails_exists"] is False


def test_missing_default_thumbnails_dir_reads_as_all_missing(tmp_path):
    from playlist_browser import artwork_statuses, open_artwork_reader

    missing = str(tmp_path / "thumbnails")
    resolver, lookups, error = open_artwork_reader(missing, "Nintendo - Super Nintendo Entertainment System")
    assert error == ""
    statuses = artwork_statuses("游戏", "/roms/snes/game.sfc", resolver, lookups, missing,
                                "Nintendo - Super Nintendo Entertainment System")
    assert statuses
    assert all(entry["status"] == "missing" for entry in statuses.values())


def test_missing_remote_artwork_dir_is_empty_inventory(tmp_path, monkeypatch):
    import subprocess
    import single_artwork as art

    def local_shell(serial, script):
        result = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr or "adb shell failed")
        return result.stdout.strip()

    monkeypatch.setattr(art, "adb_command", local_shell)
    missing = tmp_path / "thumbnails"
    inventory = art.remote_inventory("adb://serial" + str(missing), "GBA", "Named_Boxarts")
    assert inventory["filenames"] == set()
    file_leaf = tmp_path / "root" / "GBA"
    file_leaf.mkdir(parents=True)
    (file_leaf / "Named_Boxarts").write_text("x", encoding="utf-8")
    with pytest.raises(Exception):
        art.remote_inventory("adb://serial" + str(tmp_path / "root"), "GBA", "Named_Boxarts")


def test_thumbnail_download_creates_missing_artwork_directories(tmp_path):
    import io
    from types import SimpleNamespace
    from PIL import Image
    from thumbnail_downloader import ThumbnailDownloader

    image = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(image, format="PNG")
    downloader = ThumbnailDownloader(str(tmp_path / "thumbnails"))
    downloader.session = SimpleNamespace(
        get=lambda *args, **kwargs: SimpleNamespace(status_code=200, content=image.getvalue()))
    results = downloader.download_thumbnail("GBA", "Game (USA)", "游戏")
    assert all(result["status"] == "success" for result in results)
    for result in results:
        target = tmp_path / "thumbnails" / "GBA" / result["type"]
        assert target.is_dir()
        assert (target / os.path.basename(result["path"])).is_file()


def test_push_adb_directory_creates_remote_dirs(tmp_path):
    local = tmp_path / "images" / "GBA" / "Named_Boxarts"
    local.mkdir(parents=True)
    (local / "游戏.png").write_bytes(b"png")
    calls = []

    def fake_adb(args, timeout=10):
        calls.append(args)
        return ""

    push_adb_directory(str(tmp_path / "images"), "adb://serial/sdcard/thumbnails", adb_runner=fake_adb)

    shell = [call[3] for call in calls if call[:3] == ["-s", "serial", "shell"]]
    assert any(command.startswith("mkdir -p") and "thumbnails" in command for command in shell)
    pushes = [call for call in calls if call[:3] == ["-s", "serial", "push"]]
    assert pushes and pushes[0][-1] == "/sdcard/thumbnails"
