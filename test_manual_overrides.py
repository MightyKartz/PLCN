import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.getcwd(), "src"))

import plcn
import server
from manual_overrides import (
    build_override_entry,
    find_override,
    load_overrides,
    save_overrides,
    upsert_override,
)


def write_playlist(path, items):
    path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def ps_item(path="/roms/ps/Snatcher.bin", label="Wrong Existing", crc32="00000000|crc"):
    return {
        "path": path,
        "label": label,
        "core_path": "",
        "core_name": "",
        "crc32": crc32,
        "db_name": "Sony - PlayStation.lpl",
    }


def test_load_save_round_trip_and_default_missing(tmp_path):
    missing_path = tmp_path / "missing.json"
    entries = [
        {
            "system": "Sony - PlayStation",
            "rom_filename": "Snatcher.bin",
            "rom_path": "/roms/ps/Snatcher.bin",
            "crc32": "1234ABCD",
            "new_label": "掠夺者",
            "thumbnail_source": "Snatcher (Japan)",
        }
    ]

    assert load_overrides(missing_path) == []

    path = tmp_path / "overrides.json"
    save_overrides(path, entries)

    raw = path.read_text(encoding="utf-8")
    assert "掠夺者" in raw
    assert load_overrides(path) == entries


def test_server_apply_result_counts_verified_writeback_only():
    summary = {
        "total": {"success": 2, "failed": 0, "skipped": 0},
        "writeback": {
            "applied": [{"proposal_id": "ok"}],
            "failed": [{"proposal_id": "bad", "reason": "readback_mismatch"}],
            "skipped": [{"proposal_id": "old", "reason": "stale_proposal"}],
        },
    }

    result = server.build_apply_job_result(
        summary,
        changes=[{"proposal_id": "ok"}, {"proposal_id": "bad"}, {"proposal_id": "old"}],
    )

    assert result["applied_count"] == 1
    assert result["download_summary"] is summary


def test_server_config_merge_preserves_manual_overrides_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "manual_overrides_path": "/custom/manual-overrides.json",
                "single_system_name": "Sony - PlayStation",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "CONFIG_FILE", str(config_path))

    merged = server.merge_server_config({"single_system_name": "Nintendo - Game Boy Advance"})

    assert merged["manual_overrides_path"] == "/custom/manual-overrides.json"
    assert merged["single_system_name"] == "Nintendo - Game Boy Advance"


def test_upsert_override_deduplicates_by_system_crc_then_filename():
    entry = {
        "system": "Sony - PlayStation",
        "rom_filename": "Snatcher.bin",
        "rom_path": "/roms/ps/Snatcher.bin",
        "crc32": "1234abcd|crc",
        "new_label": "掠夺者",
        "thumbnail_source": "Snatcher (Japan)",
    }

    entries = upsert_override([], entry, now="2026-06-17T00:00:00Z")
    assert entries == [{**entry, "crc32": "1234ABCD", "updated_at": "2026-06-17T00:00:00Z"}]

    replacement = {**entry, "new_label": "诱拐者"}
    entries = upsert_override(entries, replacement, now="2026-06-17T00:01:00Z")
    assert len(entries) == 1
    assert entries[0]["new_label"] == "诱拐者"
    assert entries[0]["updated_at"] == "2026-06-17T00:01:00Z"

    detect_entry = {
        **entry,
        "crc32": "DETECT",
        "new_label": "掠夺者",
    }
    entries = upsert_override([], detect_entry, now="2026-06-17T00:00:00Z")
    entries = upsert_override(
        entries,
        {**detect_entry, "crc32": "", "new_label": "诱拐者"},
        now="2026-06-17T00:02:00Z",
    )
    assert len(entries) == 1
    assert entries[0]["crc32"] == ""
    assert entries[0]["new_label"] == "诱拐者"


def test_find_override_prefers_crc_then_filename():
    entries = [
        {
            "system": "sony - playstation",
            "rom_filename": "Snatcher.bin",
            "rom_path": "/other/Snatcher.bin",
            "crc32": "",
            "new_label": "filename match",
            "thumbnail_source": "Filename Source",
        },
        {
            "system": "SONY - PLAYSTATION",
            "rom_filename": "Other.bin",
            "rom_path": "/roms/ps/Other.bin",
            "crc32": "89ABCDEF",
            "new_label": "crc match",
            "thumbnail_source": "CRC Source",
        },
    ]

    item = ps_item(crc32="89abcdef|crc")

    assert find_override(entries, "Sony - PlayStation", item)["new_label"] == "crc match"
    assert find_override(entries, "sony - playstation", {**item, "crc32": ""})["new_label"] == "filename match"
    assert find_override(entries, "Sega - Saturn", item) is None


