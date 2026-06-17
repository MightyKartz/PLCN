import json
import os
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.append(os.path.join(os.getcwd(), "src"))

import plcn


FIXTURE_DIR = Path(__file__).resolve().parent / "tests" / "fixtures" / "playlists"
ROM_NAME_CN_PATH = "data/rom-name-cn"
EXPECTED_AOF3 = "Art of Fighting 3 - The Path of the Warrior / Art of Fighting - Ryuuko no Ken Gaiden"
REQUIRED_PROPOSAL_FIELDS = {
    "new_label",
    "thumbnail_source",
    "match_source",
    "match_reason",
    "match_score",
    "needs_review",
}


def analyze_fixture(filename, system_name):
    return plcn.analyze_playlist(str(FIXTURE_DIR / filename), system_name, ROM_NAME_CN_PATH)


def test_build_change_proposal_adds_backend_match_metadata():
    item = {
        "path": "/roms/snes/Super Mario World (USA).sfc",
        "label": "Super Mario World (USA)",
        "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
    }

    proposal = plcn.build_change_proposal(
        index=0,
        item=item,
        display_label="Super Mario World (USA)",
        new_label="超级马里奥世界",
        thumbnail_source="Super Mario World",
        system_name="Nintendo - Super Nintendo Entertainment System",
        match_source="rom-name-cn",
        match_reason="中文库精确匹配",
    )

    assert proposal["proposal_id"]
    assert proposal["original_item_label"] == "Super Mario World (USA)"
    assert proposal["original_db_name"] == "Nintendo - Super Nintendo Entertainment System.lpl"
    assert proposal["match_score"] >= 90
    assert proposal["match_status"] == "matched"
    assert proposal["match_source"] == "rom-name-cn"
    assert proposal["match_reason"] == "中文库精确匹配"
    assert proposal["needs_review"] is False


@pytest.mark.parametrize(
    ("fixture_name", "system_name"),
    [
        ("gba_chinese_parent.lpl", "Nintendo - Game Boy Advance"),
        ("gba_polluted_label.lpl", "Nintendo - Game Boy Advance"),
        ("fbneo_zip_short_name.lpl", "FBNeo - Arcade Games"),
        ("ps1_bin_cue.lpl", "Sony - PlayStation"),
        ("unicode_nfc_nfd.lpl", "Nintendo - Game Boy Advance"),
        ("duplicate_entries.lpl", "Nintendo - Game Boy Advance"),
        ("missing_thumbnail_source.lpl", "Nintendo - Game Boy Advance"),
    ],
)
def test_playlist_fixture_proposals_include_match_explanation_fields(fixture_name, system_name):
    changes = analyze_fixture(fixture_name, system_name)

    assert changes
    for proposal in changes:
        assert REQUIRED_PROPOSAL_FIELDS <= set(proposal)
        assert isinstance(proposal["new_label"], str)
        assert "thumbnail_source" in proposal
        assert proposal["match_source"]
        assert proposal["match_reason"]
        assert isinstance(proposal["match_score"], int)
        assert isinstance(proposal["needs_review"], bool)


def test_gba_chinese_parent_fixture_uses_rom_filename_evidence():
    changes = analyze_fixture("gba_chinese_parent.lpl", "Nintendo - Game Boy Advance")
    by_rom = {Path(change["path"]).name: change for change in changes}

    assert by_rom["F-Zero - Maximum Velocity (USA, Europe).gba"]["new_label"] == "F-Zero-极速传说"
    assert (
        by_rom["F-Zero - Maximum Velocity (USA, Europe).gba"]["thumbnail_source"]
        == "F-Zero - Maximum Velocity (USA, Europe)"
    )
    assert by_rom["Castlevania - Aria of Sorrow (USA).gba"]["new_label"] == "恶魔城-晓月圆舞曲"
    assert (
        by_rom["Castlevania - Aria of Sorrow (USA).gba"]["thumbnail_source"]
        == "Castlevania - Aria of Sorrow (USA)"
    )
    assert all(change["match_source"] == "rom-name-cn" for change in changes)
    assert all(change["new_label"] != "gba中文游戏" for change in changes)


def test_generic_polluted_label_fixture_uses_rom_filename_evidence():
    change = analyze_fixture("gba_polluted_label.lpl", "Nintendo - Game Boy Advance")[0]

    assert change["original_item_label"] == "gba中文游戏"
    assert change["new_label"] == "F-Zero-极速传说"
    assert change["thumbnail_source"] == "F-Zero - Maximum Velocity (USA, Europe)"
    assert change["match_source"] == "rom-name-cn"
    assert change["match_score"] >= 90
    assert change["needs_review"] is False


