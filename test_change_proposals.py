import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.join(os.getcwd(), "src"))

import plcn


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
