import json
import os
import re
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))

import plcn


SYSTEM = "Nintendo - Nintendo Entertainment System"
DB_NAME = f"{SYSTEM}.lpl"


class RecordingDownloader:
    calls = []

    def __init__(self, thumbnails_dir):
        self.thumbnails_dir = thumbnails_dir

    @classmethod
    def reset(cls):
        cls.calls = []

    @classmethod
    def empty_summary(cls, item_count=0):
        return {
            "item_count": item_count,
            "types": {
                type_name: {"success": 0, "failed": 0, "skipped": 0}
                for type_name in ("Named_Boxarts", "Named_Snaps", "Named_Titles")
            },
            "total": {"success": 0, "failed": 0, "skipped": 0},
            "details": [],
        }

    @classmethod
    def skipped_summary(cls, tasks, reason):
        summary = cls.empty_summary(len(tasks))
        for system, source, label in tasks:
            for type_name in summary["types"]:
                summary["types"][type_name]["skipped"] += 1
                summary["total"]["skipped"] += 1
                summary["details"].append(
                    {
                        "type": type_name,
                        "game": label,
                        "source": source,
                        "system": system,
                        "status": "skipped",
                        "message": reason,
                    }
                )
        return summary

    def download_batch(self, tasks, progress_callback=None):
        self.calls.append(list(tasks))
        return self.skipped_summary(tasks, "test downloader")


def write_playlist(path, items):
    path.write_text(
        json.dumps({"version": "1.5", "items": items}, ensure_ascii=False),
        encoding="utf-8",
    )


def read_playlist(path):
    return json.loads(path.read_text(encoding="utf-8"))


def playlist_item(path, label, db_name=DB_NAME):
    return {
        "path": path,
        "label": label,
        "core_path": "DETECT",
        "core_name": "DETECT",
        "crc32": "00000000|crc",
        "db_name": db_name,
    }


def change_for(index, item, new_label, thumbnail_source=None, proposal_id=None):
    return {
        "proposal_id": proposal_id
        or plcn.build_proposal_id(
            SYSTEM,
            index,
            item["path"],
            item["label"],
            item["db_name"],
        ),
        "index": index,
        "original_label": item["label"],
        "original_item_label": item["label"],
        "original_db_name": item["db_name"],
        "path": item["path"],
        "new_label": new_label,
        "thumbnail_source": thumbnail_source,
        "system": SYSTEM,
    }


def test_apply_changes_creates_timestamped_backup_file(tmp_path, monkeypatch):
    monkeypatch.setattr(plcn, "ThumbnailDownloader", RecordingDownloader)
    RecordingDownloader.reset()
    playlist_path = tmp_path / f"{SYSTEM}.lpl"
    original_item = playlist_item("/roms/nes/Contra (USA).zip", "Contra (USA)")
    write_playlist(playlist_path, [original_item])

    result = plcn.apply_changes(
        str(playlist_path),
        [],
        str(tmp_path / "thumbnails"),
        backup=True,
        download_thumbnails=False,
    )

    backups = list(tmp_path.glob(f"{playlist_path.name}.bak-*"))
    assert len(backups) == 1
    assert re.search(r"\.lpl\.bak-\d{8}-\d{6}$", backups[0].name)
    assert read_playlist(backups[0])["items"][0]["label"] == "Contra (USA)"
    assert result["apply"]["backup_path"] == str(backups[0])


def test_stale_proposal_is_skipped_without_enqueueing_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(plcn, "ThumbnailDownloader", RecordingDownloader)
    RecordingDownloader.reset()
    playlist_path = tmp_path / f"{SYSTEM}.lpl"
    original_item = playlist_item("/roms/nes/Contra (USA).zip", "Contra (USA)")
    current_item = {**original_item, "label": "魂斗罗"}
    write_playlist(playlist_path, [current_item])

    stale_change = change_for(
        0,
        original_item,
        new_label="魂斗罗-安全写入不应发生",
        thumbnail_source="Contra (USA)",
        proposal_id="stale-contra",
    )
    result = plcn.apply_changes(
        str(playlist_path),
        [stale_change],
        str(tmp_path / "thumbnails"),
        backup=False,
        download_thumbnails=True,
    )

    assert read_playlist(playlist_path)["items"][0]["label"] == "魂斗罗"
    assert RecordingDownloader.calls == []
    assert result["download_summary"]["item_count"] == 0
    assert result["apply"]["applied"] == []
    assert result["apply"]["skipped"] == [
        {
            "proposal_id": "stale-contra",
            "index": 0,
            "path": "/roms/nes/Contra (USA).zip",
            "reason": "stale_proposal",
            "expected": {"label": "Contra (USA)", "db_name": DB_NAME},
            "actual": {"label": "魂斗罗", "db_name": DB_NAME},
        }
    ]


def test_apply_result_includes_structured_apply_and_download_details(tmp_path, monkeypatch):
    monkeypatch.setattr(plcn, "ThumbnailDownloader", RecordingDownloader)
    RecordingDownloader.reset()
    playlist_path = tmp_path / f"{SYSTEM}.lpl"
    original_item = playlist_item("/roms/nes/Super Mario Bros. (USA).zip", "Super Mario Bros. (USA)")
    write_playlist(playlist_path, [original_item])

    change = change_for(
        0,
        original_item,
        new_label="超级马里奥兄弟",
        thumbnail_source="Super Mario Bros. (USA)",
        proposal_id="apply-mario",
    )
    result = plcn.apply_changes(
        str(playlist_path),
        [change],
        str(tmp_path / "thumbnails"),
        backup=False,
        download_thumbnails=False,
    )

    assert result["apply"]["requested_count"] == 1
    assert result["apply"]["applied"] == [
        {
            "proposal_id": "apply-mario",
            "index": 0,
            "path": "/roms/nes/Super Mario Bros. (USA).zip",
            "old_label": "Super Mario Bros. (USA)",
            "new_label": "超级马里奥兄弟",
            "thumbnail_source": "Super Mario Bros. (USA)",
        }
    ]
    assert result["apply"]["skipped"] == []
    assert result["download_summary"]["item_count"] == 1
    assert result["download_summary"]["total"]["skipped"] == 3


def test_read_back_verification_confirms_written_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(plcn, "ThumbnailDownloader", RecordingDownloader)
    RecordingDownloader.reset()
    playlist_path = tmp_path / f"{SYSTEM}.lpl"
    original_item = playlist_item("/roms/nes/Legend of Zelda, The (USA).zip", "Legend of Zelda, The (USA)")
    write_playlist(playlist_path, [original_item])

    change = change_for(
        0,
        original_item,
        new_label="塞尔达传说",
        thumbnail_source="Legend of Zelda, The (USA)",
        proposal_id="verify-zelda",
    )
    result = plcn.apply_changes(
        str(playlist_path),
        [change],
        str(tmp_path / "thumbnails"),
        backup=False,
        download_thumbnails=False,
    )

    assert read_playlist(playlist_path)["items"][0]["label"] == "塞尔达传说"
    assert result["apply"]["verification"] == [
        {
            "proposal_id": "verify-zelda",
            "index": 0,
            "path": "/roms/nes/Legend of Zelda, The (USA).zip",
            "expected_label": "塞尔达传说",
            "actual_label": "塞尔达传说",
            "status": "passed",
        }
    ]
