"""How Knuffel behaves while nothing is playing.

The invariant that matters most is not how he looks but when he asks to be
drawn again: the render loop sets its timeout from next_due(), so a deadline
in the past turns into a loop spinning at full speed. That is exactly what
happened while he was walking, because the deadline for *starting* a walk was
left in the list after one had already started.
"""

from __future__ import annotations

import random

import pytest

from display_service.core.idle_animation import (
    BLINK_SECONDS,
    BOUNDS,
    SIZE,
    IdleAnimation,
)
from display_service.render import knuffel


def _anim(seed: int = 7, now: float = 0.0) -> IdleAnimation:
    return IdleAnimation(now=now, rng=random.Random(seed))


class TestDeadlines:
    @pytest.mark.parametrize("seed", [1, 7, 42, 1234])
    def test_the_next_deadline_is_always_in_the_future(self, seed):
        """Three hours of simulated behaviour, every state it can reach."""
        anim = _anim(seed)
        now = 0.0
        for _ in range(20_000):
            due = anim.next_due()
            assert due > now, f"deadline in the past: {due} <= {now}"
            now = due
            anim.advance(now)
        assert now > 3 * 60 * 60

    def test_a_sleeping_creature_asks_for_nothing(self):
        """Nothing moves at night, so the loop can go back to its slow tick."""
        anim = _anim()
        anim.set_asleep(True)
        assert anim.next_due() == float("inf")


class TestBehaviour:
    def test_he_stays_on_the_panel(self):
        anim = _anim()
        now = 0.0
        x0, y0, x1, y1 = BOUNDS
        for _ in range(20_000):
            now = anim.next_due()
            anim.advance(now)
            pose = anim.pose()
            assert x0 <= pose.x <= x1
            # One pixel of breathing lifts him above the top bound.
            assert y0 - 1 <= pose.y <= y1
            assert pose.x + SIZE <= 128
            assert pose.y + SIZE <= 64

    def test_he_blinks(self):
        anim = _anim()
        now, moods = 0.0, set()
        for _ in range(2_000):
            now = anim.next_due()
            anim.advance(now)
            moods.add(anim.pose().mood)
        assert knuffel.BLINK in moods
        assert knuffel.AWAKE in moods

    def test_a_blink_does_not_last(self):
        """Eyes shut for a fifth of a second, not until the next event."""
        anim = _anim()
        now = 0.0
        for _ in range(2_000):
            now = anim.next_due()
            anim.advance(now)
            if anim.pose().mood == knuffel.BLINK:
                break
        else:
            pytest.fail("never blinked")
        anim.advance(now + BLINK_SECONDS)
        assert anim.pose().mood != knuffel.BLINK

    def test_he_moves_somewhere_else(self):
        anim = _anim()
        start = (anim.pose().x, anim.pose().y)
        now = 0.0
        for _ in range(5_000):
            now = anim.next_due()
            anim.advance(now)
            if (anim.pose().x, anim.pose().y)[0] != start[0]:
                return
        pytest.fail("never went anywhere")

    def test_he_walks_rather_than_teleports(self):
        """Pure random placement reads as broken; steps read as walking."""
        anim = _anim()
        now = 0.0
        previous = (anim.pose().x, anim.pose().y)
        for _ in range(10_000):
            now = anim.next_due()
            anim.advance(now)
            current = (anim.pose().x, anim.pose().y)
            jump = abs(current[0] - previous[0]) + abs(current[1] - previous[1])
            assert jump <= 5, f"jumped {jump} px at once"
            previous = current

    def test_sleeping_stops_him_where_he_stands(self):
        anim = _anim()
        now = 0.0
        for _ in range(500):
            now = anim.next_due()
            anim.advance(now)
        anim.set_asleep(True)
        before = anim.pose()
        anim.advance(now + 3600)
        after = anim.pose()
        assert (after.x, after.y) == (before.x, before.y)
        assert after.mood == knuffel.ASLEEP

    def test_waking_up_gets_him_going_again(self):
        anim = _anim()
        anim.set_asleep(True)
        anim.set_asleep(False)
        assert anim.next_due() < float("inf")
        assert anim.pose().mood != knuffel.ASLEEP
