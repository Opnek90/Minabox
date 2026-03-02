"""LED pattern implementations.

This module provides async pattern functions that control LED behavior
according to the pattern types defined in the LED service architecture:
- solid: LED permanently on or off
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
    duration_ms: int | None,
    led_id: str,
) -> None:
    """Run a solid pattern (LED permanently on).
    
    Args:
        led: The gpiozero LED instance to control.
        duration_ms: Duration in milliseconds (0 or None means infinite).
        led_id: LED identifier for logging.
    """
    led.on()
    logger.debug(
        "pattern_solid_started",
        led_id=led_id,
        duration_ms=duration_ms,
    )
    
    if duration_ms and duration_ms > 0:
        await asyncio.sleep(duration_ms / 1000.0)
        led.off()
        logger.debug("pattern_solid_finished", led_id=led_id)
    # If duration is 0 or None, LED stays on until another pattern overrides

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
            
            # Toggle LED
            if led.is_lit:
                led.off()
            else:
                led.on()
            
            # Wait for interval or cancellation
            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=interval_sec,
                )
                # Event was set, cancel pattern
                break
            except asyncio.TimeoutError:
                # Normal interval elapsed, continue
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
            
            # Pulse on
            led.on()
            
            # Wait for pulse duration or cancellation
            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=duration_sec,
                )
                # Event was set, cancel pattern
                break
            except asyncio.TimeoutError:
                # Normal pulse duration elapsed
                pass
            
            # Pulse off
            led.off()
            
            if not infinite:
                pulses += 1
            
            # Gap between pulses: deutlich kürzer als der Puls selbst,
            # damit Pulse wie ein kurzer „Ping“ wirkt (kurzes Aus, dann wieder an).
            # Pause = höchstens 1/3 der Pulse-Dauer, mindestens 100ms.
            gap_ms = max(100, duration_ms / 3)
            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=gap_ms / 1000.0,
                )
                # Event was set, cancel pattern
                break
            except asyncio.TimeoutError:
                # Normal gap elapsed, continue
                pass
    finally:
        led.off()
        logger.debug(
            "pattern_pulse_finished",
            led_id=led_id,
            pulses=pulses,
        )
