"""MQTT client for the Audio Service.

Connection handling, reconnection and status replay live in
``shared_lib.mqtt.BaseMQTTClient``; this module only adds the audio-specific
wiring.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from shared_lib.mqtt import BaseMQTTClient

from .audio_backend import PlaybackState

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
            on_message_callback: Async callback for incoming messages
                (topic, payload_str).
        """
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"audio-service-{config.env.minabox_device_id}",
            service_name="audio",
        )
        self._config = config
        self._on_message = on_message_callback
        self._register_status_will()

    def _register_status_will(self) -> None:
        """Let the broker publish a stopped status if this process dies.

        The status topic is retained, so a container that is killed without a
        clean disconnect would leave every subscriber - LED ring, OLED, WebUI -
        showing "playing" forever, with no sound to go with it. The will makes
        the broker correct that on our behalf.

        MQTT fixes the payload when the session opens, so the timestamp here is
        the connection time, not the time of death. Consumers must read
        ``state``, not the age of the message.
        """
        self.set_will(
            self._config.get_mqtt_topic("audio", "status"),
            {
                "state": PlaybackState.STOPPED.value,
                "track_id": None,
                "source_type": None,
                "source_uri": None,
                "position_ms": 0,
                "duration_ms": None,
                "volume": 0,
                "muted": False,
                "multiple_output_devices": False,
                "bluetooth_sink_available": False,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            qos=1,
            retain=True,
        )

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Decode and forward the message to the audio handler."""
        if self._on_message is None:
            return
        await self._on_message(topic, payload.decode("utf-8"))

    def get_topic(self, action: str) -> str:
        """Generate MQTT topic for audio domain."""
        return self._config.get_mqtt_topic("audio", action)
