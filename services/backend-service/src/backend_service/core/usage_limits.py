"""Usage-limit helpers: daily listening cap and allowed-time windows.

RFID-specific behaviour settings (stop on remove, resume on rescan) have
been extracted to :mod:`backend_service.core.rfid_settings`.
"""

from __future__ import annotations

from datetime import datetime
from datetime import time as dt_time
from typing import Any

from backend_service.core.general_settings import read_general_settings

DEFAULT_DAILY_LIMIT_MINUTES = 120


def read_allowed_usage_times() -> list[dict[str, Any]]:
    """Read allowed_usage_times from general_settings.json.

    Empty list = no restriction. When usage_times_enabled is False, returns [].
    """
    data = read_general_settings()
    if not bool(data.get("usage_times_enabled", False)):
        return []
    raw = data.get("allowed_usage_times")
    if not isinstance(raw, list) or not raw:
        return []
    try:
        return [
            {
                "weekday": int(x.get("weekday", 0)),
                "start": str(x.get("start", "07:00")),
                "end": str(x.get("end", "19:00")),
            }
            for x in raw
            if isinstance(x, dict) and 0 <= x.get("weekday", 0) <= 6
        ]
    except (TypeError, ValueError):
        return []


def is_within_allowed_usage_time(now: datetime, slots: list[dict[str, Any]]) -> bool:
    """Return True if now falls within any allowed slot. Empty slots = always allowed."""
    if not slots:
        return True
    try:
        t = now.time()
        wd = now.weekday()  # 0=Monday, 6=Sunday
        for s in slots:
            if s.get("weekday") != wd:
                continue
            start_s = s.get("start", "07:00")
            end_s = s.get("end", "19:00")
            if len(start_s) >= 5 and len(end_s) >= 5:
                start_parts = start_s.split(":")
                end_parts = end_s.split(":")
                start_t = dt_time(int(start_parts[0], 10), int(start_parts[1], 10))
                end_t = dt_time(int(end_parts[0], 10), int(end_parts[1], 10))
                if start_t <= end_t:
                    if start_t <= t <= end_t:
                        return True
                else:
                    if t >= start_t or t <= end_t:
                        return True
    except (ValueError, IndexError, TypeError):
        pass
    return False


def minutes_until_usage_window_ends(
    now: datetime, slots: list[dict[str, Any]]
) -> int | None:
    """Minutes left in the allowed slot *now* falls into, or None.

    None means "no end in sight from here": either there are no slots at all,
    or the box is currently outside every one of them - in which case what is
    left is nothing, not a countdown, and the caller has already refused the
    card.

    Used for the spoken warning before the listening time is over. A slot that
    wraps past midnight (22:00-06:00) is measured to its end on the following
    day, which is what the window means to the person who set it.
    """
    if not slots or not is_within_allowed_usage_time(now, slots):
        return None

    t = now.time()
    wd = now.weekday()
    remaining: list[int] = []
    minutes_now = t.hour * 60 + t.minute

    for slot in slots:
        if slot.get("weekday") != wd:
            continue
        try:
            start_h, start_m = (int(p, 10) for p in str(slot["start"]).split(":")[:2])
            end_h, end_m = (int(p, 10) for p in str(slot["end"]).split(":")[:2])
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes <= end_minutes:
            if start_minutes <= minutes_now <= end_minutes:
                remaining.append(end_minutes - minutes_now)
        elif minutes_now >= start_minutes:
            # Started today, ends tomorrow.
            remaining.append(24 * 60 - minutes_now + end_minutes)
        elif minutes_now <= end_minutes:
            remaining.append(end_minutes - minutes_now)

    # The longest of the overlapping slots wins: two windows that touch are one
    # stretch of listening time to the child in the room.
    return max(remaining) if remaining else None


def read_daily_limit_settings() -> tuple[bool, int]:
    """Read daily_limit_enabled and daily_limit_minutes from general_settings.json."""
    data = read_general_settings()
    try:
        return (
            bool(data.get("daily_limit_enabled", False)),
            max(1, min(1440, int(data.get("daily_limit_minutes", DEFAULT_DAILY_LIMIT_MINUTES)))),
        )
    except (TypeError, ValueError):
        return (False, DEFAULT_DAILY_LIMIT_MINUTES)


__all__ = [
    "read_allowed_usage_times",
    "is_within_allowed_usage_time",
    "read_daily_limit_settings",
]
