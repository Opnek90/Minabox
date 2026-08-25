"""The volume HUD: the screen this box is used for most.

Two facts drive the whole layout, both established in the redesign document:

* ``max_volume`` is a hard clamp, not a scale. The audio service pulls the
  running volume into ``[min_volume, max_volume]``, so on a box configured to
  40 the status message reports ``volume: 40`` when the knob is at its stop.
  Printing that raw number would claim "40 %" at full volume, so everything
  here works in position within the allowed range - the same arithmetic the
  WebUI slider already uses.
* One turn of the knob is one ``volume_step``. Over 0-40 at step 5 that is
  exactly eight detents, so the bar is drawn as eight blocks and a click lights
  exactly one more. It is countable from two metres without reading anything,
  which matters for the part of the audience that cannot read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import fonts
from .primitives import (
    HEIGHT,
    WIDTH,
    bar,
    blocks,
    draw_text,
    draw_text_centered,
    draw_text_right,
    new_frame,
    speaker,
    text_width,
)

# Blocks stop being countable somewhere past a dozen and a half; below four
# they no longer read as a scale. Outside that window the same area is drawn
# as a continuous bar, so a box configured 0-100 at step 1 still works.
MIN_BLOCKS = 4
MAX_BLOCKS = 16

LABEL_MAX = "MAX"
LABEL_MIN = "leise"
LABEL_MUTED = "Stumm"

_NUMBER_SIZE = 34
_NUMBER_SIZE_THREE_DIGITS = 26  # "100" does not fit next to the glyph at 34 px


@dataclass(frozen=True)
class VolumeView:
    """Everything the HUD needs, already resolved from ``audio/status``."""

    volume: int
    min_volume: int = 0
    max_volume: int = 100
    step: int = 5
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
    def steps(self) -> int:
        """Number of knob detents across the allowed range, 0 if unknown."""
        if self.step <= 0:
            return 0
        return self.span // self.step

    @property
    def filled(self) -> int:
        if self.steps <= 0:
            return 0
        return min(self.steps, round((self.clamped - self.min_volume) / self.step))

    @property
    def use_blocks(self) -> bool:
        return MIN_BLOCKS <= self.steps <= MAX_BLOCKS

    @property
    def at_max(self) -> bool:
        return self.clamped >= self.max_volume

    @property
    def at_min(self) -> bool:
        return self.clamped <= self.min_volume

    @property
    def label(self) -> str:
        """The word next to the number, empty in the ordinary case.

        At the stop the display has to say so, or one keeps turning and
        wonders. At the bottom it has to say "quiet" rather than nothing, or it
        is indistinguishable from muted.
        """
        if self.at_max:
            return LABEL_MAX
        if self.at_min:
            return LABEL_MIN
        return ""


def render(view: VolumeView) -> Any:
    """Return the frame for *view* as a mode-'1' image."""
    if view.muted:
        return _render_muted()
    return _render_level(view)


def _render_level(view: VolumeView) -> Any:
    img, draw = new_frame()

    speaker(draw, 2, 5, 22)
    baseline = 30

    if view.at_max:
        # "100 %" and the word both want the same line and only one of them
        # carries information here: the number is redundant at the stop, the
        # word is the whole point. So the word takes the hero slot.
        draw_text(draw, (30, baseline), LABEL_MAX, fonts.get(fonts.BOLD, _NUMBER_SIZE))
    else:
        number = str(view.percent)
        size = _NUMBER_SIZE_THREE_DIGITS if len(number) > 2 else _NUMBER_SIZE
        number_font = fonts.get(fonts.BOLD, size)
        draw_text(draw, (30, baseline), number, number_font)

        unit_font = fonts.get(fonts.BOLD, 13)
        unit_x = 30 + text_width(draw, number, number_font) + 4
        draw_text(draw, (unit_x, baseline), "%", unit_font)

        if view.label:
            label_font = fonts.get(fonts.BOLD, 12)
            label_left = unit_x + text_width(draw, "%", unit_font) + 4
            if label_left + text_width(draw, view.label, label_font) <= WIDTH - 3:
                draw_text_right(draw, view.label, label_font, WIDTH - 3, baseline)

    box = (3, 38, WIDTH - 3, HEIGHT - 3)
    if view.use_blocks:
        blocks(draw, box, view.steps, view.filled)
    else:
        bar(draw, box, view.fraction)
    return img


def _render_muted() -> Any:
    """Mute gets the same stage as the volume - it is the same interaction."""
    img, draw = new_frame()
    glyph = 34
    speaker(draw, (WIDTH - glyph) // 2, 4, glyph, muted=True)
    draw_text_centered(draw, LABEL_MUTED, fonts.get(fonts.BOLD, 16), HEIGHT - 4)
    return img
