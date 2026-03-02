"""MQTT client for the RFID service.

This module handles:
- Publishing RFID events (tag-scanned, tag-removed, status)
- Subscribing to command topics (cmd/set-mode)
- Connection management with automatic reconnection on broker restart
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Callable

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..exceptions import MinaboxRFIDError

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)

class MQTTClient:
    """MQTT client for the RFID service."""

    def __init__(
        self,
        config: AppConfig,
        on_set_mode_callback: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the MQTT client.

        Args:
            config: Application configuration.
            on_set_mode_callback: Callback for cmd/set-mode messages.
        """
        self._config = config
        self._on_set_mode = on_set_mode_callback

        self._client: Client | None = None
        self._running = False
        self._device_id = config.env.minabox_device_id
        self._topic_prefix = f"minabox/{self._device_id}/rfid"
        self._topics = self._build_subscription_topics()

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to."""
        return [
            f"{self._topic_prefix}/cmd/set-mode",
        ]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MqttError),
    )
    async def connect(self) -> None:
        """Connect to the MQTT broker with automatic retry."""
        logger.info(
            "mqtt_connecting",
            broker=self._config.env.mqtt_broker,
            port=self._config.env.mqtt_port,
        )

        try:
            self._client = Client(
                hostname=self._config.env.mqtt_broker,
                port=self._config.env.mqtt_port,
            )
            await self._client.__aenter__()

            for topic in self._topics:
                await self._client.subscribe(topic, qos=1)
                logger.debug("mqtt_subscribed", topic=topic)

            logger.info("mqtt_connected")

        except MqttError as exc:
            logger.error(
                "mqtt_connection_failed",
                broker=self._config.env.mqtt_broker,
                port=self._config.env.mqtt_port,
                error=str(exc),
            )
            raise

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("mqtt_disconnected")
            except Exception as exc:
                logger.warning("mqtt_disconnect_error", error=str(exc))
            finally:
                self._client = None

    async def run(self) -> None:
        """Run the MQTT client message loop with automatic reconnection on broker restart."""
        self._running = True
        logger.info("mqtt_client_running")
        reconnect_delay = 2.0
        while self._running:
            try:
                if self._client is None:
                    await self.connect()
                reconnect_delay = 2.0
                async for message in self._client.messages:
                    if not self._running:
                        break

                    topic = message.topic.value
                    payload = message.payload

                    if topic.endswith("/rfid/cmd/set-mode"):
                        self._handle_set_mode(payload)
                    else:
                        logger.warning("mqtt_unknown_topic", topic=topic)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._running:
                    raise
                logger.warning(
                    "mqtt_connection_lost_reconnecting",
                    error=str(exc),
                    exc_info=True,
                )
                await self.disconnect()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60.0)

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
        if not self._client:
            logger.warning("mqtt_publish_skipped_not_connected", topic=topic)
            return

        try:
            payload_json = json.dumps(payload)
            await self._client.publish(topic, payload_json, qos=qos, retain=retain)
            logger.debug("mqtt_published", topic=topic, qos=qos, retain=retain)
        except Exception as exc:
            logger.error(
                "mqtt_publish_failed",
                topic=topic,
                error=str(exc),
                exc_info=True,
            )

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._client is not None and self._running

    def _handle_set_mode(self, payload: bytes) -> None:
        """Handle cmd/set-mode message."""
        try:
            data = json.loads(payload.decode("utf-8"))
            mode = data.get("mode")
            if mode in ("normal", "learning"):
                logger.info("set_mode_received", mode=mode)
                if self._on_set_mode:
                    self._on_set_mode(mode)
            else:
                logger.warning("invalid_mode", mode=mode)
        except json.JSONDecodeError:
            logger.warning("invalid_command_json")
