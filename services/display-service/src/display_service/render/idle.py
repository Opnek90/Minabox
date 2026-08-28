"""The screen for "nothing is playing": Knuffel, and nothing else.

No clock and no text. Two reasons beyond taste. The audience that stands in
front of an idle box cannot read, and a panel with a permanent element in
permanent pixels burns in - an OLED clock left in the same corner for a year
ghosts through every screen after it. A creature that wanders spreads the wear
by itself.

What this screen has to say is "the box is awake, put a figure on". A dark
panel says "broken", which is the thing to avoid.
"""

from __future__ import annotations

from typing import Any

from . import knuffel, marks
from .primitives import WIDTH, new_frame

# Drawn top right, most insistent first, and absent when there is nothing to
# say. Knuffel keeps out of the strip while it is occupied rather than walking
# under it - see IdleAnimation.set_reserved().
MARK_DRAWERS = {
    "error": marks.error,
    "sleep_timer": marks.sleep_timer,
    "no_internet": marks.no_internet,
}
MARK_ORDER = ("error", "no_internet", "sleep_timer")
MARK_TOP = 2


def strip_width(names: tuple[str, ...]) -> int:
    """Pixels the marks take on the right, including the gap before them."""
    if not names:
        return 0
    return len(names) * (marks.SIZE + marks.GAP) + marks.GAP


def render(pose: Any, marks_showing: tuple[str, ...] = ()) -> Any:
    """Return the frame for *pose* as a mode-'1' image."""
    img, draw = new_frame()
    knuffel.draw(draw, pose.x, pose.y, pose.size, pose.mood)
    x = WIDTH - marks.GAP - marks.SIZE
    for name in MARK_ORDER:
        if name in marks_showing:
            MARK_DRAWERS[name](draw, x, MARK_TOP, marks.SIZE)
            x -= marks.SIZE + marks.GAP
    return img
