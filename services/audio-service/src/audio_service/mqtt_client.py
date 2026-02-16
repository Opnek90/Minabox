"""MQTT client for the Audio Service.

Handles connection, publishing, and subscribing to MQTT topics
following the Minabox topic schema.
"""

import asyncio
from collections.abc import Callable

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config_schema import ServiceConfig
from .exceptions import MQTTConnectionError, MQTTPublishError

logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client wrapper with reconnection logic.

    Provides simplified interface for publishing and subscribing
    to Minabox MQTT topics with automatic reconnection.
    """

    def __init__(self, config: ServiceConfig) -> None:
        """Initialize MQTT client.

        Args:
            config: Service configuration containing MQTT settings
        """
        self._config = config
        self._client: Client | None = None
        self._connected = False
        self._message_callbacks: dict[str, list[Callable]] = {}

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MQTTConnectionError),
    )
    async def connect(self) -> None:
        """Connect to MQTT broker with retry logic.

        Raises:
            MQTTConnectionError: If connection fails after retries
        """
        broker = self._config.global_config.mqtt_broker
        port = self._config.global_config.mqtt_port
        device_id = self._config.global_config.minabox_device_id

        logger.info(
            "mqtt_connecting",
            broker=broker,
            port=port,
        )

        try:
            # FIXED: aiomqtt 2.4.0+ API - identifier in constructor
            self._client = Client(
                hostname=broker,
                port=port,
                identifier=f"audio-service-{device_id}",
            )

            # Enter context manager (establishes connection)
            await self._client.__aenter__()
            self._connected = True

            logger.info(
                "mqtt_connected",
                broker=broker,
                port=port,
            )

        except MqttError as e:
            logger.error(
                "mqtt_connection_failed",
                broker=broker,
                port=port,
                error=str(e),
            )
            raise MQTTConnectionError(
                f"Failed to connect to MQTT broker {broker}:{port}"
            ) from e

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker gracefully."""
        if self._client is not None:
            logger.info("mqtt_disconnecting")
            try:
                await self._client.__aexit__(None, None, None)
                self._connected = False
                logger.info("mqtt_disconnected")
            except Exception as e:
                logger.warning("mqtt_disconnect_error", error=str(e))

    async def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        """Publish message to MQTT topic.

        Args:
            topic: MQTT topic to publish to
            payload: Message payload (JSON string)
            qos: Quality of Service (0, 1, or 2). Default is 1.
            retain: Whether to retain the message. Default is False.

        Raises:
            MQTTPublishError: If publishing fails
        """
        if not self._connected or self._client is None:
            raise MQTTPublishError("MQTT client not connected")

        try:
            await self._client.publish(
                topic=topic,
                payload=payload,
                qos=qos,
                retain=retain,
            )

            logger.debug(
                "mqtt_published",
                topic=topic,
                payload_length=len(payload),
                qos=qos,
                retain=retain,
            )

        except MqttError as e:
            logger.error(
                "mqtt_publish_failed",
                topic=topic,
                error=str(e),
            )
            raise MQTTPublishError(f"Failed to publish to {topic}") from e

    async def subscribe(self, topic: str) -> None:
        """Subscribe to MQTT topic.

        Args:
            topic: MQTT topic pattern to subscribe to

        Raises:
            MQTTConnectionError: If not connected
        """
        if not self._connected or self._client is None:
            raise MQTTConnectionError("MQTT client not connected")

        try:
            await self._client.subscribe(topic)
            logger.info("mqtt_subscribed", topic=topic)

        except MqttError as e:
            logger.error(
                "mqtt_subscribe_failed",
                topic=topic,
                error=str(e),
            )
            raise MQTTConnectionError(f"Failed to subscribe to {topic}") from e

    async def listen(
        self,
        message_handler: Callable[[str, str], None],
    ) -> None:
        """Listen for incoming MQTT messages.

        Args:
            message_handler: Async callback function(topic, payload)

        Raises:
            MQTTConnectionError: If not connected
        """
        if not self._connected or self._client is None:
            raise MQTTConnectionError("MQTT client not connected")

        logger.info("mqtt_listen_started")

        try:
            async for message in self._client.messages:
                topic = message.topic.value
                payload = message.payload.decode("utf-8")

                logger.debug(
                    "mqtt_message_received",
                    topic=topic,
                    payload_length=len(payload),
                )

                try:
                    await message_handler(topic, payload)
                except Exception as e:
                    logger.error(
                        "mqtt_message_handler_error",
                        topic=topic,
                        error=str(e),
                    )

        except asyncio.CancelledError:
            logger.info("mqtt_listen_cancelled")
            raise
        except Exception as e:
            logger.error("mqtt_listen_error", error=str(e))
            raise

    def is_connected(self) -> bool:
        """Check if MQTT client is connected.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    def get_topic(self, action: str) -> str:
        """Generate MQTT topic for audio domain.

        Args:
            action: Action/event name (e.g., 'play', 'status')

        Returns:
            Formatted MQTT topic
        """
        return self._config.get_mqtt_topic("audio", action)
