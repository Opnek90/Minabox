"""Playback end-of-content settings read from general_settings.json.

What happens after the last track is a user setting and has to survive a card
scan. The session's own ``repeat_mode`` cannot carry it:
``SessionManager.create_session`` builds a fresh session for every card. So the
value lives in ``general_settings.json`` alongside ``stop_playback_on_tag_remove``
and - like everything there - is read fresh on each access, which is what makes
a change in the WebUI take effect without a restart.
"""

from __future__ import annotations

from typing import Literal

from backend_service.core.general_settings import read_general_settings

EndBehavior = Literal["stop", "repeat", "repeat_while_tag"]

VALID_END_BEHAVIORS: frozenset[str] = frozenset({"stop", "repeat", "repeat_while_tag"})

DEFAULT_END_BEHAVIOR: EndBehavior = "stop"
DEFAULT_LOOP_GUARD_MINUTES = 60
DEFAULT_PLAYLIST_SHUFFLE = True
MIN_LOOP_GUARD_MINUTES = 5
MAX_LOOP_GUARD_MINUTES = 1440


def clamp_end_behavior(value: object) -> EndBehavior:
    """Normalize a raw value to a known end behaviour (unknown -> ``stop``)."""
    if isinstance(value, str) and value in VALID_END_BEHAVIORS:
        return value  # type: ignore[return-value]
    return DEFAULT_END_BEHAVIOR


def clamp_loop_guard_minutes(value: object) -> int:
    """Normalize the loop guard: 0 disables it, everything else is clamped."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return DEFAULT_LOOP_GUARD_MINUTES
    try:
        minutes = int(value)
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
    return clamp_end_behavior(read_general_settings().get("playback_end_behavior"))


def read_playlist_shuffle() -> bool:
    """Whether a playlist starts in random order.

    Defaults to ``True``, which is what the box always did. An audio play in
    chapters wants the other setting, and `PlaylistTrack.position` has kept the
    intended order all along - it was simply never used for playback.
    """
    raw = read_general_settings().get("playlist_shuffle")
    if raw is None:
        return DEFAULT_PLAYLIST_SHUFFLE
    return bool(raw)


def read_loop_guard_minutes() -> int:
    """Minutes of continuous looping after which playback fades out.

    ``0`` disables the guard. It exists so a card left on the reader cannot keep
    the box playing for hours.
    """
    raw = read_general_settings().get("playback_loop_guard_minutes")
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
