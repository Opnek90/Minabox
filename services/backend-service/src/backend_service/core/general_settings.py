"""The single reader for ``/data/general_settings.json``.

Six modules used to carry their own copy of this: the playback, RFID, sleep and
usage settings, the temperature logger and the update check. Every one of them
opened and parsed the file again, and the RFID path does that several times per
card scan - on an SD card, for a file that changes maybe twice a month.

The contract stays exactly what it was: a value is read fresh, so a change in
the WebUI takes effect without a restart. The cache is keyed on what the file
system reports about the file, so a write - always an atomic replace, which
produces a new inode - is picked up on the very next read.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_cache_key: tuple[int, int, int] | None = None
_cache_value: dict[str, Any] = {}


def general_settings_path() -> Path:
    """Where the user settings live. Read from the environment on every call."""
    return Path(os.environ.get("DATA_PATH", "/data")) / "general_settings.json"


def _fingerprint(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_ino, stat.st_size, stat.st_mtime_ns)


def read_general_settings() -> dict[str, Any]:
    """Current user settings, or an empty dict when there are none.

    Never raises: a missing or damaged file means "no overrides", and every
    caller applies its own default on top.
    """
    global _cache_key, _cache_value

    path = general_settings_path()
    fingerprint = _fingerprint(path)
    if fingerprint is None:
        with _lock:
            _cache_key, _cache_value = None, {}
        return {}

    with _lock:
        if fingerprint == _cache_key:
            return _cache_value

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("general_settings_unreadable", path=str(path), error=str(exc))
        return {}

    value = loaded if isinstance(loaded, dict) else {}
    with _lock:
        _cache_key, _cache_value = fingerprint, value
    return value


def invalidate() -> None:
    """Forget the cached copy - for tests, and after writing the file."""
    global _cache_key, _cache_value
    with _lock:
        _cache_key, _cache_value = None, {}


__all__ = ["general_settings_path", "invalidate", "read_general_settings"]
