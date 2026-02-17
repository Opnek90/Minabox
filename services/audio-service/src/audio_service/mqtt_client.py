"""MQTT client for the Audio Service.

Handles connection, publishing, and subscribing to MQTT topics
following the Minabox topic schema.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .exceptions import MQTTConnectionError, MQTTPublishError


if TYPE_CHECKING:
    from .config_schema import AppConfig


logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client for the audio service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Optional[Callable] = None,
    ) -> None:
        """Initialize MQTT client.

        Args:
            config: Application configuration.
            on_message_callback: Async callback for incoming messages (topic, payload_str).
        """
        self._config = config
        self._on_message = on_message_callback
        self._client: Optional[Client] = None
        self._running = False

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MqttError),
    )
    async def connect(self) -> None:
        """Connect to MQTT broker with retry logic."""
        broker = self._config.env.mqtt_broker
        port = self._config.env.mqtt_port
        device_id = self._config.env.minabox_device_id

        logger.info("mqtt_connecting", broker=broker, port=port)

        try:
            self._client = Client(
                hostname=broker,
                port=port,
                identifier=f"audio-service-{device_id}",
            )
            await self._client.__aenter__()
            logger.info("mqtt_connected", broker=broker, port=port)

        except MqttError as exc:
            logger.error(
                "mqtt_connection_failed",
                broker=broker,
                port=port,
                error=str(exc),
            )
            raise

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker gracefully."""
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("mqtt_disconnected")
            except Exception as exc:
                logger.warning("mqtt_disconnect_error", error=str(exc))
            finally:
                self._client = None

    async def subscribe(self, topic: str) -> None:
        """Subscribe to MQTT topic."""
        if self._client is None:
            raise MQTTConnectionError("MQTT client not connected")

        try:
            await self._client.subscribe(topic)
            logger.info("mqtt_subscribed", topic=topic)
        except MqttError as exc:
            logger.error("mqtt_subscribe_failed", topic=topic, error=str(exc))
            raise MQTTConnectionError(f"Failed to subscribe to {topic}") from exc

    async def run(self) -> None:
        """Run the MQTT client message loop.

        This method processes incoming MQTT messages until stopped.
        """
        if self._client is None:
            raise MQTTConnectionError("MQTT client not connected")

        self._running = True
        logger.info("mqtt_client_running")

        try:
            async for message in self._client.messages:
                if not self._running:
                    break

                topic = message.topic.value
                payload = message.payload.decode("utf-8")

                logger.debug(
                    "mqtt_message_received",
                    topic=topic,
                    payload_length=len(payload),
                )

                if self._on_message:
                    try:
                        await self._on_message(topic, payload)
                    except Exception as exc:
                        logger.error(
                            "mqtt_message_handler_error",
                            topic=topic,
                            error=str(exc),
                        )
        except asyncio.CancelledError:
            logger.info("mqtt_run_cancelled")
            raise
        except Exception as exc:
            if self._running:
                logger.error("mqtt_loop_error", error=str(exc))
                raise

    async def stop(self) -> None:
        """Stop the MQTT client message loop."""
        logger.info("mqtt_client_stopping")
        self._running = False

    async def publish(
        self, topic: str, payload: dict, qos: int = 1, retain: bool = False
    ) -> None:
        """Publish a message to an MQTT topic.

        Args:
            topic: The MQTT topic.
            payload: The message payload (will be JSON-serialized).
            qos: Quality of Service level (default: 1).
            retain: Whether to retain the message (default: False).
        """
        if self._client is None:
            logger.warning("mqtt_publish_skipped_not_connected", topic=topic)
            return

        try:
            payload_json = json.dumps(payload)
            await self._client.publish(
                topic=topic, payload=payload_json, qos=qos, retain=retain,
            )
            logger.debug("mqtt_published", topic=topic, qos=qos, retain=retain)
        except MqttError as exc:
            logger.error("mqtt_publish_failed", topic=topic, error=str(exc))
            raise MQTTPublishError(f"Failed to publish to {topic}") from exc

    @property
    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._client is not None and self._running

    def get_topic(self, action: str) -> str:
        """Generate MQTT topic for audio domain."""
        return self._config.get_mqtt_topic("audio", action)
