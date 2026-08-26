"""Tests for MediaDownloader: duration handling, thumbnails, max_filesize wiring.

yt_dlp.YoutubeDL is replaced with a fake that records the option dict it was
built with and returns a canned info dict, so these tests need no network
access and no real media file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3

from media_downloader_service import downloader as downloader_module
from media_downloader_service.downloader import DownloadError, MediaDownloader


class _FakeYoutubeDL:
    captured_opts: dict | None = None
    info: dict = {}
    write_mp3: bool = False

    def __init__(self, opts: dict) -> None:
        type(self).captured_opts = opts

    def __enter__(self) -> _FakeYoutubeDL:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = True) -> dict:
        if download and type(self).write_mp3:
            mp3_path = Path(type(self).captured_opts["outtmpl"].replace("%(ext)s", "mp3"))
            mp3_path.parent.mkdir(parents=True, exist_ok=True)
            mp3_path.write_bytes(b"fake mp3 data")
        return type(self).info


@pytest.fixture(autouse=True)
def fake_yt_dlp(monkeypatch):
    _FakeYoutubeDL.captured_opts = None
    _FakeYoutubeDL.info = {}
    _FakeYoutubeDL.write_mp3 = False
    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", _FakeYoutubeDL)
    yield


def test_get_video_info_handles_none_duration():
    """Regression: some extractors (livestreams) return duration: None, not absent."""
    _FakeYoutubeDL.info = {
        "title": "Live Now",
        "uploader": "Someone",
        "duration": None,
        "thumbnail": "",
        "id": "abc123",
    }
    result = MediaDownloader().get_video_info("https://example.org/live")
    assert result["duration_ms"] == 0


def test_download_video_handles_none_duration(tmp_path):
    _FakeYoutubeDL.info = {
        "id": "abc123",
        "title": "Live Now",
        "uploader": "Someone",
        "duration": None,
        "thumbnails": [],
        "thumbnail": "",
    }
    _FakeYoutubeDL.write_mp3 = True
    result = MediaDownloader().download_video("https://example.org/live", tmp_path)
    assert result["duration_ms"] == 0


def test_download_video_wires_max_filesize_into_ydl_opts(tmp_path):
    _FakeYoutubeDL.info = {
        "id": "x",
        "title": "T",
        "duration": 1,
        "thumbnails": [],
        "thumbnail": "",
    }
    _FakeYoutubeDL.write_mp3 = True
    MediaDownloader(max_filesize_mb=50).download_video("https://example.org/t", tmp_path)
    assert _FakeYoutubeDL.captured_opts["max_filesize"] == 50 * 1024 * 1024


def test_download_video_picks_last_thumbnail_as_best(tmp_path):
    """yt-dlp sorts info["thumbnails"] ascending by preference; the best is last."""
    _FakeYoutubeDL.info = {
        "id": "x",
        "title": "T",
        "duration": 10,
        "thumbnails": [{"url": "low.jpg"}, {"url": "high.jpg"}],
        "thumbnail": "fallback.jpg",
    }
    _FakeYoutubeDL.write_mp3 = True
    result = MediaDownloader().download_video("https://example.org/t", tmp_path)
    assert result["thumbnail"] == "high.jpg"


def test_download_video_falls_back_to_top_level_thumbnail(tmp_path):
    _FakeYoutubeDL.info = {
        "id": "x",
        "title": "T",
        "duration": 10,
        "thumbnails": [],
        "thumbnail": "fallback.jpg",
    }
    _FakeYoutubeDL.write_mp3 = True
    result = MediaDownloader().download_video("https://example.org/t", tmp_path)
    assert result["thumbnail"] == "fallback.jpg"


def test_download_video_raises_download_error_when_mp3_missing(tmp_path):
    _FakeYoutubeDL.info = {"id": "x", "title": "T", "duration": 1}
    _FakeYoutubeDL.write_mp3 = False  # extractor "succeeds" but no file appears
    with pytest.raises(DownloadError):
        MediaDownloader().download_video("https://example.org/t", tmp_path)


def test_embed_thumbnail_fallback_embeds_and_removes_sidecar(tmp_path):
    mp3_path = tmp_path / "audio.mp3"
    mp3_path.write_bytes(b"fake mp3 data")
    thumb_path = tmp_path / "audio.jpg"
    thumb_path.write_bytes(b"fake jpeg bytes")

    embedded = MediaDownloader()._embed_thumbnail_fallback(mp3_path, tmp_path)

    assert embedded is True
    assert not thumb_path.exists()
    assert ID3(mp3_path).getall("APIC")


def test_embed_thumbnail_fallback_no_sidecar_is_a_noop(tmp_path):
    mp3_path = tmp_path / "audio.mp3"
    mp3_path.write_bytes(b"fake mp3 data")
    assert MediaDownloader()._embed_thumbnail_fallback(mp3_path, tmp_path) is True
