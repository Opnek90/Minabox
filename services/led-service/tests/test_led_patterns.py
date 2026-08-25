"""Tests for the pattern coroutines, above all the meaning of ``repeat``.

``repeat`` counts whole cycles: one blink is on and off again. It used to count
toggles for blink but pulses for pulse, which is why ``repeat: 2`` produced a
single blink and the "5 second" test blink lasted 2.5 seconds.
"""

from __future__ import annotations

import asyncio

import pytest
from led_test_doubles import FakeClock, FakeLED

from led_service.core import led_patterns
from led_service.core.led_patterns import (
    _GLOW_STEPS,
    run_blink_pattern,
    run_glow_pattern,
    run_off_pattern,
    run_pulse_pattern,
    run_solid_pattern,
)
from led_service.exceptions import InvalidPatternError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", fake)
    return fake


# --- the shared wait helper --------------------------------------------------


async def test_sleep_or_cancel_reports_the_timeout_as_not_cancelled() -> None:
    assert await led_patterns._sleep_or_cancel(asyncio.Event(), 0.01) is False


async def test_sleep_or_cancel_returns_immediately_when_already_cancelled() -> None:
    """A pre-set event must not cost a full interval before the pattern stops."""
    event = asyncio.Event()
    event.set()

    assert await led_patterns._sleep_or_cancel(event, 30.0) is True


async def test_sleep_or_cancel_wakes_up_when_the_event_is_set() -> None:
    event = asyncio.Event()
    waiter = asyncio.create_task(led_patterns._sleep_or_cancel(event, 30.0))
    await asyncio.sleep(0)
    event.set()

    assert await asyncio.wait_for(waiter, timeout=1.0) is True


# --- solid and off -----------------------------------------------------------


async def test_solid_switches_on_and_leaves_it_there() -> None:
    led = FakeLED()

    await run_solid_pattern(led, "led_1")

    assert led.transitions == ["on"]


async def test_off_switches_off_without_a_visible_pulse() -> None:
    led = FakeLED()

    await run_off_pattern(led, "led_1")

    assert led.transitions == ["off"]


# --- blink -------------------------------------------------------------------


async def test_one_blink_is_on_and_off_again(clock: FakeClock) -> None:
    led = FakeLED()

    await run_blink_pattern(led, 500, 1, "led_1", asyncio.Event())

    # The trailing off comes from the finally block and is a no-op here.
    assert led.transitions == ["on", "off", "off"]
    assert clock.waits == [0.5, 0.5]


async def test_repeat_counts_whole_blinks(clock: FakeClock) -> None:
    led = FakeLED()

    await run_blink_pattern(led, 200, 3, "led_1", asyncio.Event())

    assert led.transitions.count("on") == 3
    assert clock.waits == [0.2] * 6


