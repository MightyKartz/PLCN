import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from plcn import analyze_playlist


EXPECTED_AOF3 = "Art of Fighting 3 - The Path of the Warrior / Art of Fighting - Ryuuko no Ken Gaiden"


def test_fbneo_preview_uses_rom_path_stem_before_wrong_playlist_label(tmp_path):
    playlist_path = tmp_path / "FBNeo - Arcade Games.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "default_core_path": "DETECT",
                "default_core_name": "DETECT",
                "label_display_mode": 0,
                "right_thumbnail_mode": 0,
                "left_thumbnail_mode": 0,
                "items": [
                    {
                        "path": "/storage/roms/fbneo/aof3.zip",
                        "label": "Unknown Arcade Entry",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = analyze_playlist(str(playlist_path), "FBNeo - Arcade Games", "data/rom-name-cn")

    assert changes[0]["thumbnail_source"] == EXPECTED_AOF3
    assert changes[0]["new_label"] == "龙虎之拳 3 - 斗士之路"
    assert changes[0]["match_source"] == "libretro-dat-rom"


def test_fbneo_preview_uses_retroarch_crc_field_before_wrong_names(tmp_path):
    playlist_path = tmp_path / "FBNeo - Arcade Games.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/storage/roms/fbneo/not-aof3.zip",
                        "label": "Unknown Arcade Entry",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "0A015CAC|crc",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = analyze_playlist(str(playlist_path), "FBNeo - Arcade Games", "data/rom-name-cn")

    assert changes[0]["thumbnail_source"] == EXPECTED_AOF3
    assert changes[0]["new_label"] == "龙虎之拳 3 - 斗士之路"
    assert changes[0]["match_source"] == "libretro-dat-rom"
    assert changes[0]["match_diagnostics"]["dat_result"] == "matched"
    assert "playlist-crc" in changes[0]["match_diagnostics"]["candidate_sources"]


def test_fbneo_preview_reports_local_dat_miss_without_fake_dat_match(tmp_path):
    playlist_path = tmp_path / "FBNeo - Arcade Games.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/storage/roms/fbneo/notadat.zip",
                        "label": "Unlisted Arcade (World 123456)",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = analyze_playlist(str(playlist_path), "FBNeo - Arcade Games", "data/rom-name-cn")

    assert changes[0]["match_source"] == "arcade-fallback"
    assert changes[0]["match_diagnostics"]["dat_result"] == "not-found"
    assert changes[0]["match_diagnostics"]["fingerprint_status"] == "not-local"
    assert "本地 DAT 未命中" in changes[0]["match_reason"]


def test_fbneo_strikers_variants_do_not_reuse_plus_translation(tmp_path):
    playlist_path = tmp_path / "FBNeo - Arcade Games.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/storage/roms/fbneo/s1945.zip",
                        "label": "Strikers 1945 (World)",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    },
                    {
                        "path": "/storage/roms/fbneo/s1945ii.zip",
                        "label": "Strikers 1945 II",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    },
                    {
                        "path": "/storage/roms/fbneo/s1945p.zip",
                        "label": "Strikers 1945 Plus",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = analyze_playlist(str(playlist_path), "FBNeo - Arcade Games", "data/rom-name-cn")

    assert changes[0]["thumbnail_source"] == "Strikers 1945 (World)"
    assert changes[0]["new_label"] == "打击者1945"
    assert changes[1]["thumbnail_source"] == "Strikers 1945 II"
    assert changes[1]["new_label"] == "打击者1945二代"
    assert changes[2]["thumbnail_source"] == "Strikers 1945 Plus"
    assert changes[2]["new_label"] == "打击者 1945 加强版"
