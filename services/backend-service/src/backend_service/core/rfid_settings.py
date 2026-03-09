"""RFID-specific behaviour settings read from general_settings.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _read_general_settings() -> dict:
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            return json.loads(gs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return {}


def read_stop_playback_on_tag_remove() -> bool:
    """Return True if playback should stop when the RFID tag is removed."""
    return bool(_read_general_settings().get("stop_playback_on_tag_remove", False))


def read_resume_on_tag_rescan() -> bool:
    """Return True if playback should resume from the last saved position
    when a tag is placed back on the reader.

    Defaults to True so the feature is opt-out rather than opt-in.
    """
    return bool(_read_general_settings().get("resume_on_tag_rescan", True))


__all__ = [
    "read_stop_playback_on_tag_remove",
    "read_resume_on_tag_rescan",
]
