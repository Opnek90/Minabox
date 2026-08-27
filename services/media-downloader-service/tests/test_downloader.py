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
            for hook in type(self).captured_opts.get("progress_hooks", []):
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 50,
                        "total_bytes": 100,
                        "speed": 512_000.0,
                        "eta": 7,
                    }
                )
            # postprocessor names are each PP's pp_key(), not its class name -
            # verified against the installed yt-dlp package. Using the wrong
            # ("FFmpegExtractAudio") name here once let this test pass while
            # the real code silently never reported "converting".
            for hook in type(self).captured_opts.get("postprocessor_hooks", []):
                hook({"status": "started", "postprocessor": "ExtractAudio"})
                hook({"status": "started", "postprocessor": "EmbedThumbnail"})
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


def test_postprocessor_hook_names_match_the_real_yt_dlp_classes():
    """downloader.py compares d["postprocessor"] against literal strings.
    yt-dlp reports each PP's pp_key(), not its class name - e.g.
    FFmpegExtractAudioPP reports "ExtractAudio". Pulling the real values from
    the installed package, rather than hardcoding them a second time, is the
    whole point: a hardcoded pair here once matched a hardcoded-but-wrong pair
    in downloader.py and both passed."""
    from yt_dlp.postprocessor import EmbedThumbnailPP, FFmpegExtractAudioPP, FFmpegMetadataPP

    assert downloader_module.postprocessor_stage_for(FFmpegExtractAudioPP.pp_key()) == (
        downloader_module.STAGE_CONVERTING
    )
    assert downloader_module.postprocessor_stage_for(EmbedThumbnailPP.pp_key()) == (
        downloader_module.STAGE_EMBEDDING_THUMBNAIL
    )
    assert downloader_module.postprocessor_stage_for(FFmpegMetadataPP.pp_key()) == (
        downloader_module.STAGE_EMBEDDING_METADATA
    )


def test_download_video_raises_download_error_when_mp3_missing(tmp_path):
    _FakeYoutubeDL.info = {"id": "x", "title": "T", "duration": 1}
    _FakeYoutubeDL.write_mp3 = False  # extractor "succeeds" but no file appears
    with pytest.raises(DownloadError):
        MediaDownloader().download_video("https://example.org/t", tmp_path)


def test_download_video_reports_stages_via_on_progress(tmp_path):
    """fetching_info before extraction starts, then downloading (with a real
    percent/speed/eta from yt-dlp's own hook data), then converting, then the
    two embedding stages - in that order, straight from yt-dlp's hooks
    rather than simulated."""
    _FakeYoutubeDL.info = {
        "id": "x",
        "title": "T",
        "duration": 1,
        "thumbnails": [],
        "thumbnail": "",
    }
    _FakeYoutubeDL.write_mp3 = True
    calls: list[downloader_module.ProgressUpdate] = []

    MediaDownloader().download_video(
        "https://example.org/t", tmp_path, on_progress=calls.append
    )

    assert calls == [
        downloader_module.ProgressUpdate("fetching_info", None, None, None),
        downloader_module.ProgressUpdate("downloading", 50.0, 512_000.0, 7),
        downloader_module.ProgressUpdate("converting", None, None, None),
        downloader_module.ProgressUpdate("embedding_thumbnail", None, None, None),
    ]


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


class _LoggerSpy:
    """Records logger.debug/.warning calls made through downloader_module.logger.

    Spies directly rather than using structlog.testing.capture_logs():
    main.py's module-level structlog.configure() sets a filtering bound
    logger at INFO globally (as soon as anything imports main, including
    other test modules in the same session), which silently drops the
    .debug() call before any capturing processor would ever see it - exactly
    the production behaviour these tests mean to confirm, but it defeats
    capture_logs().
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.debug_calls: list[tuple] = []
        self.warning_calls: list[tuple] = []
        monkeypatch.setattr(downloader_module.logger, "debug", self._record(self.debug_calls))
        monkeypatch.setattr(downloader_module.logger, "warning", self._record(self.warning_calls))

    @staticmethod
    def _record(sink: list[tuple]):
        return lambda *a, **kw: sink.append((a, kw))


def test_yt_dlp_logger_downgrades_the_known_sabr_warning(monkeypatch):
    """The "android client formats skipped" warning fires on every single
    YouTube import (see _YT_EXTRACTOR_ARGS) and is not actionable - it must
    not show up as an operator-facing warning."""
    spy = _LoggerSpy(monkeypatch)

    downloader_module._YtDlpLogger().warning(
        "[youtube] abc: Some android client https formats have been skipped "
        "as they are missing a URL. YouTube may have enabled the SABR-only "
        "streaming experiment for the current session. See "
        "https://github.com/yt-dlp/yt-dlp/issues/12482 for more details"
    )

    assert spy.warning_calls == []
    assert len(spy.debug_calls) == 1
    assert spy.debug_calls[0][0][0] == "yt_dlp_warning"


def test_yt_dlp_logger_keeps_other_warnings_at_warning_level(monkeypatch):
    spy = _LoggerSpy(monkeypatch)

    downloader_module._YtDlpLogger().warning("some unrelated, real problem")

    assert spy.debug_calls == []
    assert spy.warning_calls == [(("yt_dlp_warning",), {"text": "some unrelated, real problem"})]
