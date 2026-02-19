from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

import structlog

from .events import RawButtonEvent


logger = structlog.get_logger(__name__)

# Max delay between two presses to count as double-click (seconds).
DOUBLE_PRESS_WINDOW_S: float = 0.4


@dataclass(slots=True)
class PressClassifier:
    """Classify push-button interactions into raw events.

    We leverage gpiozero's HoldMixin callbacks (`when_pressed`, `when_held`,
    `when_released`). A long-press does not emit short-press. A second press
    within DOUBLE_PRESS_WINDOW_S of a release is classified as double_press
    (on second release); otherwise the first release becomes short_press after
    the window expires.
    """

    source_id: str
    emit: Callable[[RawButtonEvent], None]
    _held_fired: bool = False
    _pending_short_timer: threading.Timer | None = None
    _possible_double: bool = False

    def on_pressed(self) -> None:
        if self._pending_short_timer is not None:
            self._pending_short_timer.cancel()
            self._pending_short_timer = None
            self._possible_double = True
            self._held_fired = False
            logger.debug("button_pressed", source_id=self.source_id)
            return
        self._possible_double = False
        self._held_fired = False
        logger.debug("button_pressed", source_id=self.source_id)

    def on_held(self) -> None:
        self._held_fired = True
        if self._possible_double:
            self._possible_double = False
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
        if self._possible_double:
            self._possible_double = False
            event = RawButtonEvent(
                source_id=self.source_id,
                event_type="double_press",
                timestamp=RawButtonEvent.now_utc(),
            )
            self.emit(event)
            logger.debug("button_double_press_emitted", source_id=self.source_id)
            return

        def fire_short() -> None:
            self._pending_short_timer = None
            event = RawButtonEvent(
                source_id=self.source_id,
                event_type="short_press",
                timestamp=RawButtonEvent.now_utc(),
            )
            self.emit(event)
            logger.debug("button_short_press_emitted", source_id=self.source_id)

        self._pending_short_timer = threading.Timer(DOUBLE_PRESS_WINDOW_S, fire_short)
        self._pending_short_timer.start()


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

