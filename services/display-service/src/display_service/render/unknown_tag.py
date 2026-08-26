"""The screen for a figure the box does not know.

Knuffel again, puzzled, because a box with one character reads as one thing
rather than as a pile of screens. The face is for the child, who put something
on the reader and heard nothing; the words are for whoever can read them.

Held for a few seconds and then gone - it reports an event, it is not a state.
"""

from __future__ import annotations

from typing import Any

from . import fonts, knuffel
from .primitives import draw_text, new_frame

TEXT = "Wer bist du?"
GLYPH = 44
GLYPH_XY = (2, 10)


def render() -> Any:
    """Return the frame as a mode-'1' image."""
    img, draw = new_frame()
    knuffel.draw(draw, *GLYPH_XY, GLYPH, knuffel.PUZZLED)
    draw_text(draw, (50, 30), "?", fonts.get(fonts.BOLD, 30))
    draw_text(draw, (48, 52), TEXT, fonts.get(fonts.REGULAR, 11))
    return img
