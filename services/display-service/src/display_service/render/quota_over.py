"""The screen for "that is enough for today".

The daily limit is the third case with the same shape as an unknown or a
barred figure: the child puts something on the reader and nothing happens. That
is the shape a picture is actually good for.

Knuffel asleep, because he is done for today - the same face as at night, and
the word is what separates the two. On the idle screen there is never any text.
"""

from __future__ import annotations

from typing import Any

from . import fonts, knuffel
from .primitives import WIDTH, draw_text_centered, new_frame

TEXT = "Zeit um!"
GLYPH = 40
GLYPH_XY = ((WIDTH - GLYPH) // 2, 2)


def render() -> Any:
    """Return the frame as a mode-'1' image."""
    img, draw = new_frame()
    knuffel.draw(draw, *GLYPH_XY, GLYPH, knuffel.ASLEEP)
    draw_text_centered(draw, TEXT, fonts.get(fonts.BOLD, 15), 61)
    return img
