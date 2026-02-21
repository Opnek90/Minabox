"""MQTT client for the display service: audio/status and config/reload."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

import structlog
from aiomqtt import Client, MqttError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from .config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client for the display service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Callable[[str, bytes], None],
        on_config_reload_callback: Callable[[], None],
    ) -> None:
        self._config = config
        self._on_message = on_message_callback
        self._on_config_reload = on_config_reload_callback
        self._client: Client | None = None
        self._running = False
        device_id = config.env.minabox_device_id
        prefix = f"minabox/{device_id}"
        self._topics = [
            f"{prefix}/audio/status",
            f"{prefix}/display/config/reload",
        ]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MqttError),
    )
    async def connect(self) -> None:
        """Connect to the MQTT broker."""
        logger.info(
            "mqtt_connecting",
            broker=self._config.env.mqtt_broker,
            port=self._config.env.mqtt_port,
        )
        self._client = Client(
            hostname=self._config.env.mqtt_broker,
            port=self._config.env.mqtt_port,
        )
        await self._client.__aenter__()
        for topic in self._topics:
            await self._client.subscribe(topic, qos=1)
            logger.debug("mqtt_subscribed", topic=topic)
        logger.info("mqtt_connected")

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
        """Run the MQTT message loop."""
        if not self._client:
            raise RuntimeError("MQTT client not connected")
        self._running = True
        logger.info("mqtt_client_running")
        try:
            async for message in self._client.messages:
                if not self._running:
                    break
                topic = message.topic.value
                payload = message.payload
                if topic.endswith("/display/config/reload"):
                    logger.info("config_reload_received")
                    try:
                        self._on_config_reload()
                    except Exception as exc:
                        logger.error("config_reload_failed", error=str(exc), exc_info=True)
                else:
                    try:
                        self._on_message(topic, payload)
                    except Exception as exc:
                        logger.error(
                            "message_callback_error",
                            topic=topic,
                            error=str(exc),
                            exc_info=True,
                        )
        except Exception as exc:
            if self._running:
                logger.error("mqtt_loop_error", error=str(exc), exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop the MQTT message loop."""
        logger.info("mqtt_client_stopping")
        self._running = False

    async def publish(self, topic: str, payload: dict) -> None:
        """Publish a message to an MQTT topic."""
        if not self._client:
            logger.warning("mqtt_publish_skipped_not_connected", topic=topic)
            return
        try:
            payload_json = json.dumps(payload)
            await self._client.publish(topic, payload_json, qos=1)
            logger.debug("mqtt_published", topic=topic)
        except Exception as exc:
            logger.error("mqtt_publish_failed", topic=topic, error=str(exc), exc_info=True)