def test_fbneo_zip_short_name_fixture_uses_dat_rom_evidence_before_label():
    change = analyze_fixture("fbneo_zip_short_name.lpl", "FBNeo - Arcade Games")[0]

    assert change["original_item_label"] == "Unknown Arcade Entry"
    assert change["new_label"] == "龙虎之拳 3 - 斗士之路"
    assert change["thumbnail_source"] == EXPECTED_AOF3
    assert change["match_source"] == "libretro-dat-rom"
    assert change["match_diagnostics"]["dat_result"] == "matched"
    assert any(
        source.startswith("rom")
        for source in change["match_diagnostics"]["candidate_sources"]
    )


def test_ps1_bin_cue_fixture_prefers_cue_entry_and_rom_translation():
    changes = analyze_fixture("ps1_bin_cue.lpl", "Sony - PlayStation")

    assert len(changes) == 1
    change = changes[0]
    assert change["path"].endswith(".cue")
    assert change["new_label"] == "最终幻想7 初版"
    assert change["thumbnail_source"] == "Final Fantasy VII (USA) (Disc 1)"
    assert change["match_source"] == "rom-name-cn"
    assert change["needs_review"] is False


def test_unicode_fixture_snapshot_matching_accepts_nfc_nfd_equivalents():
    fixture = json.loads((FIXTURE_DIR / "unicode_nfc_nfd.lpl").read_text(encoding="utf-8"))
    item = fixture["items"][0]
    nfc_item = {
        **item,
        "path": unicodedata.normalize("NFC", item["path"]),
        "label": unicodedata.normalize("NFC", item["label"]),
    }

    assert item["path"] != nfc_item["path"]
    assert item["label"] != nfc_item["label"]

    proposal = plcn.build_change_proposal(
        index=0,
        item=nfc_item,
        display_label=nfc_item["label"],
        new_label=nfc_item["label"],
        thumbnail_source=nfc_item["label"],
        system_name="Nintendo - Game Boy Advance",
        match_source="fixture",
        match_reason="Unicode normalization fixture",
    )

    assert plcn.proposal_matches_item(proposal, item) is True


def test_duplicate_entries_fixture_deduplicates_before_building_proposals():
    changes = analyze_fixture("duplicate_entries.lpl", "Nintendo - Game Boy Advance")

    assert len(changes) == 1
    assert changes[0]["path"].endswith("F-Zero - Maximum Velocity (USA, Europe).gba")
    assert changes[0]["new_label"] == "F-Zero-极速传说"


def test_missing_thumbnail_source_fixture_requires_review():
    change = analyze_fixture("missing_thumbnail_source.lpl", "Nintendo - Game Boy Advance")[0]

    assert change["new_label"] == "火星孤岛测试甲乙丙"
    assert change["thumbnail_source"] is None
    assert change["match_source"] == "filename"
    assert change["match_status"] == "review"
    assert change["needs_review"] is True


def test_build_change_proposal_marks_existing_complete_item_ready():
    item = {
        "path": "/roms/snes/Super Mario World (USA).sfc",
        "label": "超级马里奥世界",
        "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
    }

    proposal = plcn.build_change_proposal(
        index=0,
        item=item,
        display_label="Super Mario World (USA)",
        new_label="超级马里奥世界",
        thumbnail_source="Super Mario World",
        system_name="Nintendo - Super Nintendo Entertainment System",
        match_source="playlist",
        cover_exists=True,
        cover_path="/thumbs/Nintendo - Super Nintendo Entertainment System/Named_Boxarts/超级马里奥世界.png",
    )

    assert proposal["match_status"] == "ready"
    assert proposal["match_score"] == 100
    assert proposal["needs_review"] is False
    assert proposal["cover_exists"] is True
    cover_preview = urlparse(proposal["cover_preview_url"])
    assert cover_preview.path == "/api/thumbnail/preview"
    assert parse_qs(cover_preview.query)["path"][0] == proposal["cover_path"]


def test_build_change_proposal_marks_label_correct_cover_missing_as_download_only():
    item = {
        "path": "/roms/snes/Super Mario World (USA).sfc",
        "label": "超级马里奥世界",
        "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
    }

    proposal = plcn.build_change_proposal(
        index=0,
        item=item,
        display_label="Super Mario World (USA)",
        new_label="超级马里奥世界",
        thumbnail_source="Super Mario World",
        system_name="Nintendo - Super Nintendo Entertainment System",
        match_source="playlist",
        cover_exists=False,
    )

    assert proposal["match_status"] == "download"
    assert proposal["needs_review"] is False
    assert proposal["cover_exists"] is False


def test_build_change_proposal_marks_cover_existing_label_change_as_rename_only():
    item = {
        "path": "/roms/snes/Super Mario World (USA).sfc",
        "label": "Super Mario World",
        "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
    }

    proposal = plcn.build_change_proposal(
        index=0,
        item=item,
        display_label="Super Mario World",
        new_label="超级马里奥世界",
        thumbnail_source="Super Mario World",
        system_name="Nintendo - Super Nintendo Entertainment System",
        match_source="rom-name-cn",
        cover_exists=True,
    )

    assert proposal["match_status"] == "rename"
    assert proposal["needs_review"] is False
    assert proposal["cover_exists"] is True


