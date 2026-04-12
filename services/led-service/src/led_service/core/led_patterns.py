"""LED pattern implementations.

This module provides async pattern functions that control LED behavior
according to the pattern types defined in the LED service architecture:
- solid: LED permanently on (duration_ms is intentionally ignored)
- blink: LED toggles at regular intervals
- pulse: LED briefly lights up then turns off
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from ..exceptions import InvalidPatternError

if TYPE_CHECKING:
    from gpiozero import LED

logger = structlog.get_logger(__name__)

async def run_solid_pattern(
    led: LED,
    led_id: str,
) -> None:
    """Run a solid pattern (LED permanently on).

    The LED is turned on and stays on indefinitely until another pattern
    overrides it. duration_ms is intentionally not a parameter here because
    'solid' means constant light — a duration would contradict that semantics
    and previously caused the LED not to light up when duration_ms was non-zero.

    Args:
        led: The gpiozero LED instance to control.
        led_id: LED identifier for logging.
    """
    led.on()
    logger.debug("pattern_solid_started", led_id=led_id)
    # LED stays on until another pattern overrides it — no sleep, no led.off()

async def run_off_pattern(
    led: LED,
    led_id: str,
) -> None:
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
        interval_ms: Time in milliseconds between toggles.
        repeat: Number of blink cycles (0 or None means infinite).
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
    cycles = 0
    infinite = repeat is None or repeat == 0

    logger.debug(
        "pattern_blink_started",
        led_id=led_id,
        interval_ms=interval_ms,
        repeat=repeat,
        infinite=infinite,
    )

    try:
        while infinite or cycles < repeat:
            if cancel_event.is_set():
                logger.debug("pattern_blink_cancelled", led_id=led_id, cycles=cycles)
                break

            if led.is_lit:
                led.off()
            else:
                led.on()

            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=interval_sec,
                )
                break
            except asyncio.TimeoutError:
                pass

            if not infinite:
                cycles += 1
    finally:
        led.off()
        logger.debug(
            "pattern_blink_finished",
            led_id=led_id,
            cycles=cycles,
        )

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
            if cancel_event.is_set():
                logger.debug("pattern_pulse_cancelled", led_id=led_id, pulses=pulses)
                break

            led.on()

            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=duration_sec,
                )
                break
            except asyncio.TimeoutError:
                pass

            led.off()

            if not infinite:
                pulses += 1

            # Gap between pulses: at most 1/3 of pulse duration, minimum 100 ms.
            gap_ms = max(100, duration_ms / 3)
            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=gap_ms / 1000.0,
                )
                break
            except asyncio.TimeoutError:
                pass
    finally:
        led.off()
        logger.debug(
            "pattern_pulse_finished",
            led_id=led_id,
            pulses=pulses,
        )
