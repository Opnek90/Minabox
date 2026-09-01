"""The volume HUD: the screen this box is used for most.

Two facts drive the whole layout, both established in the redesign document:

* ``max_volume`` is a hard clamp, not a scale. The audio service pulls the
  running volume into ``[min_volume, max_volume]``, so on a box configured to
  40 the status message reports ``volume: 40`` when the knob is at its stop.
  Printing that raw number would claim "40 %" at full volume, so everything
  here works in position within the allowed range - the same arithmetic the
  WebUI slider already uses.
* One turn of the knob is one ``volume_step``, so the bar is drawn as one block
  per setting the knob can be in and a click lights exactly one more. It is
  countable from two metres without reading anything, which matters for the
  part of the audience that cannot read.

There is deliberately no percentage on this screen. It would be a third number
for one quantity - the WebUI already prints the raw volume next to a slider
that spans the allowed range - and any two of them disagree. The blocks cannot
disagree with anything.

The count is settings, not steps: a knob that can sit in five places draws five
blocks and the quietest one lights **one**, never none. Parents set
``min_volume`` precisely so the box is never silent, and a screen showing an
empty row at the floor would say the opposite of what is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import fonts, knuffel
from .primitives import (
    HEIGHT,
    WIDTH,
    bar,
    blocks,
    draw_text_centered,
    draw_text_right,
    new_frame,
    speaker,
)

# Blocks stop being countable somewhere past a dozen and a half; below three
# they no longer read as a scale. Outside that window the same area is drawn
# as a continuous bar, so a box configured 0-100 at step 1 still works.
MIN_BLOCKS = 3
MAX_BLOCKS = 16

LABEL_MAX = "MAX"
LABEL_MIN = "Leise"
LABEL_MUTED = "Stumm"

# The bar fallback never reads as empty either, for the same reason the blocks
# do not: at the floor there is still sound.
MIN_BAR_FRACTION = 0.06


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
    def positions(self) -> int:
        """Number of places the knob can sit in - one more than the detents."""
        if self.steps <= 0:
            return 0
        return self.steps + 1

    @property
    def filled(self) -> int:
        """Blocks lit: 1 at the quietest setting, never 0.

        The floor is a setting, not silence. min_volume exists so the box is
        never quiet enough to confuse a child, and an empty row would claim the
        opposite.
        """
        if self.positions <= 0:
            return 0
        index = round((self.clamped - self.min_volume) / self.step)
        return min(self.positions, max(0, index) + 1)

    @property
    def use_blocks(self) -> bool:
        return MIN_BLOCKS <= self.positions <= MAX_BLOCKS

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

    speaker(draw, 3, 1, 28)
    if view.label:
        # Only the ends say anything worth saying: at the stop, that there is
        # no more; at the floor, that this is as quiet as it gets and not off.
        draw_text_right(draw, view.label, fonts.get(fonts.BOLD, 20), WIDTH - 4, 26)

    box = (3, 31, WIDTH - 3, HEIGHT - 3)
    if view.use_blocks:
        blocks(draw, box, view.positions, view.filled)
    else:
        bar(draw, box, max(MIN_BAR_FRACTION, view.fraction))
    return img


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