def test_chinese_parent_directory_uses_filename_for_cover_source(tmp_path):
    playlist_path = tmp_path / "Sony - PlayStation.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/PS/掠夺者/Snatcher.bin",
                        "label": "掠夺者",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": "Sony - PlayStation.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        changes = plcn.analyze_playlist(
            str(playlist_path),
            "Sony - PlayStation",
            "data/rom-name-cn",
        )
    finally:
        playlist_path.unlink(missing_ok=True)

    assert changes[0]["new_label"] == "掠夺者"
    assert changes[0]["thumbnail_source"] == "Snatcher (Japan)"
    assert "Tiger & Bunny" not in changes[0]["thumbnail_source"]


def test_generic_chinese_parent_directory_does_not_override_rom_label(tmp_path):
    playlist_path = tmp_path / "Nintendo - Game Boy Advance.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/gba中文游戏/F-Zero - Maximum Velocity (USA, Europe).gba",
                        "label": "F-Zero - Maximum Velocity (USA, Europe)",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": "Nintendo - Game Boy Advance.lpl",
                    },
                    {
                        "path": "/roms/gba中文游戏/Castlevania - Aria of Sorrow (USA).gba",
                        "label": "Castlevania - Aria of Sorrow (USA)",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": "Nintendo - Game Boy Advance.lpl",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = plcn.analyze_playlist(
        str(playlist_path),
        "Nintendo - Game Boy Advance",
        "data/rom-name-cn",
    )

    assert [change["new_label"] for change in changes] == [
        "F-Zero-极速传说",
        "恶魔城-晓月圆舞曲",
    ]
    assert [change["thumbnail_source"] for change in changes] == [
        "F-Zero - Maximum Velocity (USA, Europe)",
        "Castlevania - Aria of Sorrow (USA)",
    ]
    assert all(change["match_source"] != "folder" for change in changes)


def test_generic_chinese_existing_label_is_repaired_from_rom_filename(tmp_path):
    playlist_path = tmp_path / "Nintendo - Game Boy Advance.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/gba中文游戏/F-Zero - Maximum Velocity (USA, Europe).gba",
                        "label": "gba中文游戏",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": "Nintendo - Game Boy Advance.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changes = plcn.analyze_playlist(
        str(playlist_path),
        "Nintendo - Game Boy Advance",
        "data/rom-name-cn",
    )

    assert changes[0]["new_label"] == "F-Zero-极速传说"
    assert changes[0]["thumbnail_source"] == "F-Zero - Maximum Velocity (USA, Europe)"
    assert changes[0]["match_source"] == "rom-name-cn"


def test_existing_boxart_lookup_indexes_local_named_boxarts(tmp_path):
    thumbnails_dir = tmp_path / "thumbnails"
    boxarts = thumbnails_dir / "Nintendo - Super Nintendo Entertainment System" / "Named_Boxarts"
    boxarts.mkdir(parents=True)
    (boxarts / "超级马里奥世界.png").write_bytes(b"")

    lookup = plcn.build_existing_boxart_lookup(
        str(thumbnails_dir),
        "Nintendo - Super Nintendo Entertainment System",
    )
    exists, path = plcn.find_existing_boxart(
        str(thumbnails_dir),
        "Nintendo - Super Nintendo Entertainment System",
        "超级马里奥世界",
        "Super Mario World",
        lookup=lookup,
    )

    assert exists is True
    assert path.endswith("超级马里奥世界.png")


def test_apply_changes_skips_stale_proposal_snapshot(tmp_path):
    playlist_path = tmp_path / "Nintendo - Super Nintendo Entertainment System.lpl"
    playlist_path.write_text(
        json.dumps(
            {
                "version": "1.5",
                "items": [
                    {
                        "path": "/roms/snes/Super Mario World (USA).sfc",
                        "label": "User Edited Name",
                        "core_path": "",
                        "core_name": "",
                        "crc32": "00000000|crc",
                        "db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    stale_change = {
        "index": 0,
        "path": "/roms/snes/Super Mario World (USA).sfc",
        "original_label": "Super Mario World (USA)",
        "original_item_label": "Super Mario World (USA)",
        "original_db_name": "Nintendo - Super Nintendo Entertainment System.lpl",
        "new_label": "超级马里奥世界",
        "thumbnail_source": "Super Mario World",
        "system": "Nintendo - Super Nintendo Entertainment System",
    }

    summary = plcn.apply_changes(
        str(playlist_path),
        [stale_change],
        str(tmp_path / "thumbnails"),
        backup=False,
        download_thumbnails=False,
    )

    saved = json.loads(playlist_path.read_text(encoding="utf-8"))
    assert saved["items"][0]["label"] == "User Edited Name"
    assert summary["total"] == {"success": 0, "failed": 0, "skipped": 0}
