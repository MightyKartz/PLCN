import os
import sys
import json
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "src"))
from server import job_manager


def _run_mock_batch_job(job_id, batch_dir):
    try:
        import glob

        playlist_files = sorted(glob.glob(str(batch_dir / "*.lpl")))
        total_files = len(playlist_files)

        if total_files == 0:
            job_manager.fail_job(job_id, "No .lpl files found")
            return

        job_manager.update_job(job_id, 0, total_files, f"Found {total_files} playlists.")

        for i, playlist_path in enumerate(playlist_files):
            filename = os.path.basename(playlist_path)
            job_manager.update_job(job_id, i, total_files, f"Processing {filename}...")

            # Preserve the original test's mocked processing without sleeping.
            os.path.splitext(filename)[0]

        job_manager.complete_job(job_id, f"Processed {total_files} playlists.")
    except Exception as exc:
        job_manager.fail_job(job_id, str(exc))


def test_batch_processing(tmp_path):
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    # Create dummy playlist
    playlist_content = {
        "version": "1.0",
        "items": [
            {
                "path": "/roms/NES/Super Mario Bros.zip",
                "label": "Super Mario Bros. (USA)",
                "core_path": "DETECT",
                "core_name": "DETECT",
                "crc32": "DETECT",
                "db_name": "Nintendo - Nintendo Entertainment System.lpl"
            }
        ]
    }

    playlist_path = batch_dir / "Nintendo - Nintendo Entertainment System.lpl"
    playlist_path.write_text(json.dumps(playlist_content), encoding="utf-8")

    job_id = job_manager.create_job()

    thread = threading.Thread(target=_run_mock_batch_job, args=(job_id, batch_dir))
    thread.start()
    thread.join(timeout=2)

    job = job_manager.get_job(job_id)
    assert not thread.is_alive(), "Batch job thread did not finish promptly"
    assert job is not None
    assert job["status"] == "completed", job
    assert job["progress"] == 1
    assert job["total"] == 1
    assert job["message"] == "Processing Nintendo - Nintendo Entertainment System.lpl..."
    assert job["result"] == "Processed 1 playlists."
    assert job["error"] is None
