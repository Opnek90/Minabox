"""Event processor: consume raw events from FIFO queue, apply mapping, publish to MQTT."""

from __future__ import annotations

import asyncio
from typing import Callable

import structlog

from ..config_schema import ButtonConfig, ButtonServiceConfig
from ..infrastructure.mqtt_client import MQTTClient
from .events import RawButtonEvent

logger = structlog.get_logger(__name__)

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
    publish_raw_events: bool = False,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Consume raw events from queue, map to actions, publish to MQTT.
    
    Runs until shutdown_event is set (if provided) or the queue is closed.
    """
    logger.debug("event_processor_started", publish_raw_events=publish_raw_events)
    
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
            
            # Optional: publish raw event for debugging
            if publish_raw_events:
                await mqtt_client.publish_raw_event(
                    button_id=button.id,
                    name=button.name,
                    button_type=button.type,
                    event_type=event_type_str,
                )
            
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
