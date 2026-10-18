"""The screen for a button press or card scan while remote-control lock is on.

Knuffel shakes his head (eyes and sealed mouth shifting left and right) beside
a padlock, so a child who cannot read still sees a friendly "not right now".
"""

from __future__ import annotations

from typing import Any

from . import fonts, knuffel, marks
from .primitives import draw_text, new_frame

TEXT = "Ferngesteuert"
GLYPH = 44
GLYPH_XY = (2, 10)
LOCK_SIZE = 24
LOCK_XY = (74, 10)


def render(phase: int = 0) -> Any:
    """Return the frame for *phase* as a mode-'1' image."""
    img, draw = new_frame()
    mood = knuffel.SHAKE_LEFT if phase % 2 == 0 else knuffel.SHAKE_RIGHT
    knuffel.draw(draw, *GLYPH_XY, GLYPH, mood)
    marks.locked(draw, *LOCK_XY, LOCK_SIZE)
    draw_text(draw, (48, 52), TEXT, fonts.get(fonts.REGULAR, 11))
    return img