def test_analyze_playlist_applies_manual_override_before_matching(tmp_path):
    playlist_path = tmp_path / "Nintendo - Game Boy Advance.lpl"
    write_playlist(
        playlist_path,
        [
            {
                "path": "/roms/gba/Untranslated Homebrew.gba",
                "label": "Untranslated Homebrew",
                "core_path": "",
                "core_name": "",
                "crc32": "DETECT",
                "db_name": "Nintendo - Game Boy Advance.lpl",
            }
        ],
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


def test_analyze_playlist_applies_manual_override_before_fuzzy_matching(tmp_path):
    playlist_path = tmp_path / "Sony - PlayStation.lpl"
    write_playlist(playlist_path, [ps_item()])

    overrides_path = tmp_path / "manual-overrides.json"
    save_overrides(
        overrides_path,
        [
            {
                "system": "Sony - PlayStation",
                "rom_filename": "Snatcher.bin",
                "rom_path": "/roms/ps/Snatcher.bin",
                "crc32": "00000000",
                "new_label": "掠夺者",
                "thumbnail_source": "Snatcher (Japan)",
            }
        ],
    )

    changes = plcn.analyze_playlist(
        str(playlist_path),
        "Sony - PlayStation",
        "data/rom-name-cn",
        manual_overrides_path=str(overrides_path),
    )

    assert changes[0]["match_source"] == "manual_override"
    assert changes[0]["new_label"] == "掠夺者"
    assert changes[0]["thumbnail_source"] == "Snatcher (Japan)"
    assert changes[0]["needs_review"] is False
    assert changes[0]["match_score"] == 100


def test_manual_override_conflicting_with_exact_rom_source_is_review_only(tmp_path):
    playlist_path = tmp_path / "Sony - PlayStation.lpl"
    write_playlist(playlist_path, [ps_item(path="/roms/PS/Snatcher.bin")])

    probe_changes = plcn.analyze_playlist(
        str(playlist_path),
        "Sony - PlayStation",
        "data/rom-name-cn",
    )
    if not probe_changes or probe_changes[0].get("thumbnail_source") != "Snatcher (Japan)":
        pytest.skip("missing local source for Snatcher (Japan) in this checkout")

    overrides_path = tmp_path / "manual-overrides.json"
    save_overrides(
        overrides_path,
        [
            {
                "system": "Sony - PlayStation",
                "rom_filename": "Snatcher.bin",
                "rom_path": "/roms/PS/Snatcher.bin",
                "crc32": "00000000",
                "new_label": "掠夺者",
                "thumbnail_source": "Tiger & Bunny - On-Air Jack! (Japan)",
            }
        ],
    )

    changes = plcn.analyze_playlist(
        str(playlist_path),
        "Sony - PlayStation",
        "data/rom-name-cn",
        manual_overrides_path=str(overrides_path),
    )

    assert changes[0]["thumbnail_source"] == "Tiger & Bunny - On-Air Jack! (Japan)"
    assert changes[0]["needs_review"] is True or changes[0]["match_status"] == "review"
    assert "conflict" in changes[0]["match_reason"].lower()


def test_build_override_entry_from_payload():
    payload = {
        "system": "Sony - PlayStation",
        "change": {
            "path": "/roms/PS/Snatcher.bin",
            "original_item_label": "Wrong Existing",
            "crc32": "1234abcd|crc",
            "new_label": "掠夺者",
            "thumbnail_source": "Snatcher (Japan)",
        },
    }

    entry = build_override_entry(payload, now="2026-06-17T00:00:00Z")

    assert entry == {
        "system": "Sony - PlayStation",
        "rom_path": "/roms/PS/Snatcher.bin",
        "rom_filename": "Snatcher.bin",
        "crc32": "1234ABCD",
        "new_label": "掠夺者",
        "thumbnail_source": "Snatcher (Japan)",
        "updated_at": "2026-06-17T00:00:00Z",
    }
