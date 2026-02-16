"""MQTT client for RFID service with automatic reconnection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from .config_schema import ServiceConfig

logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client wrapper with automatic reconnection and topic helpers.

    Handles connection lifecycle, publishing, and subscribing with retry logic.
    """

    def __init__(self, config: ServiceConfig) -> None:
        """Initialize MQTT client.

        Parameters
        ----------
        config:
            Service configuration containing MQTT broker details and device ID.
        """
        self._config = config
        self._client: Client | None = None
        self._connected = False

    @retry(
        retry=retry_if_exception_type(MqttError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    async def connect(self) -> None:
        """Connect to MQTT broker with exponential backoff retry."""
        logger.info(
            "mqtt_connecting",
            broker=self._config.mqtt_broker,
            port=self._config.mqtt_port,
        )

        self._client = Client(
            hostname=self._config.mqtt_broker,
            port=self._config.mqtt_port,
        )
        await self._client.__aenter__()
        self._connected = True

        logger.info(
            "mqtt_connected",
            broker=self._config.mqtt_broker,
            port=self._config.mqtt_port,
        )

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._connected = False
            logger.info("mqtt_disconnected")

    async def publish(
        self,
        topic_suffix: str,
        payload: str,
        *,
        retain: bool = False,
        qos: int = 1,
    ) -> None:
        """Publish a message to an MQTT topic.

        Parameters
        ----------
        topic_suffix:
            Topic suffix (e.g., "rfid/tag-scanned").
            Full topic will be: minabox/{device_id}/{topic_suffix}
        payload:
            JSON payload as string.
        retain:
            Whether to set the retain flag (use for status topics).
        qos:
            Quality of Service level (0, 1, or 2).

        Raises
        ------
        MqttError
            If publishing fails.
        """
        if not self._connected or self._client is None:
            logger.warning("mqtt_publish_skipped_not_connected", topic=topic_suffix)
            return

        full_topic = f"minabox/{self._config.device_id}/{topic_suffix}"

        try:
            await self._client.publish(
                full_topic,
                payload=payload,
                qos=qos,
                retain=retain,
            )
            logger.debug(
                "mqtt_published",
                topic=full_topic,
                retain=retain,
                qos=qos,
                payload_length=len(payload),
            )
        except MqttError as exc:
            logger.error(
                "mqtt_publish_failed",
                topic=full_topic,
                error=str(exc),
            )
            raise

    async def subscribe(self, topic_suffix: str) -> None:
        """Subscribe to an MQTT topic.

        Parameters
        ----------
        topic_suffix:
            Topic suffix (e.g., "rfid/cmd/set-mode").
            Full topic will be: minabox/{device_id}/{topic_suffix}
        """
        if not self._connected or self._client is None:
            logger.warning("mqtt_subscribe_skipped_not_connected", topic=topic_suffix)
            return

        full_topic = f"minabox/{self._config.device_id}/{topic_suffix}"

        try:
            await self._client.subscribe(full_topic)
            logger.info("mqtt_subscribed", topic=full_topic)
        except MqttError as exc:
            logger.error(
                "mqtt_subscribe_failed",
                topic=full_topic,
                error=str(exc),
            )
            raise

    async def messages(self):
        """Iterate over incoming MQTT messages.

        Yields
        ------
        Message
            aiomqtt Message objects.
        """
        if not self._connected or self._client is None:
            logger.warning("mqtt_messages_not_connected")
            return

        async for message in self._client.messages:
            yield message

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connected
