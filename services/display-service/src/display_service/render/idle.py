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

from . import knuffel
from .primitives import new_frame


def render(pose: Any) -> Any:
    """Return the frame for *pose* as a mode-'1' image."""
    img, draw = new_frame()
    knuffel.draw(draw, pose.x, pose.y, pose.size, pose.mood)
    return img
