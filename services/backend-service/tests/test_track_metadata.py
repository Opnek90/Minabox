"""Tag and cover extraction across the container formats we accept.

The real work is mutagen's; these tests pin the mapping this module puts on
top of it - which key wins per format, the cover size ceiling, and that a
missing file never raises.
"""

from __future__ import annotations

import types
from pathlib import Path

from backend_service.core import track_metadata


class _FakeAudio:
    def __init__(self, tags: object, length: float | None = None) -> None:
        self.tags = tags
        self.info = types.SimpleNamespace(length=length) if length else None


def _patch_mutagen(monkeypatch, *, easy: object, raw: object = None) -> None:
    def fake_file(_path: str, easy: bool = False):  # noqa: FBT001,FBT002
        return easy_obj if easy else raw_obj

    easy_obj, raw_obj = easy, raw
    monkeypatch.setattr(track_metadata, "MutagenFile", fake_file)


def test_read_tags_reads_normalised_easy_keys(monkeypatch):
    _patch_mutagen(
        monkeypatch,
        easy=_FakeAudio(
            {"artist": ["Rolf Zuckowski"], "album": ["Rabatz"], "title": ["Wie schoen"]},
            length=123.4,
        ),
    )
    tags = track_metadata.read_tags(Path("x.mp3"))
    assert tags.artist == "Rolf Zuckowski"
    assert tags.album == "Rabatz"
    assert tags.title == "Wie schoen"
    assert tags.duration_ms == 123400


def test_read_tags_falls_back_to_id3_frame_ids(monkeypatch):
    # mutagen could not open the file in easy mode - the raw ID3 frame names
    # have to be understood too.
    _patch_mutagen(
        monkeypatch,
        easy=None,
        raw=_FakeAudio({"TPE1": ["Die Maus"], "TALB": ["Lachgeschichten"]}, length=1.0),
    )
    tags = track_metadata.read_tags(Path("x.mp3"))
    assert tags.artist == "Die Maus"
    assert tags.album == "Lachgeschichten"


def test_read_tags_is_empty_when_nothing_can_be_read(monkeypatch):
    _patch_mutagen(monkeypatch, easy=None, raw=None)
    tags = track_metadata.read_tags(Path("x.mp3"))
    assert tags == track_metadata.TrackTags()


def test_read_tags_never_raises(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("corrupt header")

    monkeypatch.setattr(track_metadata, "MutagenFile", boom)
    assert track_metadata.read_tags(Path("x.flac")) == track_metadata.TrackTags()


class _FakeCoverTags:
    def __init__(self, frame: object) -> None:
        self._frame = frame

    def getall(self, key: str) -> list:
        return [self._frame] if key == "APIC" and self._frame is not None else []

    def keys(self):
        return []

    def __contains__(self, _key: str) -> bool:
        return False


def test_extract_embedded_cover_returns_bytes_and_extension(monkeypatch):
    frame = types.SimpleNamespace(data=b"\xff\xd8jpegdata", mime="image/jpeg")
    monkeypatch.setattr(
        track_metadata, "MutagenFile", lambda *_a, **_k: _FakeAudio(_FakeCoverTags(frame))
    )
    result = track_metadata.extract_embedded_cover(Path("x.mp3"))
    assert result == (b"\xff\xd8jpegdata", ".jpg")


def test_extract_embedded_cover_rejects_oversized_art(monkeypatch):
    big = b"x" * (track_metadata.COVER_MAX_BYTES + 1)
    frame = types.SimpleNamespace(data=big, mime="image/png")
    monkeypatch.setattr(
        track_metadata, "MutagenFile", lambda *_a, **_k: _FakeAudio(_FakeCoverTags(frame))
    )
    assert track_metadata.extract_embedded_cover(Path("x.mp3")) is None


def test_save_track_cover_writes_file_and_clears_other_extension(monkeypatch, tmp_path):
    covers = tmp_path / "covers"
    monkeypatch.setattr(track_metadata, "COVERS_DIR", covers)

    stale = covers / "track_7.png"
    covers.mkdir()
    stale.write_bytes(b"old")

    url = track_metadata.save_track_cover(7, b"newjpeg", ".jpg")
    assert url == "/static/covers/track_7.jpg"
    assert (covers / "track_7.jpg").read_bytes() == b"newjpeg"
    assert not stale.exists()


def test_save_track_cover_refuses_oversized_bytes(monkeypatch, tmp_path):
    monkeypatch.setattr(track_metadata, "COVERS_DIR", tmp_path / "covers")
    assert (
        track_metadata.save_track_cover(1, b"x" * (track_metadata.COVER_MAX_BYTES + 1), ".jpg")
        is None
    )
