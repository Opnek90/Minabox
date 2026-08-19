"""MQTT client for the RFID service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds:
- the RFID subscription list
- the cmd/set-mode command handler
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

import structlog
from shared_lib.mqtt import BaseMQTTClient

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
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
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"rfid-service-{config.env.minabox_device_id}",
            service_name="rfid",
        )
        self._config = config
        self._on_set_mode = on_set_mode_callback
        self._device_id = config.env.minabox_device_id
        self._topic_prefix = f"minabox/{self._device_id}/rfid"

        # Registered up front; the base client applies them on every connect.
        for topic in self._build_subscription_topics():
            self._subscriptions[topic] = 1

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to."""
        return [
            f"{self._topic_prefix}/cmd/set-mode",
            f"minabox/{self._device_id}/config/general",
        ]

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Dispatch an incoming message to the RFID handlers."""
        if topic.endswith("/rfid/cmd/set-mode"):
            self._handle_set_mode(payload)
        elif topic.endswith("/config/general"):
            await self.apply_general_config(payload)
        else:
            logger.warning("mqtt_unknown_topic", topic=topic)

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
