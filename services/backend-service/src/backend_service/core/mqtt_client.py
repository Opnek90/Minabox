"""MQTT client for Backend Service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds the backend's
handler-registry dispatch (with topic wildcards) and its publish contract:
unlike the device services, a failed backend publish is surfaced to the HTTP
caller as :class:`MQTTPublishError` rather than swallowed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from shared_lib.mqtt import BaseMQTTClient

from backend_service.config_schema import BackendConfig
from backend_service.core.debug_export.runtime_buffers import record_mqtt
from backend_service.exceptions import MQTTPublishError

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
    """MQTT client with reconnection and retry logic."""

    def __init__(self, config: BackendConfig) -> None:
        """Initialize MQTT client.

        Args:
            config: Backend configuration
        """
        super().__init__(
            config.mqtt_broker,
            config.mqtt_port,
            identifier=f"backend-{config.device_id}",
            service_name="backend",
        )
        self.config = config
        self._message_handlers: dict[str, list[Callable]] = {}
        logger.debug(
            "mqtt_client_initialized",
            broker=config.mqtt_broker,
            port=config.mqtt_port,
        )

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def subscribe(self, topic: str, handler: Callable | None = None, qos: int = 1) -> None:
        """Subscribe to MQTT topic with handler.

        The topic is remembered by the base client and re-applied on every
        reconnect, so a broker restart does not leave the backend deaf.

        Args:
            topic: MQTT topic to subscribe (supports wildcards +, #)
            handler: Async function to call when message received
            qos: Quality of Service level
        """
        if handler is not None:
            self._message_handlers.setdefault(topic, []).append(handler)
        await super().subscribe(topic, qos=qos)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = False,
        *,
        remember: bool = False,
    ) -> bool:
        """Publish message to MQTT topic.

        Args:
            topic: MQTT topic (e.g., 'minabox/box1/audio/play')
            payload: Message payload (will be JSON-encoded)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain message on broker
            remember: Re-publish this payload after a reconnect

        Raises:
            MQTTPublishError: If publish fails
        """
        # Add timestamp if not present
        if isinstance(payload, dict) and "timestamp" not in payload:
            payload["timestamp"] = datetime.now(UTC).isoformat()

        delivered = await super().publish(
            topic, payload, qos=qos, retain=retain, remember=remember
        )
        if not delivered:
            raise MQTTPublishError(f"Failed to publish to {topic}: broker not connected")

        record_mqtt("out", topic, json.dumps(payload))
        logger.debug("mqtt_published", topic=topic, payload=payload, qos=qos)
        return True

    async def publish_state(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = True,
    ) -> bool:
        """Publish state that should survive a broker restart, without raising.

        Used for retained announcements made during startup, which must not be
        able to fail the boot when the broker is briefly away.
        """
        if isinstance(payload, dict) and "timestamp" not in payload:
            payload["timestamp"] = datetime.now(UTC).isoformat()
        delivered = await BaseMQTTClient.publish(
            self, topic, payload, qos=qos, retain=retain, remember=True
        )
        if delivered:
            record_mqtt("out", topic, json.dumps(payload))
        return delivered

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Decode and dispatch to the registered handlers."""
        await self._handle_message(topic, payload.decode())

    async def _handle_message(self, topic: str, payload: str) -> None:
        """Handle incoming MQTT message.

        Args:
            topic: Message topic
            payload: Message payload (JSON string)
        """
        record_mqtt("in", topic, payload)
        try:
            data = json.loads(payload)
            logger.debug("mqtt_message_received", topic=topic, data=data)

            # Find matching handlers (exact match or wildcard)
            for pattern, handlers in self._message_handlers.items():
                if self._topic_matches(topic, pattern):
                    for handler in handlers:
                        try:
                            await handler(topic, data)
                        except Exception as e:
                            logger.error(
                                "mqtt_handler_error",
                                topic=topic,
                                pattern=pattern,
                                error=str(e),
                            )
        except json.JSONDecodeError as e:
            logger.error("mqtt_invalid_json", topic=topic, error=str(e))

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if topic matches pattern (supports wildcards).

        Args:
            topic: Actual topic (e.g., 'minabox/box1/rfid/tag-scanned')
            pattern: Pattern with wildcards (e.g., 'minabox/+/rfid/#')

        Returns:
            True if topic matches pattern
        """
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        if len(pattern_parts) > len(topic_parts):
            return False

        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == "#":
                # Multi-level wildcard - matches rest
                return True
            elif pattern_part == "+":
                # Single-level wildcard
                continue
            elif i >= len(topic_parts) or pattern_part != topic_parts[i]:
                return False

        return len(topic_parts) == len(pattern_parts)

    # Backward-compatible aliases
    async def start_listening(self) -> None:
        """Alias for run()."""
        await self.run()

    async def stop_listening(self) -> None:
        """Alias for stop()."""
        await self.stop()

    # ========================================================================
    # Convenience methods for common topics
    # ========================================================================

    async def publish_audio_command(self, action: str, payload: dict[str, Any]) -> None:
        """Publish audio command.

        Args:
            action: Action name (e.g., 'play', 'pause', 'stop')
            payload: Command payload
        """
        topic = self.config.get_mqtt_topic("audio", action)
        await self.publish(topic, payload, qos=1)

    async def publish_rfid_command(self, action: str, payload: dict[str, Any]) -> None:
        """Publish RFID command.

        Args:
            action: Action name (e.g., 'cmd/set-mode')
            payload: Command payload
        """
        topic = self.config.get_mqtt_topic("rfid", action)
        await self.publish(topic, payload, qos=1)

    async def publish_config_update(
        self,
        service: str,
        config_data: dict[str, Any],
    ) -> None:
        """Publish config update to service.

        Args:
            service: Service name (e.g., 'button', 'led')
            config_data: Configuration data
        """
        topic = self.config.get_mqtt_topic(service, "config/update")
        await self.publish(topic, config_data, qos=1)
