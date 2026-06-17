import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.join(os.getcwd(), "src"))

from server import annotate_download_summary_paths, split_plcn_apply_result


def test_annotate_download_summary_rewrites_temp_paths_to_adb_preview_urls():
    summary = {
        "details": [
            {
                "type": "Named_Boxarts",
                "game": "超级马里奥世界",
                "source": "Super Mario World",
                "system": "SNES",
                "status": "success",
                "path": "/tmp/plcn-adb-thumbnails-abc/SNES/Named_Boxarts/超级马里奥世界.png",
            },
            {
                "type": "Named_Snaps",
                "game": "超级马里奥世界",
                "source": "Super Mario World",
                "system": "SNES",
                "status": "success",
                "path": "/tmp/plcn-adb-thumbnails-abc/SNES/Named_Snaps/超级马里奥世界.png",
            },
        ]
    }

    annotate_download_summary_paths(
        summary,
        local_root="/tmp/plcn-adb-thumbnails-abc",
        final_root="adb://RG476H01077813/sdcard/RetroArch/thumbnails",
    )

    boxart = summary["details"][0]
    assert boxart["path"] == "adb://RG476H01077813/sdcard/RetroArch/thumbnails/SNES/Named_Boxarts/超级马里奥世界.png"
    assert boxart["cover_path"] == boxart["path"]
    preview = urlparse(boxart["cover_preview_url"])
    assert preview.path == "/api/thumbnail/preview"
    assert parse_qs(preview.query)["path"][0] == boxart["cover_path"]

    snap = summary["details"][1]
    assert snap["path"] == "adb://RG476H01077813/sdcard/RetroArch/thumbnails/SNES/Named_Snaps/超级马里奥世界.png"
    assert "cover_path" not in snap


def test_split_apply_result_keeps_download_summary_layer_for_ui():
    download_summary = {
        "item_count": 1,
        "types": {},
        "total": {"success": 1, "failed": 0, "skipped": 0},
        "details": [
            {
                "type": "Named_Boxarts",
                "game": "魂斗罗",
                "source": "Contra (USA)",
                "system": "NES",
                "status": "success",
                "path": "/tmp/plcn-adb-thumbnails-def/NES/Named_Boxarts/魂斗罗.png",
            }
        ],
    }
    apply_summary = {"applied": [{"proposal_id": "contra"}], "skipped": []}
    composite = {
        **download_summary,
        "download_summary": download_summary,
        "apply": apply_summary,
    }

    summary, apply = split_plcn_apply_result(composite)
    annotate_download_summary_paths(
        summary,
        local_root="/tmp/plcn-adb-thumbnails-def",
        final_root="adb://RG476H01077813/sdcard/RetroArch/thumbnails",
    )

    assert summary is download_summary
    assert apply is apply_summary
    assert composite["download_summary"]["details"][0]["cover_path"].startswith("adb://RG476H01077813/")
