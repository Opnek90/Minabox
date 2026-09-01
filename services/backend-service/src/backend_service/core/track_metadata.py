"""Read tags and embedded cover art from imported audio files.

The upload path used to read only ID3 ``TPE1``/``TALB`` inline in
``routes_tracks.py``. FLAC/OGG/Opus (Vorbis comments) and M4A/MP4 files were
left with empty ``artist``/``album`` even when the tags were right there, and
the cover extraction had no size ceiling. This module is the single place that
knows how each container stores that information.

Nothing in here ever raises: a file with no tags, a truncated download or an
exotic codec simply yields empty fields, and every caller has its own fallback
(the upload form, the online lookup, or just leaving the column ``NULL``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from mutagen import File as MutagenFile

logger = structlog.get_logger(__name__)

#: Embedded (or online) cover art larger than this is ignored. A cover is shown
#: at a few hundred pixels on the WebUI and the OLED - nothing legitimate comes
#: close, and the file sits on the SD card forever.
COVER_MAX_BYTES: int = 3 * 1024 * 1024

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"

#: Tag names per container, in the order mutagen exposes them. ``easy=True``
#: normalises MP3/FLAC/OGG/MP4 onto the lowercase Vorbis-style names; the
#: upper-case ID3 frame ids are the fallback for the rare file mutagen cannot
#: open in easy mode.
_TITLE_KEYS = ("title", "TIT2", "\xa9nam")
_ARTIST_KEYS = ("artist", "albumartist", "TPE1", "TPE2", "\xa9ART", "aART")
_ALBUM_KEYS = ("album", "TALB", "\xa9alb")


@dataclass
class TrackTags:
    """What could be read from a file's tags. Every field is optional."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration_ms: int | None = None


def _first_text(tags: Any, keys: tuple[str, ...]) -> str | None:
    """First non-empty value among *keys*, whatever shape the tag has."""
    if not tags:
        return None
    for key in keys:
        try:
            value = tags[key] if key in tags else None
        except (KeyError, TypeError, ValueError):
            value = None
        if value is None:
            continue
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def read_tags(path: Path) -> TrackTags:
    """Title, artist, album and duration from an audio file's tags."""
    try:
        easy = MutagenFile(str(path), easy=True)
    except Exception as exc:  # noqa: BLE001 - mutagen raises a zoo of errors
        logger.warning("track_metadata_read_failed", path=str(path), error=str(exc))
        return TrackTags()

    source = easy
    if source is None or getattr(source, "tags", None) is None:
        try:
            source = MutagenFile(str(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("track_metadata_read_failed", path=str(path), error=str(exc))
            source = None

    if source is None:
        return TrackTags()

    duration_ms: int | None = None
    info = getattr(source, "info", None)
    length = getattr(info, "length", None)
    if isinstance(length, (int, float)) and length > 0:
        duration_ms = int(length * 1000)

    tags = getattr(source, "tags", None)
    return TrackTags(
        title=_first_text(tags, _TITLE_KEYS),
        artist=_first_text(tags, _ARTIST_KEYS),
        album=_first_text(tags, _ALBUM_KEYS),
        duration_ms=duration_ms,
    )


def extract_embedded_cover(path: Path) -> tuple[bytes, str] | None:
    """Embedded front cover as ``(bytes, ".jpg" | ".png")``, or ``None``.

    Handles ID3 ``APIC`` frames, FLAC/Opus ``pictures`` and MP4 ``covr``.
    Anything larger than :data:`COVER_MAX_BYTES` is treated as absent.
    """
    try:
        audio = MutagenFile(str(path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_cover_extract_failed", path=str(path), error=str(exc))
        return None
    if not audio:
        return None

    data: bytes | None = None
    ext = ".jpg"
    try:
        tags = getattr(audio, "tags", None)
        if tags:
            apics: list[Any] = getattr(tags, "getall", lambda _: [])("APIC")
            if not apics:
                for key in getattr(tags, "keys", lambda: [])():
                    if key and str(key).startswith("APIC"):
                        apics = [tags[key]]
                        break
            if apics:
                frame = apics[0]
                data = getattr(frame, "data", None)
                if "png" in (getattr(frame, "mime", "") or "").lower():
                    ext = ".png"
            elif "covr" in tags:
                covr = tags["covr"]
                if covr:
                    pic = covr[0]
                    data = bytes(pic)
                    # mutagen.mp4.MP4Cover.imageformat: 14 = PNG, 13 = JPEG
                    if getattr(pic, "imageformat", None) == 14:
                        ext = ".png"
        if data is None and getattr(audio, "pictures", None):
            pic = audio.pictures[0]
            data = getattr(pic, "data", None)
            if "png" in (getattr(pic, "mime", "") or "").lower():
                ext = ".png"
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_cover_extract_failed", path=str(path), error=str(exc))
        return None

    if not data:
        return None
    if len(data) > COVER_MAX_BYTES:
        logger.info("track_cover_too_large", path=str(path), bytes=len(data))
        return None
    return bytes(data), ext


def save_track_cover(track_id: int, data: bytes, ext: str) -> str | None:
    """Write a cover for *track_id* and return its ``/static`` URL.

    Keeps the ``track_<id>`` naming the rest of the code already deletes on
    track removal, and clears the other extension so a JPEG does not linger
    next to a new PNG.
    """
    if not data or len(data) > COVER_MAX_BYTES:
        return None
    ext = ext if ext in (".jpg", ".png") else ".jpg"
    try:
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        (COVERS_DIR / f"track_{track_id}{'.png' if ext == '.jpg' else '.jpg'}").unlink(
            missing_ok=True
        )
        (COVERS_DIR / f"track_{track_id}{ext}").write_bytes(data)
    except OSError as exc:
        logger.warning("track_cover_save_failed", track_id=track_id, error=str(exc))
        return None
    logger.info("track_cover_saved", track_id=track_id, ext=ext, bytes=len(data))
    return f"/static/covers/track_{track_id}{ext}"


__all__ = [
    "COVER_MAX_BYTES",
    "COVERS_DIR",
    "STATIC_DIR",
    "TrackTags",
    "extract_embedded_cover",
    "read_tags",
    "save_track_cover",
]