@pytest.mark.parametrize("repeat", [None, 0])
async def test_blink_repeats_forever_until_cancelled(
    repeat: int | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = FakeLED()
    clock = FakeClock(cancel_after=7)
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", clock)

    await run_blink_pattern(led, 100, repeat, "led_1", asyncio.Event())

    assert len(clock.waits) == 7
    assert led.transitions[-1] == "off"


async def test_a_cancelled_blink_never_leaves_the_led_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling mid-blink used to be the only way to strand a lit LED."""
    led = FakeLED()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", FakeClock(cancel_after=1))

    await run_blink_pattern(led, 500, 0, "led_1", asyncio.Event())

    assert led.is_lit is False
    assert led.transitions[-1] == "off"


async def test_blink_rejects_a_non_positive_interval() -> None:
    with pytest.raises(InvalidPatternError):
        await run_blink_pattern(FakeLED(), 0, 1, "led_1", asyncio.Event())


# --- pulse -------------------------------------------------------------------


async def test_repeat_counts_whole_pulses(clock: FakeClock) -> None:
    led = FakeLED()

    await run_pulse_pattern(led, 300, 2, "led_1", asyncio.Event())

    assert led.transitions == ["on", "off", "on", "off", "off"]


async def test_the_last_pulse_has_no_trailing_gap(clock: FakeClock) -> None:
    """The gap after the final pulse only delayed the next pattern."""
    led = FakeLED()

    await run_pulse_pattern(led, 300, 2, "led_1", asyncio.Event())

    # duration, gap, duration -- and then nothing.
    assert clock.waits == [0.3, 0.1, 0.3]


async def test_the_pulse_gap_is_a_third_of_the_duration_but_at_least_100ms(
    clock: FakeClock,
) -> None:
    led = FakeLED()

    await run_pulse_pattern(led, 900, 2, "led_1", asyncio.Event())

    assert clock.waits == [0.9, 0.3, 0.9]


async def test_a_cancelled_pulse_never_leaves_the_led_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    led = FakeLED()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", FakeClock(cancel_after=1))

    await run_pulse_pattern(led, 300, 0, "led_1", asyncio.Event())

    assert led.is_lit is False


async def test_pulse_rejects_a_non_positive_duration() -> None:
    with pytest.raises(InvalidPatternError):
        await run_pulse_pattern(FakeLED(), 0, 1, "led_1", asyncio.Event())


# --- glow --------------------------------------------------------------------


async def test_one_glow_cycle_runs_every_brightness_step(clock: FakeClock) -> None:
    led = FakeLED()

    await run_glow_pattern(led, 2000, 0.0, 1.0, 1, "led_1", asyncio.Event())

    # Every step, plus the final 0.0 from the finally block.
    assert len(led.values) == _GLOW_STEPS + 1
    assert clock.waits == [2.0 / _GLOW_STEPS] * _GLOW_STEPS


async def test_glow_starts_dark_peaks_in_the_middle_and_ends_dark(
    clock: FakeClock,
) -> None:
    led = FakeLED()

    await run_glow_pattern(led, 2000, 0.0, 1.0, 1, "led_1", asyncio.Event())

    steps = led.values[:_GLOW_STEPS]
    assert steps[0] == pytest.approx(0.0, abs=1e-9)
    assert steps[_GLOW_STEPS // 2] == pytest.approx(1.0, abs=1e-9)
    assert led.values[-1] == 0.0


async def test_glow_stays_inside_the_configured_brightness_range(
    clock: FakeClock,
) -> None:
    led = FakeLED()

    await run_glow_pattern(led, 1000, 0.2, 0.8, 1, "led_1", asyncio.Event())

    assert min(led.values[:_GLOW_STEPS]) == pytest.approx(0.2)
    assert max(led.values[:_GLOW_STEPS]) == pytest.approx(0.8)


async def test_repeat_counts_whole_glow_cycles(clock: FakeClock) -> None:
    led = FakeLED()

    await run_glow_pattern(led, 500, 0.0, 1.0, 3, "led_1", asyncio.Event())

    assert len(clock.waits) == 3 * _GLOW_STEPS


async def test_a_cancelled_glow_fades_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling between steps must not freeze the LED at half brightness."""
    led = FakeLED()
    monkeypatch.setattr(led_patterns, "_sleep_or_cancel", FakeClock(cancel_after=5))

    await run_glow_pattern(led, 2000, 0.0, 1.0, 0, "led_1", asyncio.Event())

    assert led.values[-1] == 0.0


async def test_glow_rejects_a_cycle_too_short_to_look_smooth() -> None:
    with pytest.raises(InvalidPatternError):
        await run_glow_pattern(FakeLED(), 100, 0.0, 1.0, 1, "led_1", asyncio.Event())


async def test_glow_rejects_a_range_it_cannot_breathe_in() -> None:
    """The schema repairs this, but the coroutine stays the last line of defence."""
    with pytest.raises(InvalidPatternError):
        await run_glow_pattern(FakeLED(), 2000, 0.8, 0.2, 1, "led_1", asyncio.Event())
