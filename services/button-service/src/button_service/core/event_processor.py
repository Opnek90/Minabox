"""Event processor: consume raw events from FIFO queue, apply mapping, publish to MQTT."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

import structlog

from ..config_schema import ButtonConfig, ButtonServiceConfig
from ..infrastructure.mqtt_client import MQTTClient
from .events import RawButtonEvent

logger = structlog.get_logger(__name__)

# Type-based debounce configuration (milliseconds)
# Push buttons get debouncing to prevent accidental rapid presses (child-proof)
# Rotary encoders get no debouncing for smooth volume control
DEBOUNCE_CONFIG = {
    "push": 300,    # 300ms cooldown for push buttons
    "rotary": 0,    # No debounce for rotary encoders (volume needs rapid events)
}


class ButtonDebouncer:
    """Tracks last-fired timestamp per button to prevent rapid duplicate events.
    
    Debouncing is type-based: push buttons get a cooldown, rotary encoders don't.
    This prevents children from accidentally triggering multiple play commands by
    mashing buttons, while keeping volume control smooth and responsive.
    """

    def __init__(self):
        self._last_fired: dict[str, float] = {}  # button_id → timestamp (ms)

    def should_fire(self, button: ButtonConfig) -> bool:
        """Check if button is allowed to fire based on type-specific cooldown.
        
        Args:
            button: Button configuration with id and type
            
        Returns:
            True if button should fire, False if still in cooldown period
        """
        cooldown_ms = DEBOUNCE_CONFIG.get(button.type, 0)
        
        # Rotary encoders and unknown types: always fire
        if cooldown_ms == 0:
            return True
        
        now = time.time() * 1000  # Current time in milliseconds
        last = self._last_fired.get(button.id, 0)
        
        # Check if cooldown period has elapsed
        if now - last < cooldown_ms:
            return False  # Still in cooldown, reject event
        
        # Update last-fired timestamp
        self._last_fired[button.id] = now
        return True


def _resolve_action(button: ButtonConfig, event_type: str) -> str | None:
    """Resolve logical action for a raw event type from button config.

    Returns:
        Action name if mapped, None if no mapping for this event_type.
    """
    if button.mode == "basic":
        return button.action or None
    if button.mode == "advanced" and button.actions:
        return button.actions.get(event_type)
    return None


async def run_event_processor(
    event_queue: asyncio.Queue[RawButtonEvent],
    get_config: Callable[[], ButtonServiceConfig | None],
    mqtt_client: MQTTClient,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Consume raw events from queue, map to actions, publish to MQTT.

    For every hardware event two things happen unconditionally:
      1. A raw-event is published on  minabox/{id}/button/raw-event
         so that the LED service and the WebUI hardware test-mode always
         receive feedback, regardless of whether an action mapping exists.
      2. If a logical action is configured for this event type it is
         published on  minabox/{id}/button/{action-name}  for the backend.

    Debouncing is applied before MQTT publish to prevent rapid duplicate commands.
    Raw events are still published for LED feedback even if debounced.

    Runs until shutdown_event is set (if provided) or the queue is closed.
    """
    logger.debug("event_processor_started")
    debouncer = ButtonDebouncer()

    while True:
        try:
            if shutdown_event and shutdown_event.is_set():
                logger.debug("event_processor_shutdown_requested")
                break

            # Wait for next event with short timeout to allow shutdown check
            try:
                event = await asyncio.wait_for(
                    event_queue.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue

            config = get_config()
            if not config:
                logger.warning("event_processor_no_config", source_id=event.source_id)
                continue

            button = next((b for b in config.buttons if b.id == event.source_id), None)
            if not button:
                logger.warning("event_processor_unknown_source", source_id=event.source_id)
                continue

            event_type_str = event.event_type

            # Always publish raw event — required by LED service (blink) and
            # WebUI hardware test-mode, not just for debugging.
            await mqtt_client.publish_raw_event(
                button_id=button.id,
                name=button.name,
                button_type=button.type,
                event_type=event_type_str,
            )

            # Apply debouncing BEFORE resolving/publishing action
            if not debouncer.should_fire(button):
                logger.debug(
                    "button_debounced",
                    button_id=button.id,
                    button_type=button.type,
                    event_type=event_type_str,
                )
                continue  # Skip action publishing, but raw event was already sent

            # Resolve action and publish
            action = _resolve_action(button, event_type_str)
            if action:
                # Always publish to button topic (for backend / WebUI)
                await mqtt_client.publish_action(
                    action=action,
                    source=event.source_id,
                    event_type=event_type_str,
                )
                # Volume commands: also publish directly to audio topic for low latency
                # (avoids extra hop via backend)
                if action in ("volume_up", "volume_down"):
                    await mqtt_client.publish_audio_command(action, {})
                logger.debug(
                    "action_triggered",
                    action=action,
                    source=event.source_id,
                    event_type=event_type_str,
                )
            else:
                logger.debug(
                    "event_no_mapping",
                    source_id=event.source_id,
                    event_type=event_type_str,
                )

        except asyncio.CancelledError:
            logger.debug("event_processor_cancelled")
            break
        except Exception as exc:
            logger.error(
                "event_processor_error",
                error=str(exc),
                exc_info=True,
            )

    logger.debug("event_processor_stopped")
