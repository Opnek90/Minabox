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

# Where he is allowed to stand, so no part of him leaves the panel.
BOUNDS = (2, 2, 128 - SIZE - 2, 64 - SIZE - 2)


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
        self._asleep = False

    def set_asleep(self, asleep: bool) -> None:
        """At night he sleeps: eyes shut, and nothing moves.

        A bright thing wandering around a dark child's bedroom is the opposite
        of what a night mode is for, and a still panel is also the cheapest
        thing this service can do.
        """
        self._asleep = asleep
        if asleep:
            self._target = None

    def pose(self) -> Pose:
        offset = 1 if self._breath_up and not self._asleep else 0
        if self._asleep:
            mood = knuffel.ASLEEP
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
            self._target = self._pick_target()
            self._next_step = now
        if self._target is not None and now >= self._next_step:
            self._step(now)

    # ------------------------------------------------------------------

    def _pick_target(self) -> tuple[int, int]:
        """Somewhere else, and far enough that the walk is visible."""
        x0, y0, x1, y1 = BOUNDS
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
