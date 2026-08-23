"""RFID-specific behaviour settings read from general_settings.json."""

from __future__ import annotations

from backend_service.core.general_settings import read_general_settings


def read_stop_playback_on_tag_remove() -> bool:
    """Return True if playback should stop when the RFID tag is removed."""
    return bool(read_general_settings().get("stop_playback_on_tag_remove", False))


def read_resume_on_tag_rescan() -> bool:
    """Return True if playback should resume from the last saved position
    when a tag is placed back on the reader.

    Defaults to True so the feature is opt-out rather than opt-in.
    """
    return bool(read_general_settings().get("resume_on_tag_rescan", True))


__all__ = [
    "read_stop_playback_on_tag_remove",
    "read_resume_on_tag_rescan",
]
