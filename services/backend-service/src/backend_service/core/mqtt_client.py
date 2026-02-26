"""MQTT client for Backend Service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend_service.config_schema import AppConfig, BackendConfig
from backend_service.exceptions import MQTTConnectionError, MQTTPublishError

logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client with reconnection and retry logic."""

    def __init__(self, config: BackendConfig) -> None:
        """Initialize MQTT client.

        Args:
            config: Backend configuration
        """
        self.config = config
        self.client: Client | None = None
        self._connected = False
        self._running = False
        self._message_handlers: dict[str, list[Callable]] = {}
        logger.debug(
            "mqtt_client_initialized",
            broker=config.mqtt_broker,
            port=config.mqtt_port,
        )

    @retry(
        retry=retry_if_exception_type(MqttError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
    )
    async def connect(self) -> None:
        """Connect to MQTT broker with retry logic.

        Raises:
            MQTTConnectionError: If connection fails after retries
        """
        logger.debug("mqtt_connecting", broker=self.config.mqtt_broker)

        try:
            self.client = Client(
                hostname=self.config.mqtt_broker,
                port=self.config.mqtt_port,
                identifier=f"backend-{self.config.device_id}",
            )
            await self.client.__aenter__()
            self._connected = True
            logger.debug("mqtt_connected_successfully")
        except Exception as e:
            logger.error("mqtt_connection_failed", error=str(e))
            self._connected = False
            raise MQTTConnectionError(f"Failed to connect to MQTT broker: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self.client and self._connected:
            logger.debug("mqtt_disconnecting")
            try:
                await self.client.__aexit__(None, None, None)
                self._connected = False
                logger.debug("mqtt_disconnected")
            except Exception as e:
                logger.error("mqtt_disconnect_error", error=str(e))

    @property
    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._connected

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        """Publish message to MQTT topic.

        Args:
            topic: MQTT topic (e.g., 'minabox/box1/audio/play')
            payload: Message payload (will be JSON-encoded)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain message on broker

        Raises:
            MQTTPublishError: If publish fails
        """
        if not self._connected or not self.client:
            raise MQTTPublishError("MQTT client not connected")

        # Add timestamp if not present
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.now(UTC).isoformat()

        try:
            message = json.dumps(payload)
            await self.client.publish(topic, message, qos=qos, retain=retain)
            logger.debug("mqtt_published", topic=topic, payload=payload, qos=qos)
        except Exception as e:
            logger.error("mqtt_publish_failed", topic=topic, error=str(e))
            raise MQTTPublishError(f"Failed to publish to {topic}: {e}") from e

    async def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to MQTT topic with handler.

        Args:
            topic: MQTT topic to subscribe (supports wildcards +, #)
            handler: Async function to call when message received
        """
        if topic not in self._message_handlers:
            self._message_handlers[topic] = []

        self._message_handlers[topic].append(handler)
        logger.debug("mqtt_subscribed", topic=topic)

    async def _handle_message(self, topic: str, payload: str) -> None:
        """Handle incoming MQTT message.

        Args:
            topic: Message topic
            payload: Message payload (JSON string)
        """
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

    async def run(self) -> None:
        """Run the MQTT client message loop with automatic reconnection on broker restart."""
        self._running = True
        logger.debug("mqtt_listening_started")
        reconnect_delay = 2.0
        while self._running:
            try:
                if not self._connected or not self.client:
                    await self.connect()
                reconnect_delay = 2.0
                # Subscribe to all registered topics
                for topic in self._message_handlers.keys():
                    await self.client.subscribe(topic)
                    logger.debug("mqtt_topic_subscribed", topic=topic)
                # Listen for messages
                async for message in self.client.messages:
                    if not self._running:
                        break
                    await self._handle_message(message.topic.value, message.payload.decode())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._running:
                    raise
                logger.warning("mqtt_connection_lost_reconnecting", error=str(e))
                await self.disconnect()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60.0)

    async def stop(self) -> None:
        """Stop the MQTT client message loop."""
        logger.info("mqtt_client_stopping")
        self._running = False

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
