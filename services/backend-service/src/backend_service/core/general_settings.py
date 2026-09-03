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


#: The keys ``PUT /config/general`` accepts. Anything else in a request body is
#: dropped silently, so a key that is not in here cannot be written at all.
#:
#: It lives here rather than in the route because a second caller has to ask
#: the same question: an addon that is installed by flipping a setting
#: (``component_catalog.py``) is only offered when its field can actually be
#: written. Without the check the WebUI would show a switch that springs back.
WRITABLE_KEYS: frozenset[str] = frozenset(
    {
        "minabox_device_id",
        "log_level",
        "mqtt_broker",
        "mqtt_port",
        "disable_gpio",
        "sleep_timer_minutes",
        "bedtime_fade_enabled",
        "bedtime_fade_duration_minutes",
        "bedtime_fade_interval_seconds",
        "bedtime_fade_step_percent",
        "usage_times_enabled",
        "daily_limit_enabled",
        "daily_limit_minutes",
        "stop_playback_on_tag_remove",
        "resume_on_tag_rescan",
        "playback_end_behavior",
        "playback_loop_guard_minutes",
        "playlist_shuffle",
        "allowed_usage_times",
        "auto_update_check_enabled",
        "update_channel",
        "max_upload_size_mb",
        "media_import_allowed_domains",
        "online_metadata_lookup_enabled",
        "analytics_retention_weeks",
        # Spoken announcements (core/announcements.py).
        "announcements_enabled",
        "announce_card_name",
        "announce_unknown_card",
        "announce_usage_limit",
        "announce_mute",
        "announce_language",
        "announce_volume_percent",
        "announce_duck_percent",
        "announce_limit_warning_minutes",
        # Setup wizard (docs/services/webui/Setup-Wizard.md). Without these
        # keys the filter below drops them silently, and the wizard would come
        # back on every visit.
        "setup_completed",
        "setup_version",
    }
)
