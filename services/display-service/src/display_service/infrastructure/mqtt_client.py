"""MQTT client for the display service: audio/status and config/reload.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``.
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
    """MQTT client for the display service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Callable[[str, bytes], None],
        on_config_reload_callback: Callable[[], None],
    ) -> None:
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"display-service-{config.env.minabox_device_id}",
            service_name="display",
        )
        self._config = config
        self._on_message = on_message_callback
        self._on_config_reload = on_config_reload_callback

        device_id = config.env.minabox_device_id
        prefix = f"minabox/{device_id}"
        # Registered up front; the base client applies them on every connect.
        for topic in (
            f"{prefix}/audio/status",
            f"{prefix}/audio/error",
            f"{prefix}/rfid/unknown-tag",
            f"{prefix}/rfid/tag-blocked",
            f"{prefix}/rfid/tag-scanned",
            f"{prefix}/rfid/tag-removed",
            f"{prefix}/led/usage-denied",
            f"{prefix}/system/service-error",
            f"{prefix}/display/config/reload",
            f"{prefix}/config/general",
        ):
            self._subscriptions[topic] = 1

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Dispatch an incoming message to the display handlers."""
        if topic.endswith("/display/config/reload"):
            logger.info("config_reload_received")
            try:
                self._on_config_reload()
            except Exception as exc:
                logger.error("config_reload_failed", error=str(exc), exc_info=True)
        elif topic.endswith("/config/general"):
            await self.apply_general_config(payload)
        else:
            self._on_message(topic, payload)
