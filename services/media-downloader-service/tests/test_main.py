"""Tests for the FastAPI routes: health check and the output_dir path guard.

Deliberately does not use `with TestClient(app):` - that would run the
lifespan startup, which tries to create /mnt/audio/tracks/downloads and has
no business touching the real filesystem in a test run. Plain instantiation
still routes requests, it just skips startup/shutdown events, which none of
these tests depend on.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from media_downloader_service import main as main_module
from media_downloader_service.downloader import ProgressUpdate
from media_downloader_service.main import app

client = TestClient(app)


def test_health_check_returns_healthy():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "media-downloader-service"


def test_download_rejects_output_dir_outside_audio_volume():
    response = client.post(
        "/download",
        json={"url": "https://example.org/track", "output_dir": "/etc/evil"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "DOWNLOAD_FAILED"


def test_download_accepts_output_dir_inside_audio_volume(monkeypatch, tmp_path):
    """The guard only rejects paths outside the shared volume - a legitimate
    per-track directory under it must still reach the downloader, and the
    request must complete through the asyncio.to_thread dispatch."""
    monkeypatch.setattr(main_module.config, "audio_base_dir", tmp_path)
    called: dict = {}

    def fake_download_video(self, url, output_dir, on_progress=None):
        called["output_dir"] = output_dir
        if on_progress:
            on_progress(ProgressUpdate("downloading", 50.0))
        return {
            "file_path": str(output_dir / "audio.mp3"),
            "title": "T",
            "artist": "A",
            "album": "Downloads",
            "duration_ms": 0,
            "video_id": "x",
            "thumbnail_embedded": True,
        }

    monkeypatch.setattr(main_module.MediaDownloader, "download_video", fake_download_video)

    target = tmp_path / "42"
    response = client.post(
        "/download",
        json={"url": "https://example.org/track", "output_dir": str(target)},
    )

    assert response.status_code == 201
    assert called["output_dir"] == target.resolve()
    assert response.json()["title"] == "T"


def test_download_progress_reachable_while_job_runs(monkeypatch, tmp_path):
    """job_id lets a concurrent caller poll /download/progress/{job_id};
    the entry is gone again once the request has completed."""
    monkeypatch.setattr(main_module.config, "audio_base_dir", tmp_path)
    seen_mid_flight: dict = {}

    def fake_download_video(self, url, output_dir, on_progress=None):
        if on_progress:
            on_progress(ProgressUpdate("converting"))
        seen_mid_flight["progress"] = dict(main_module._progress)
        return {
            "file_path": str(output_dir / "audio.mp3"),
            "title": "T",
            "artist": "A",
            "album": "Downloads",
            "duration_ms": 0,
            "video_id": "x",
            "thumbnail_embedded": True,
        }

    monkeypatch.setattr(main_module.MediaDownloader, "download_video", fake_download_video)

    response = client.post(
        "/download",
        json={"url": "https://example.org/track", "output_dir": str(tmp_path), "job_id": "42"},
    )

    assert response.status_code == 201
    assert seen_mid_flight["progress"] == {"42": ProgressUpdate("converting")}
    assert "42" not in main_module._progress  # cleaned up after the request finished


def test_download_progress_unknown_job_reports_done():
    response = client.get("/download/progress/does-not-exist")
    assert response.status_code == 200
    assert response.json() == {
        "stage": "done",
        "percent": None,
        "speed_bytes_per_sec": None,
        "eta_seconds": None,
    }
