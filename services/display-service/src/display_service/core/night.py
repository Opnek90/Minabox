"""Is it night, as the panel understands the question.

Kept apart from everything else because the answer is a pure function of two
strings and a clock reading, and because midnight is the interesting part: a
window from 20:00 to 07:00 is the ordinary case and it wraps.
"""

from __future__ import annotations

from datetime import time


def _parse(value: str) -> time | None:
    """HH:MM as a time of day, or None if it is not one."""
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError):
        return None


def is_night(now: time, start: str, end: str) -> bool:
    """True while *now* falls inside the window from *start* to *end*.

    A window that wraps past midnight - which every useful one does - is the
    normal case, not the exception. Equal ends mean no night at all rather than
    a permanent one: somebody who wants the panel dim around the clock sets the
    day contrast, and reading it the other way would darken a box for a setting
    that looks like it does nothing.
    """
    first, last = _parse(start), _parse(end)
    if first is None or last is None or first == last:
        return False
    if first < last:
        return first <= now < last
    return now >= first or now < last
