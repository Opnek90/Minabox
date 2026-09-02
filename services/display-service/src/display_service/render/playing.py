"""The screen for "something is playing".

Two things share 128x64, one for each reader:

* the **title**, complete rather than cut off, for the parent who wants to know
  what is on;
* the **progress**, drawn as Knuffel walking a line to the end of the song -
  his position is the one thing on this panel a four-year-old can read, "this
  far to go", and near the end he turns and waves.

The remaining time in words used to sit along the bottom, for the parent. It is
gone: the panel is the child's, the parent has the phone, and dropping it buys
the room to draw Knuffel large enough to have a face. ``PlayingView.time_text``
stays - it is the obvious thing to put back if a parent-facing view ever wants
it - it is just not on the glass.

The title's font size follows its length instead of being fixed, which is what
makes "complete" possible at all: "Ein Lama in Yokohama" comes back on two
lines, "Das Lied von der Raupe Nimmersatt" at the same size and also whole.
Only a title too long for two lines even at the smallest size is trimmed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from . import fonts, knuffel
from .primitives import (
    SLEEP_ZS_PHASES,
    SLEEP_ZS_WIDTH,
    WIDTH,
    bar,
    block_height,
    draw_text,
    fit_lines,
    new_frame,
    sleep_zs,
    speaker,
)

# The title block is a fixed band, so the layout below it does not move when a
# shorter title picks a larger size. The band decides the size, not the other
# way round: two lines fit up to 10 px, a single line up to 20. It is a little
# shorter than it was, to give Knuffel headroom above the track he walks.
TITLE_SIZES = (20, 18, 16, 14, 13, 12, 11, 10, 9)
TITLE_TOP = 1
TITLE_MAX_LINES = 2
TITLE_BAND_HEIGHT = 22
TITLE_LINE_GAP = 2

# The progress bar is Knuffel walking to the end of the song. The track he
# walks is a full-width line low on the panel; behind him it is thickened to
# show the part that is done, and he stands at the join. His position is the
# thing a four-year-old reads - "this far to go" - so the line itself stays
# thin and quiet, and with the remaining time gone he gets most of the height.
WALK_LINE_Y = 56
WALK_KNUFFEL = 28
WALK_X0 = 3
WALK_X1 = WIDTH - 3

# The last stretch of the track: close enough to the end that Knuffel turns
# round and waves rather than trudging the last few pixels.
ARRIVING_MS = 15_000

# While playing, this screen replaces the widget grid - and with it the grid's
# permanent mute icon. Playback is exactly when that icon matters, so it comes
# along: a small glyph top right, and the title gives up the width for it.
MUTE_GLYPH = 13
MUTE_XY = (WIDTH - MUTE_GLYPH - 3, 2)

UNKNOWN_TIME = "spielt"

# Paused has its own layout. "Pause" as a word is for whoever can read, and the
# person most often standing in front of this panel cannot yet - so Knuffel
# falls asleep instead, which needs no reading at all. The title and the bar
# stay: what is on and how far in are still true while paused, and they are
# what the parent looks for.
PAUSED_TITLE_TOP = 1
PAUSED_TITLE_BAND_HEIGHT = 22
PAUSED_BAR_BOX = (3, 26, WIDTH - 3, 34)
PAUSED_SLEEPER_SIZE = 27
PAUSED_SLEEPER_TOP = 36
# Between him and the first Z. Closer and the Z grows out of his ear.
PAUSED_Z_GAP = 6
# The Zs hang off his upper right, the way a comic does it - but not above his
# head: lifted any further, the biggest one runs into the progress bar, and a Z
# growing out of a bar is just a broken bar.
PAUSED_Z_TOP = PAUSED_SLEEPER_TOP

# How long one Z stays before the next joins it. Two seconds is exactly two
# render ticks, so the rhythm is even rather than limping between one tick and
# two - and three phases make a six-second breath, which is about the pace of
# someone actually asleep.
#
# It also decides what this costs. Only the Z block changes between phases, so
# the diffed partial update is roughly four pages of 28 columns, every two
# seconds, on a bus the RFID reader shares. Halving the interval would double
# that for a livelier fidget nobody asked for.
PAUSED_SLEEP_PHASE_SECONDS = 2.0


@dataclass(frozen=True)
class PlayingView:
    """What the playing screen needs, already resolved."""

    title: str
    remaining_ms: int | None
    duration_ms: int | None
    paused: bool = False
    muted: bool = False
    # Which of the three sleep phases to draw. Only read while paused; the
    # caller advances it, so this stays a pure view.
    sleep_phase: int = 0

    @property
    def fraction(self) -> float:
        """How much of the track is behind us, 0.0-1.0."""
        if not self.duration_ms or self.remaining_ms is None:
            return 0.0
        played = self.duration_ms - self.remaining_ms
        return min(1.0, max(0.0, played / self.duration_ms))

    @property
    def time_text(self) -> str:
        """The remaining time in words, or what to say when there is none.

        Streams have no length and VLC does not always know one straight away,
        so "no remaining time" is a normal state rather than an error.
        """
        if self.remaining_ms is None:
            return UNKNOWN_TIME
        seconds = max(0, round(self.remaining_ms / 1000))
        if seconds >= 60:
            return f"noch {math.ceil(seconds / 60)} Min."
        # Rounded to ten: a display that ticks down every second on a panel
        # this size is noise, and the number is not that precise anyway.
        return f"noch {max(10, round(seconds / 10) * 10)} Sek."

    @property
    def arriving(self) -> bool:
        """In the home stretch - near enough the end for Knuffel to wave.

        A stream has no end to arrive at, so it is never true there.
        """
        return self.remaining_ms is not None and 0 <= self.remaining_ms <= ARRIVING_MS


def _title(draw: Any, view: PlayingView, band_top: int, band_height: int) -> None:
    """Fit the title into its band and draw it, centred vertically."""
    title_width = WIDTH - 4
    if view.muted:
        speaker(draw, *MUTE_XY, MUTE_GLYPH, muted=True)
        title_width -= MUTE_GLYPH + 6

    font, lines, size = fit_lines(
        draw,
        view.title or "",
        title_width,
        TITLE_MAX_LINES,
        TITLE_SIZES,
        fonts.REGULAR,
        max_height=band_height,
        line_gap=TITLE_LINE_GAP,
    )
    # Centred in the band, so a one-line title does not hang from the top edge
    # while a two-line one fills it.
    height = block_height(size, len(lines), TITLE_LINE_GAP)
    top = band_top + max(0, (band_height - height) // 2)
    for index, line in enumerate(lines):
        draw_text(draw, (2, top + size + index * (size + TITLE_LINE_GAP)), line, font)


def _render_paused(view: PlayingView) -> Any:
    """Title, bar, and Knuffel asleep with the Zs coming off him."""
    img, draw = new_frame()

    _title(draw, view, PAUSED_TITLE_TOP, PAUSED_TITLE_BAND_HEIGHT)
    bar(draw, PAUSED_BAR_BOX, view.fraction)

    # The sleeper and his Zs are centred as one group, so he does not sit
    # off-centre with empty panel beside him.
    group = PAUSED_SLEEPER_SIZE + PAUSED_Z_GAP + SLEEP_ZS_WIDTH
    left = max(2, (WIDTH - group) // 2)
    knuffel.draw(
        draw, left, PAUSED_SLEEPER_TOP, PAUSED_SLEEPER_SIZE, knuffel.ASLEEP
    )
    sleep_zs(
        draw,
        left + PAUSED_SLEEPER_SIZE + PAUSED_Z_GAP,
        PAUSED_Z_TOP,
        view.sleep_phase % SLEEP_ZS_PHASES + 1,
    )
    return img


def _walk(draw: Any, view: PlayingView) -> None:
    """Knuffel on the track, at the point the song has reached.

    Behind him the line is thickened - that stretch is done; ahead it stays a
    thin rule. He stands at the join, and near the end he turns to wave.
    """
    fraction = max(0.0, min(1.0, view.fraction))
    overhang = knuffel.wave_overhang(WALK_KNUFFEL)
    x_max = WALK_X1 - WALK_KNUFFEL - overhang
    kx = WALK_X0 + round(fraction * (x_max - WALK_X0))
    join = kx + WALK_KNUFFEL // 2

    # Ahead of him a thin rule; behind him a thicker bar for the stretch that
    # is done, so a parent gets "this much played" as well as "this far to go".
    draw.line([(join, WALK_LINE_Y), (WALK_X1, WALK_LINE_Y)], fill=1, width=1)
    draw.rectangle([WALK_X0, WALK_LINE_Y - 2, join, WALK_LINE_Y + 2], fill=1)

    mood = knuffel.WAVE_UP if view.arriving else knuffel.AWAKE
    knuffel.draw(draw, kx, WALK_LINE_Y - WALK_KNUFFEL, WALK_KNUFFEL, mood)


def render(view: PlayingView) -> Any:
    """Return the frame for *view* as a mode-'1' image."""
    if view.paused:
        return _render_paused(view)

    img, draw = new_frame()
    _title(draw, view, TITLE_TOP, TITLE_BAND_HEIGHT)
    _walk(draw, view)
    return img
