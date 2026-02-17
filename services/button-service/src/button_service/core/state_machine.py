from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import structlog

from .events import RawButtonEvent


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class PressClassifier:
    """Classify push-button interactions into raw events.

    We leverage gpiozero's HoldMixin callbacks (`when_pressed`, `when_held`,
    `when_released`) and ensure a long-press doesn't also emit a short-press.
    """

    source_id: str
    emit: Callable[[RawButtonEvent], None]
    _held_fired: bool = False

    def on_pressed(self) -> None:
        self._held_fired = False
        logger.debug("button_pressed", source_id=self.source_id)

    def on_held(self) -> None:
        # gpiozero guarantees this fires after hold_time seconds while pressed
        self._held_fired = True
        event = RawButtonEvent(
            source_id=self.source_id,
            event_type="long_press",
            timestamp=RawButtonEvent.now_utc(),
        )
        self.emit(event)
        logger.debug("button_long_press_emitted", source_id=self.source_id)

    def on_released(self) -> None:
        if self._held_fired:
            logger.debug("button_released_after_hold", source_id=self.source_id)
            return

        event = RawButtonEvent(
            source_id=self.source_id,
            event_type="short_press",
            timestamp=RawButtonEvent.now_utc(),
        )
        self.emit(event)
        logger.debug("button_short_press_emitted", source_id=self.source_id)


@dataclass(slots=True)
class EncoderSwitchEmitter:
    """Emit encoder switch presses as raw 'press' events.

    The button architecture uses 'press' as the event_type for the encoder
    switch (`sw` pin).
    """

    source_id: str
    emit: Callable[[RawButtonEvent], None]

    def on_pressed(self) -> None:
        event = RawButtonEvent(
            source_id=self.source_id,
            event_type="press",
            timestamp=RawButtonEvent.now_utc(),
        )
        self.emit(event)
        logger.debug("encoder_switch_press_emitted", source_id=self.source_id)


@dataclass(slots=True)
class EncoderRotationEmitter:
    """Emit rotary encoder rotation events."""

    source_id: str
    emit: Callable[[RawButtonEvent], None]
    steps_per_event: int = 1

    def on_clockwise(self) -> None:
        self._emit_steps(event_type="rotate_cw")

    def on_counter_clockwise(self) -> None:
        self._emit_steps(event_type="rotate_ccw")

    def _emit_steps(self, event_type: str) -> None:
        # gpiozero's RotaryEncoder can generate many events quickly; we emit
        # one RawButtonEvent per callback invocation by default.
        event = RawButtonEvent(
            source_id=self.source_id,
            event_type=event_type,  # type: ignore[arg-type]
            timestamp=RawButtonEvent.now_utc(),
        )
        self.emit(event)
        logger.debug("encoder_rotation_emitted", source_id=self.source_id, event_type=event_type)

