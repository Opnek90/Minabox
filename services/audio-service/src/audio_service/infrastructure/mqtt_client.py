"""MQTT client for the Audio Service.

Connection handling, reconnection and status replay live in
``shared_lib.mqtt.BaseMQTTClient``; this module only adds the audio-specific
wiring.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog
from shared_lib.mqtt import BaseMQTTClient

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
    """MQTT client for the audio service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Callable | None = None,
    ) -> None:
        """Initialize MQTT client.

        Args:
            config: Application configuration.
            on_message_callback: Async callback for incoming messages (topic, payload_str).
        """
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"audio-service-{config.env.minabox_device_id}",
            service_name="audio",
        )
        self._config = config
        self._on_message = on_message_callback

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Decode and forward the message to the audio handler."""
        if self._on_message is None:
            return
        await self._on_message(topic, payload.decode("utf-8"))

    def get_topic(self, action: str) -> str:
        """Generate MQTT topic for audio domain."""
        return self._config.get_mqtt_topic("audio", action)
