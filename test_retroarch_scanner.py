import json
import os
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))

from retroarch_scanner import materialize_adb_file, scan_retroarch_target


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
