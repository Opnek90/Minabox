"""The volume HUD: the screen this box is used for most.

``max_volume`` is a hard clamp, not a scale. The audio service pulls the
running volume into ``[min_volume, max_volume]``, so on a box configured to 40
the status message reports ``volume: 40`` when the knob is at its stop.
Everything here works in position within the allowed range - the same
arithmetic the WebUI slider already uses - never the raw number.

The level is Knuffel singing, with a rising run of notes coming out of his
mouth: one note per level, each larger than the last, so the count, the size
and the climb all say the same thing. There are **five** levels, fixed,
whatever the knob's own step happens to be. Nobody sets the volume to a
precise one of a dozen-odd detents, and a playful "this loud" reads better to
a child who cannot count yet than an exact block would. The quietest level
still shows one note: the floor is a setting, not silence - ``min_volume``
exists so the box is never quiet enough to lose - and no note at all would say
the opposite.

At the top Knuffel belts it out, eyes screwed shut. That pose is the ceiling
cue: it replaces the full row of blocks that used to mean "this is as far as
the knob goes".

No text and no percentage. A picture of Knuffel singing needs neither, and a
number here would be a third figure for one quantity - the WebUI already
prints the raw volume beside a slider that spans the range, and any two of the
three disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import fonts, knuffel
from .primitives import HEIGHT, WIDTH, draw_text_centered, new_frame

# How many singing levels the range is quantised into, floor included.
LEVELS = 5

LABEL_MUTED = "Stumm"

# Knuffel on the left; the notes climb away to his upper right, clear of his
# body so they are not swallowed by it.
_KNUFFEL_SIZE = 44
_KNUFFEL_XY = (2, 9)
_NOTE_X0, _NOTE_Y0 = 50, 41
_NOTE_DX, _NOTE_DY = 15, 7


@dataclass(frozen=True)
class VolumeView:
    """Everything the HUD needs, already resolved from ``audio/status``."""

    volume: int
    min_volume: int = 0
    max_volume: int = 100
    muted: bool = False

    @property
    def span(self) -> int:
        """Size of the allowed range, never zero."""
        return max(1, self.max_volume - self.min_volume)

    @property
    def clamped(self) -> int:
        """The reported volume pulled into the allowed range.

        A retained status message from before a config change can sit outside
        it, and a HUD is not the place to argue about that.
        """
        return min(max(self.volume, self.min_volume), self.max_volume)

    @property
    def fraction(self) -> float:
        return (self.clamped - self.min_volume) / self.span

    @property
    def percent(self) -> int:
        return round(self.fraction * 100)

    @property
    def at_max(self) -> bool:
        return self.clamped >= self.max_volume

    @property
    def at_min(self) -> bool:
        return self.clamped <= self.min_volume

    @property
    def level(self) -> int:
        """Which singing level, 1 at the floor and never 0.

        The knob's own resolution does not reach the panel: two boxes, one
        configured 0-100 at step 1 and one 20-40 at step 5, both show the
        same five levels at the same fractions of their range.
        """
        return 1 + round(self.fraction * (LEVELS - 1))


def render(view: VolumeView) -> Any:
    """Return the frame for *view* as a mode-'1' image."""
    if view.muted:
        return _render_muted()
    return _render_singing(view)


def _render_singing(view: VolumeView) -> Any:
    img, draw = new_frame()

    mood = knuffel.BELTING if view.at_max else knuffel.SINGING
    knuffel.draw(draw, *_KNUFFEL_XY, _KNUFFEL_SIZE, mood)
    _notes(draw, view.level)
    return img


def _notes(draw: Any, count: int) -> None:
    """*count* notes climbing to the right from Knuffel, each bigger than the
    last.

    The number of them is the reading, so the run is not padded out to a fixed
    length with faint ones. Level 1 is a single small note beside him; level 5
    reaches the top right corner.
    """
    for k in range(count):
        cx = _NOTE_X0 + k * _NOTE_DX
        cy = _NOTE_Y0 - k * _NOTE_DY
        r = 2 + k
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=1)
        if k:
            # A stem off the top right, the way a note is drawn. The first one
            # is too small to carry one without turning into a smudge.
            draw.line(
                [(cx + r - 1, cy - 1), (cx + r - 1, cy - r - 4)], fill=1, width=2
            )


def _render_muted() -> Any:
    """Mute gets the same stage as the volume - it is the same interaction.

    Knuffel with his lips pressed shut rather than a crossed-out speaker: the
    box has one character, and a face that is plainly not making a sound beats
    a glyph a child has to learn. "Stumm" stays underneath for whoever can read.
    """
    img, draw = new_frame()
    size = 40
    knuffel.draw(draw, (WIDTH - size) // 2, 2, size, knuffel.HUSHED)
    draw_text_centered(draw, LABEL_MUTED, fonts.get(fonts.BOLD, 16), HEIGHT - 4)
    return img
