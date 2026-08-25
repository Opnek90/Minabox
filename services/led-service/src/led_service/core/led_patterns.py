"""LED pattern implementations.

This module provides async pattern functions that control LED behavior
according to the pattern types defined in the LED service architecture:
- solid: LED permanently on (duration_ms is intentionally ignored)
- blink: LED toggles at regular intervals
- pulse: LED briefly lights up then turns off
- glow: smooth breathing effect via Software PWM (PWMLED) using a sine curve

``repeat`` counts whole cycles everywhere: one blink is on *and* off again,
one pulse is on and off again, one glow cycle is dark to bright and back.
An earlier version counted blink toggles instead, so ``repeat: 2`` produced a
single blink and the "5 second" test blink lasted 2.5 seconds.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

import structlog

from ..exceptions import InvalidPatternError

if TYPE_CHECKING:
    from gpiozero import LED, PWMLED

logger = structlog.get_logger(__name__)

# Number of brightness steps per glow cycle. Higher = smoother, higher CPU cost.
# 50 steps is imperceptible on slow cycles (>= 1 s) and negligible for the Pi.
_GLOW_STEPS = 50


async def _sleep_or_cancel(cancel_event: asyncio.Event, seconds: float) -> bool:
    """Wait for ``seconds`` unless the pattern is cancelled first.

    Every pattern needs the same "sleep, but wake up immediately when someone
    overrides me" step, and writing it inline meant a try/except around every
    single wait. Returns True if the pattern should stop.
    """
    if cancel_event.is_set():
        return True
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
    except TimeoutError:
        return False
    return True


async def run_solid_pattern(led: LED, led_id: str) -> None:
    """Run a solid pattern (LED permanently on).

    The LED is turned on and stays on indefinitely until another pattern
    overrides it. duration_ms is intentionally not a parameter here because
    'solid' means constant light -- a duration would contradict that semantics
    and previously caused the LED not to light up when duration_ms was non-zero.

    Args:
        led: The gpiozero LED instance to control.
        led_id: LED identifier for logging.
    """
    led.on()
    logger.debug("pattern_solid_started", led_id=led_id)
    # LED stays on until another pattern overrides it -- no sleep, no led.off()


async def run_off_pattern(led: LED, led_id: str) -> None:
    """Turn the LED off immediately without any visible pulse.

    Useful for logical states like 'audio_stopped' or 'audio_paused'
    that may arrive frequently without any visible indication desired.
    """
    led.off()
    logger.debug("pattern_off_applied", led_id=led_id)


async def run_blink_pattern(
    led: LED,
    interval_ms: int,
    repeat: int | None,
    led_id: str,
    cancel_event: asyncio.Event,
) -> None:
    """Run a blink pattern (LED toggles at regular intervals).

    Args:
        led: The gpiozero LED instance to control.
        interval_ms: Time in milliseconds the LED stays on, and stays off.
        repeat: Number of complete on/off blinks (0 or None means infinite).
        led_id: LED identifier for logging.
        cancel_event: Event to signal pattern cancellation.

    Raises:
        InvalidPatternError: If interval_ms is not positive.
    """
    if interval_ms <= 0:
        raise InvalidPatternError(
            f"Blink pattern requires positive interval_ms, got {interval_ms}"
        )

    interval_sec = interval_ms / 1000.0
    blinks = 0
    infinite = repeat is None or repeat == 0

    logger.debug(
        "pattern_blink_started",
        led_id=led_id,
        interval_ms=interval_ms,
        repeat=repeat,
        infinite=infinite,
    )

    try:
        while infinite or blinks < repeat:
            led.on()
            if await _sleep_or_cancel(cancel_event, interval_sec):
                break
            led.off()
            if await _sleep_or_cancel(cancel_event, interval_sec):
                break
            blinks += 1
    finally:
        led.off()
        logger.debug("pattern_blink_finished", led_id=led_id, blinks=blinks)


async def run_pulse_pattern(
    led: LED,
    duration_ms: int,
    repeat: int | None,
    led_id: str,
    cancel_event: asyncio.Event,
) -> None:
    """Run a pulse pattern (LED briefly lights up then turns off).

    Args:
        led: The gpiozero LED instance to control.
        duration_ms: Duration of each pulse in milliseconds.
        repeat: Number of pulses (0 or None means infinite).
        led_id: LED identifier for logging.
        cancel_event: Event to signal pattern cancellation.

    Raises:
        InvalidPatternError: If duration_ms is not positive.
    """
    if duration_ms <= 0:
        raise InvalidPatternError(
            f"Pulse pattern requires positive duration_ms, got {duration_ms}"
        )

    duration_sec = duration_ms / 1000.0
    # Gap between pulses: at most 1/3 of pulse duration, minimum 100 ms.
    gap_sec = max(100.0, duration_ms / 3) / 1000.0
    pulses = 0
    infinite = repeat is None or repeat == 0

    logger.debug(
        "pattern_pulse_started",
        led_id=led_id,
        duration_ms=duration_ms,
        repeat=repeat,
        infinite=infinite,
    )

    try:
        while infinite or pulses < repeat:
            led.on()
            if await _sleep_or_cancel(cancel_event, duration_sec):
                break
            led.off()
            pulses += 1

            # No trailing gap after the last pulse -- it would only delay the
            # next pattern by up to a third of a pulse for no visible effect.
            if not infinite and pulses >= repeat:
                break
            if await _sleep_or_cancel(cancel_event, gap_sec):
                break
    finally:
        led.off()
        logger.debug("pattern_pulse_finished", led_id=led_id, pulses=pulses)


def _glow_brightness(step: int, min_brightness: float, span: float) -> float:
    """Brightness of one glow step on a sine curve, starting and ending dark."""
    angle = (step / _GLOW_STEPS) * math.pi * 2
    # cos goes 1..-1..1; map to 0..1..0 then scale into the brightness range
    return min_brightness + span * (0.5 - 0.5 * math.cos(angle))


async def run_glow_pattern(
    led: PWMLED,
    cycle_ms: int,
    min_brightness: float,
    max_brightness: float,
    repeat: int | None,
    led_id: str,
    cancel_event: asyncio.Event,
) -> None:
    """Run a glow (breathing) pattern using Software PWM via PWMLED.

    Brightness follows a sine curve: dark -> bright -> dark over one cycle.
    The effect is smooth and natural for slow ambient cycles (>= 1 s).

    Stops cleanly on cancel_event between every brightness step so the LED
    never freezes at an intermediate brightness level after cancellation.

    Args:
        led: A gpiozero PWMLED instance (not a plain LED).
        cycle_ms: Duration of one full glow cycle in milliseconds (min 500).
        min_brightness: Minimum brightness value 0.0-1.0.
        max_brightness: Maximum brightness value 0.0-1.0.
        repeat: Number of cycles. 0 or None means infinite.
        led_id: LED identifier for logging.
        cancel_event: Event to signal pattern cancellation.

    Raises:
        InvalidPatternError: If cycle_ms < 500 or brightness values are invalid.
    """
    if cycle_ms < 500:
        raise InvalidPatternError(
            f"Glow pattern requires cycle_ms >= 500, got {cycle_ms}"
        )
    if not (0.0 <= min_brightness <= 1.0 and 0.0 <= max_brightness <= 1.0):
        raise InvalidPatternError(
            f"Glow brightness values must be in [0.0, 1.0], "
            f"got min={min_brightness} max={max_brightness}"
        )
    if min_brightness >= max_brightness:
        raise InvalidPatternError(
            f"Glow min_brightness ({min_brightness}) must be less than "
            f"max_brightness ({max_brightness})"
        )

    step_sec = (cycle_ms / 1000.0) / _GLOW_STEPS
    span = max_brightness - min_brightness
    cycles = 0
    infinite = repeat is None or repeat == 0

    logger.debug(
        "pattern_glow_started",
        led_id=led_id,
        cycle_ms=cycle_ms,
        min_brightness=min_brightness,
        max_brightness=max_brightness,
        repeat=repeat,
        infinite=infinite,
    )

    try:
        while infinite or cycles < repeat:
            cancelled = False
            for step in range(_GLOW_STEPS):
                led.value = _glow_brightness(step, min_brightness, span)
                if await _sleep_or_cancel(cancel_event, step_sec):
                    cancelled = True
                    break
            if cancelled:
                break
            cycles += 1
    finally:
        led.value = 0.0
        logger.debug("pattern_glow_finished", led_id=led_id, cycles=cycles)
