import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import plcn
from manual_overrides import find_override, load_overrides, save_overrides


def test_load_and_save_overrides_round_trip_local_json(tmp_path):
    overrides_path = tmp_path / "manual-overrides.json"
    entries = [
        {
            "system": "Nintendo - Game Boy Advance",
            "rom_filename": "F-Zero - Maximum Velocity (USA, Europe).gba",
            "new_label": "F-Zero-极速传说",
            "thumbnail_source": "F-Zero - Maximum Velocity (USA, Europe)",
        }
    ]

    save_overrides(overrides_path, entries)

    assert json.loads(overrides_path.read_text(encoding="utf-8")) == entries
    assert load_overrides(overrides_path) == entries


def test_load_overrides_returns_empty_list_for_missing_file(tmp_path):
    assert load_overrides(tmp_path / "missing.json") == []


def test_find_override_matches_system_and_rom_filename():
    entries = [
        {
            "system": "Nintendo - Game Boy Advance",
            "rom_filename": "F-Zero - Maximum Velocity (USA, Europe).gba",
            "new_label": "F-Zero-极速传说",
            "thumbnail_source": "F-Zero - Maximum Velocity (USA, Europe)",
        },
        {
            "system": "Sony - PlayStation",
            "rom_filename": "F-Zero - Maximum Velocity (USA, Europe).gba",
            "new_label": "Wrong system",
            "thumbnail_source": "Wrong system",
        },
    ]
    item = {
        "path": "/storage/roms/gba/F-Zero - Maximum Velocity (USA, Europe).gba",
        "label": "F-Zero - Maximum Velocity (USA, Europe)",
        "crc32": "DETECT",
    }

    match = find_override(entries, "Nintendo - Game Boy Advance", item)

    assert match["new_label"] == "F-Zero-极速传说"
    assert match["thumbnail_source"] == "F-Zero - Maximum Velocity (USA, Europe)"


def test_find_override_matches_crc_even_when_filename_differs():
    entries = [
        {
            "system": "FBNeo - Arcade Games",
            "crc32": "0A015CAC",
            "new_label": "龙虎之拳 3 - 斗士之路",
            "thumbnail_source": "Art of Fighting 3 - The Path of the Warrior / Art of Fighting - Ryuuko no Ken Gaiden",
        }
    ]
    item = {
        "path": "/storage/roms/fbneo/not-aof3.zip",
        "label": "Unknown Arcade Entry",
        "crc32": "0a015cac|crc",
    }

    match = find_override(entries, "FBNeo - Arcade Games", item)

    assert match["new_label"] == "龙虎之拳 3 - 斗士之路"
    assert match["thumbnail_source"].startswith("Art of Fighting 3")


def test_analyze_playlist_applies_manual_override_before_matching(tmp_path):
    playlist_path = tmp_path / "Nintendo - Game Boy Advance.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/gba/Untranslated Homebrew.gba",
                        "label": "Untranslated Homebrew",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "DETECT",
                        "db_name": "Nintendo - Game Boy Advance.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    overrides_path = tmp_path / "manual-overrides.json"
    save_overrides(
        overrides_path,
        [
            {
                "system": "Nintendo - Game Boy Advance",
                "rom_filename": "Untranslated Homebrew.gba",
                "new_label": "未收录自制游戏",
                "thumbnail_source": "Untranslated Homebrew",
            }
        ],
    )

    changes = plcn.analyze_playlist(
        str(playlist_path),
        "Nintendo - Game Boy Advance",
        "data/rom-name-cn",
        manual_overrides_path=str(overrides_path),
    )

    assert changes[0]["new_label"] == "未收录自制游戏"
    assert changes[0]["thumbnail_source"] == "Untranslated Homebrew"
    assert changes[0]["match_source"] == "manual_override"
    assert changes[0]["needs_review"] is False
    assert changes[0]["match_diagnostics"]["evidence_source"] == "manual_override"
