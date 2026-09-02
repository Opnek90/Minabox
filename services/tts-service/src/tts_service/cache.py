"""The clip cache on disk.

A box says the same dozen phrases over and over - the names of the cards in the
box, "I do not know this card", "ten minutes left". Synthesising them again
every time would cost a second of Raspberry Pi CPU for a file that has not
changed, so every clip is kept under a name derived from what was said and in
which voice. Nothing here is state: deleting the whole directory costs the next
announcement a second, and nothing else.

The directory is a shared volume - the audio service reads the finished clip
from the same path - so the file name has to be safe to build from arbitrary
text. A hash is, and it doubles as the equality check: same voice, same text,
same file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

SUFFIX = ".wav"


def clip_name(voice: str, text: str) -> str:
    """The file name for *text* in *voice*.

    The voice is part of the key, not just the text: the same sentence in
    German and in English is two different clips, and so is the same sentence
    after somebody swapped the voice file.
    """
    digest = hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()
    return f"{digest[:32]}{SUFFIX}"


def clip_path(cache_dir: Path, voice: str, text: str) -> Path:
    """Where the clip for *text* in *voice* is, or would be."""
    return cache_dir / clip_name(voice, text)


def prune(cache_dir: Path, *, max_files: int, max_bytes: int) -> int:
    """Drop the least recently used clips until the cache fits again.

    Returns how many files were removed. Least recently *used*, not written:
    ``read_clip`` touches a hit, so the phrases a box actually says survive a
    one-off name that was spoken once and never again.

    Never raises. A cache that cannot be pruned is a full disk at worst, and
    refusing to speak because of it would be the wrong trade.
    """
    try:
        entries = [
            (p.stat().st_mtime, p.stat().st_size, p)
            for p in cache_dir.glob(f"*{SUFFIX}")
            if p.is_file()
        ]
    except OSError as exc:
        logger.warning("cache_prune_unreadable", error=str(exc))
        return 0

    entries.sort(key=lambda e: e[0])  # oldest touch first
    total_bytes = sum(size for _mtime, size, _p in entries)
    removed = 0

    for _mtime, size, path in entries:
        if len(entries) - removed <= max_files and total_bytes <= max_bytes:
            break
        try:
            path.unlink()
        except OSError as exc:
            logger.debug("cache_prune_failed", path=str(path), error=str(exc))
            continue
        total_bytes -= size
        removed += 1

    if removed:
        logger.info("cache_pruned", removed=removed, remaining_bytes=total_bytes)
    return removed


def touch(path: Path) -> None:
    """Mark a clip as used, so pruning takes the ones nobody asks for."""
    try:
        path.touch()
    except OSError as exc:
        logger.debug("cache_touch_failed", path=str(path), error=str(exc))
