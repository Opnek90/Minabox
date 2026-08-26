"""The screen for a figure the box knows but will not play.

Not the puzzled face: he recognises this one perfectly well, he is just not
allowed. A circle with a stroke through it is about as close to universal as
this panel gets, and the name underneath is for whoever can read it.

Laid out like the quota screen - glyph above, words below - so the word has the
whole width. Set beside the glyph at a fixed size it ran off the edge, which
PIL does not complain about.
"""

from __future__ import annotations

from typing import Any

from . import fonts, marks
from .primitives import WIDTH, draw_text_centered, fit_lines, new_frame

TEXT = "gesperrt"
GLYPH = 30
GLYPH_XY = ((WIDTH - GLYPH) // 2, 1)
TEXT_BASELINE = 47
NAME_BASELINE = 61
NAME_SIZES = (12, 11, 10, 9)


def render(name: str = "") -> Any:
    """Return the frame as a mode-'1' image, naming the figure if we know it."""
    img, draw = new_frame()
    marks.barred(draw, *GLYPH_XY, GLYPH)
    draw_text_centered(draw, TEXT, fonts.get(fonts.BOLD, 15), TEXT_BASELINE)
    if name:
        font, lines, _ = fit_lines(
            draw, name, WIDTH - 6, 1, NAME_SIZES, fonts.REGULAR, max_height=13
        )
        draw_text_centered(draw, lines[0], font, NAME_BASELINE)
    return img
