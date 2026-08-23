"""Playback end-of-content settings read from general_settings.json.

Was am Ende des letzten Titels passiert, ist eine Nutzereinstellung und muss
einen Tag-Scan ueberleben. Der Session-eigene ``repeat_mode`` taugt dafuer
nicht: ``SessionManager.create_session`` legt fuer jede neue Karte eine frische
Session an. Der Wert lebt darum wie ``stop_playback_on_tag_remove`` in
``general_settings.json`` und wird -- ebenso wie dort -- bei jedem Zugriff frisch
gelesen, damit eine Aenderung in der WebUI ohne Neustart greift.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

EndBehavior = Literal["stop", "repeat", "repeat_while_tag"]

VALID_END_BEHAVIORS: frozenset[str] = frozenset({"stop", "repeat", "repeat_while_tag"})

DEFAULT_END_BEHAVIOR: EndBehavior = "stop"
DEFAULT_LOOP_GUARD_MINUTES = 60
DEFAULT_PLAYLIST_SHUFFLE = True
MIN_LOOP_GUARD_MINUTES = 5
MAX_LOOP_GUARD_MINUTES = 1440


def _read_general_settings() -> dict:
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            return json.loads(gs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return {}


def clamp_end_behavior(value: object) -> EndBehavior:
    """Normalize a raw value to a known end behaviour (unknown -> ``stop``)."""
    if isinstance(value, str) and value in VALID_END_BEHAVIORS:
        return value  # type: ignore[return-value]
    return DEFAULT_END_BEHAVIOR


def clamp_loop_guard_minutes(value: object) -> int:
    """Normalize the loop guard: 0 disables it, everything else is clamped."""
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_LOOP_GUARD_MINUTES
    if minutes <= 0:
        return 0
    return max(MIN_LOOP_GUARD_MINUTES, min(MAX_LOOP_GUARD_MINUTES, minutes))


def read_playback_end_behavior() -> EndBehavior:
    """What to do once the last track of a session has finished.

    ``stop``             -- end playback (previous behaviour, default)
    ``repeat``           -- start the session over
    ``repeat_while_tag`` -- start over only while the card is still on the reader
    """
    return clamp_end_behavior(_read_general_settings().get("playback_end_behavior"))


def read_playlist_shuffle() -> bool:
    """Whether a playlist starts in random order.

    Defaults to ``True``, which is what the box always did. An audio play in
    chapters wants the other setting, and `PlaylistTrack.position` has kept the
    intended order all along - it was simply never used for playback.
    """
    raw = _read_general_settings().get("playlist_shuffle")
    if raw is None:
        return DEFAULT_PLAYLIST_SHUFFLE
    return bool(raw)


def read_loop_guard_minutes() -> int:
    """Minutes of continuous looping after which playback fades out.

    ``0`` disables the guard. It exists so a card left on the reader cannot keep
    the box playing for hours.
    """
    raw = _read_general_settings().get("playback_loop_guard_minutes")
    if raw is None:
        return DEFAULT_LOOP_GUARD_MINUTES
    return clamp_loop_guard_minutes(raw)


__all__ = [
    "DEFAULT_END_BEHAVIOR",
    "DEFAULT_LOOP_GUARD_MINUTES",
    "DEFAULT_PLAYLIST_SHUFFLE",
    "EndBehavior",
    "MAX_LOOP_GUARD_MINUTES",
    "MIN_LOOP_GUARD_MINUTES",
    "VALID_END_BEHAVIORS",
    "clamp_end_behavior",
    "clamp_loop_guard_minutes",
    "read_loop_guard_minutes",
    "read_playback_end_behavior",
    "read_playlist_shuffle",
]
