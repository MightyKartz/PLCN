import json
import os
import sys

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
