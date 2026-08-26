"""How Knuffel behaves while nothing is playing.

Pure random movement looks broken - it twitches rather than walks. What reads
as alive is mostly stillness with the eyes doing the work, and occasional
movement that has somewhere to go:

* he breathes, a single pixel up and down;
* he blinks, every few seconds, briefly;
* every half minute or so he picks a spot and walks there.

Each of those is a small rectangle on the bus rather than a whole frame - a
blink is one page of the eye row - so the whole thing costs about one percent
of a bus that the RFID reader needs free, which is the only reason an animated
idle screen is defensible at all.

No wall clock here: the caller supplies the time, so tests can move it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..render import knuffel

# 38 px on a 128x64 panel: he owns the screen, and the arithmetic still works.
# The dirty rectangle when he moves is his own area plus the step, so 40 columns
# across 6 pages - 240 bytes, 22 ms. That is 18 % of the bus while he is walking
# and 1.8 % while he only breathes and blinks, which is nearly all of the time.
SIZE = 38

BREATH_SECONDS = 1.2
BLINK_EVERY = (3.0, 8.0)
BLINK_SECONDS = 0.18
WALK_EVERY = (20.0, 60.0)
STEP_SECONDS = 0.12
STEP_PIXELS = 2

WAVE_EVERY = (25.0, 70.0)
WAVE_SECONDS = 1.8
WAVE_PHASE_SECONDS = 0.22

# Where he is allowed to stand, so no part of him leaves the panel - including
# the arm, which reaches further right than the rest of him. PIL clips silently,
# so a hand drawn past the edge would simply not be there.
_OVERHANG = knuffel.wave_overhang(SIZE)
BOUNDS = (2, 2, 128 - SIZE - _OVERHANG - 2, 64 - SIZE - 2)


@dataclass(frozen=True)
class Pose:
    """Everything the renderer needs for one frame."""

    x: int
    y: int
    mood: str

    @property
    def size(self) -> int:
        return SIZE


class IdleAnimation:
    """Knuffel's behaviour, advanced by a clock the caller owns."""

    def __init__(self, now: float, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        x0, y0, x1, y1 = BOUNDS
        self._x = self._rng.randint(x0, x1)
        self._y = self._rng.randint(y0, y1)
        self._target: tuple[int, int] | None = None
        self._breath_up = False
        self._next_breath = now + BREATH_SECONDS
        self._next_blink = now + self._rng.uniform(*BLINK_EVERY)
        self._blink_until = 0.0
        self._next_walk = now + self._rng.uniform(*WALK_EVERY)
        self._next_step = 0.0
        self._next_wave = now + self._rng.uniform(*WAVE_EVERY)
        self._wave_until = 0.0
        self._wave_next_phase = 0.0
        self._wave_up = False
        self._asleep = False
        # Pixels on the right kept clear for the marks on the idle screen.
        self._reserved = 0

    def wave_now(self, now: float) -> None:
        """Wave because something just happened, not because a timer came round.

        Any walk in progress is abandoned - one thing at a time - and both its
        deadline and the next scheduled wave are pushed into the future.
        Leaving either behind is how the render loop ends up spinning against
        a deadline that has already passed.
        """
        if self._asleep:
            return
        self._target = None
        self._next_walk = now + self._rng.uniform(*WALK_EVERY)
        self._wave_until = now + WAVE_SECONDS
        self._wave_up = True
        self._wave_next_phase = now + WAVE_PHASE_SECONDS
        self._next_wave = now + WAVE_SECONDS + self._rng.uniform(*WAVE_EVERY)

    def set_reserved(self, width: int, now: float) -> None:
        """Keep *width* pixels on the right clear of him.

        The marks on the idle screen live there. Rather than letting him walk
        underneath them - on a one-bit panel two lit shapes simply merge - he
        stays out, and walks off if the strip appears while he is standing in
        it. He walks rather than jumps, so there is a second or two of overlap
        while he leaves.

        *now* is not decoration: starting a walk means the step deadline has to
        be set with it, or next_due() reports the one left over from the last
        walk - a time already past - and the render loop spins.
        """
        if width == self._reserved:
            return
        self._reserved = width
        if self._x > self._max_x() and not self._asleep:
            self._target = (self._max_x(), self._y)
            self._next_step = now

    @property
    def reserved(self) -> int:
        """Pixels currently kept clear on the right."""
        return self._reserved

    def _max_x(self) -> int:
        return max(BOUNDS[0], BOUNDS[2] - self._reserved)

    @property
    def walking(self) -> bool:
        """True while he is on his way somewhere.

        Exposed because "is he moving" cannot be told from the pose: breathing
        shifts him a pixel too, and a test comparing positions would call that
        a walk.
        """
        return self._target is not None

    def set_asleep(self, asleep: bool) -> None:
        """At night he sleeps: eyes shut, and nothing moves.

        A bright thing wandering around a dark child's bedroom is the opposite
        of what a night mode is for, and a still panel is also the cheapest
        thing this service can do.
        """
        self._asleep = asleep
        if asleep:
            self._target = None
            self._wave_until = 0.0

    def pose(self) -> Pose:
        offset = 1 if self._breath_up and not self._asleep else 0
        if self._asleep:
            mood = knuffel.ASLEEP
        elif self._wave_until:
            mood = knuffel.WAVE_UP if self._wave_up else knuffel.WAVE_DOWN
        elif self._blink_until:
            mood = knuffel.BLINK
        else:
            mood = knuffel.AWAKE
        return Pose(x=self._x, y=self._y - offset, mood=mood)

    def next_due(self) -> float:
        """When this wants to be advanced again, as an absolute clock reading.

        Each concern contributes exactly one deadline, and only the one that
        can still happen: while he is walking, the deadline for *starting* a
        walk is already behind us, and reporting that would hand the caller a
        time in the past. A render loop that sets its timeout from this would
        then spin at full speed for as long as the walk lasted.
        """
        if self._asleep:
            return float("inf")
        due = [
            self._next_breath,
            self._blink_until if self._blink_until else self._next_blink,
            self._next_step if self._target is not None else self._next_walk,
            self._wave_next_phase if self._wave_until else self._next_wave,
        ]
        return min(due)

    def advance(self, now: float) -> None:
        """Move time forward. The pose afterwards is what should be drawn."""
        if self._asleep:
            return
        if now >= self._next_breath:
            self._breath_up = not self._breath_up
            self._next_breath = now + BREATH_SECONDS
        if self._blink_until and now >= self._blink_until:
            self._blink_until = 0.0
        elif not self._blink_until and now >= self._next_blink:
            self._blink_until = now + BLINK_SECONDS
            self._next_blink = now + self._rng.uniform(*BLINK_EVERY)
        if self._target is None and now >= self._next_walk:
            if self._wave_until:
                # Not while he is waving. Pushed back rather than skipped: the
                # deadline feeds next_due(), and one left in the past spins the
                # render loop.
                self._next_walk = now + self._rng.uniform(*WALK_EVERY)
            else:
                self._target = self._pick_target()
                self._next_step = now
        if self._target is not None and now >= self._next_step:
            self._step(now)
        self._advance_wave(now)

    def _advance_wave(self, now: float) -> None:
        """Waving, and never while walking - one thing at a time reads better.

        A wave that falls due mid-walk is pushed back rather than skipped: its
        deadline feeds next_due(), and leaving one in the past would spin the
        render loop.
        """
        if self._wave_until:
            if now >= self._wave_until:
                self._wave_until = 0.0
            elif now >= self._wave_next_phase:
                self._wave_up = not self._wave_up
                self._wave_next_phase = now + WAVE_PHASE_SECONDS
            return
        if now < self._next_wave:
            return
        if self._target is not None:
            self._next_wave = now + self._rng.uniform(*WAVE_EVERY)
            return
        self._wave_until = now + WAVE_SECONDS
        self._wave_up = True
        self._wave_next_phase = now + WAVE_PHASE_SECONDS
        self._next_wave = now + WAVE_SECONDS + self._rng.uniform(*WAVE_EVERY)

    # ------------------------------------------------------------------

    def _pick_target(self) -> tuple[int, int]:
        """Somewhere else, and far enough that the walk is visible."""
        x0, y0, _, y1 = BOUNDS
        x1 = self._max_x()
        for _ in range(8):
            x = self._rng.randint(x0, x1)
            y = self._rng.randint(y0, y1)
            if abs(x - self._x) + abs(y - self._y) >= 20:
                return x, y
        return x0 if self._x > (x0 + x1) // 2 else x1, self._y

    def _step(self, now: float) -> None:
        target_x, target_y = self._target
        self._x += _towards(self._x, target_x)
        self._y += _towards(self._y, target_y)
        self._next_step = now + STEP_SECONDS
        if (self._x, self._y) == (target_x, target_y):
            self._target = None
            self._next_walk = now + self._rng.uniform(*WALK_EVERY)


def _towards(value: int, target: int) -> int:
    """One step of at most STEP_PIXELS in the right direction."""
    delta = target - value
    if delta == 0:
        return 0
    return max(-STEP_PIXELS, min(STEP_PIXELS, delta))
