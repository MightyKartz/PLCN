import sys
from pathlib import Path

from requests.adapters import HTTPAdapter

sys.path.append(str(Path(__file__).resolve().parent / "src"))
from database import DatabaseManager
from thumbnail_downloader import ThumbnailDownloader
from server import job_manager


def test_database_keyword_search_returns_expected_translation(tmp_path):
    db = DatabaseManager(str(tmp_path / "test_opt.db"))

    try:
        cursor = db.get_connection().cursor()
        cursor.executemany(
            "INSERT INTO translations (english_name, chinese_name, system) VALUES (?, ?, ?)",
            [
                ("Super Mario World", "超级马里奥世界", "SNES"),
                ("Legend of Zelda", "塞尔达传说", "NES"),
            ],
        )
        db.get_connection().commit()

        results = db.search_by_keyword("Mario")

        assert results == [
            {
                "english_name": "Super Mario World",
                "chinese_name": "超级马里奥世界",
                "system": "SNES",
            }
        ]
    finally:
        db.close()


def test_network_retry_configures_http_and_https_adapters(tmp_path):
    downloader = ThumbnailDownloader(str(tmp_path / "thumbs"))

    for scheme in ("http://", "https://"):
        adapter = downloader.session.get_adapter(scheme)
        retries = adapter.max_retries

        assert isinstance(adapter, HTTPAdapter)
        assert retries.total == 3
        assert retries.backoff_factor == 1
        assert set(retries.status_forcelist) == {500, 502, 503, 504}


def test_job_system_tracks_lifecycle():
    job_id = job_manager.create_job()

    job = job_manager.get_job(job_id)
    assert job == {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "message": "",
        "result": None,
        "error": None,
    }

    job_manager.update_job(job_id, 50, 100, "Halfway there")
    job = job_manager.get_job(job_id)
    assert job["status"] == "running"
    assert job["progress"] == 50
    assert job["total"] == 100
    assert job["message"] == "Halfway there"
    assert job["result"] is None
    assert job["error"] is None

    job_manager.complete_job(job_id)
    job = job_manager.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["total"] == 100
    assert job["result"] is None
    assert job["error"] is None
