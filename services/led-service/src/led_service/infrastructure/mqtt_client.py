"""MQTT client for the LED service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds:
- the LED subscription list
- the config API (config/get, config/update, config/reload, config/response)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import structlog
from shared_lib.mqtt import BaseMQTTClient

from ..config_schema import LEDServiceConfig

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
    """MQTT client for the LED service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Callable[[str, bytes], None],
        on_config_update_callback: Callable[[LEDServiceConfig], None],
        on_config_reload_callback: Callable[[], None],
    ) -> None:
        """Initialize the MQTT client.

        Args:
            config: Application configuration.
            on_message_callback: Callback for regular MQTT messages (topic, payload).
            on_config_update_callback: Callback for config/update messages.
            on_config_reload_callback: Callback for config/reload messages.
        """
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"led-service-{config.env.minabox_device_id}",
            service_name="led",
        )
        self._config = config
        self._on_message = on_message_callback
        self._on_config_update = on_config_update_callback
        self._on_config_reload = on_config_reload_callback

        # Registered up front; the base client applies them on every connect.
        for topic in self._build_subscription_topics():
            self._subscriptions[topic] = 1

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to.

        Returns:
            List of topic strings.
        """
        device_id = self._config.env.minabox_device_id
        prefix = f"minabox/{device_id}"

        return [
            # Audio status
            f"{prefix}/audio/status",

            # RFID events
            f"{prefix}/rfid/tag-scanned",
            f"{prefix}/rfid/tag-removed",
            f"{prefix}/rfid/unknown-tag",
            # Retained presence topic: always reflects current tag state.
            # Re-subscribed after config reload to trigger broker re-delivery.
            f"{prefix}/rfid/presence",

            # System events
            f"{prefix}/system/service-started",
            f"{prefix}/system/service-error",
            f"{prefix}/system/booting",

            # Button events
            f"{prefix}/button/raw-event",

            # Backend status
            f"{prefix}/backend/unreachable",

            # Parental: usage outside allowed times
            f"{prefix}/led/usage-denied",

            # Config API
            f"{prefix}/led/config/update",
            f"{prefix}/led/config/reload",
            f"{prefix}/led/config/get",
            f"{prefix}/config/general",
        ]

    async def resubscribe_retained_topics(self) -> None:
        """Re-subscribe to retained topics to trigger broker re-delivery.

        The MQTT broker only delivers a retained message when a client
        subscribes. If the connection stays alive (e.g. after a config reload)
        no new subscribe happens and retained messages are not re-delivered.
        Calling this method forces re-delivery of all retained topics so that
        state-dependent LEDs (e.g. RFID status ring) show the correct state
        after a re-initialization.
        """
        if not self.is_connected:
            logger.warning("resubscribe_skipped_not_connected")
            return

        device_id = self._config.env.minabox_device_id
        prefix = f"minabox/{device_id}"
        for topic in (f"{prefix}/rfid/presence", f"{prefix}/audio/status"):
            await self.resubscribe(topic, qos=1)

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Dispatch an incoming message to the LED handlers."""
        if topic.endswith("/led/config/update"):
            await self._handle_config_update(payload)
        elif topic.endswith("/led/config/reload"):
            await self._handle_config_reload()
        elif topic.endswith("/led/config/get"):
            await self._handle_config_get()
        elif topic.endswith("/config/general"):
            await self.apply_general_config(payload)
        else:
            # Regular message - pass to callback
            self._on_message(topic, payload)

    async def _handle_config_update(self, payload: bytes) -> None:
        """Handle config/update message.

        Args:
            payload: The new LED configuration as JSON.
        """
        logger.debug("config_update_received")

        try:
            config_dict = json.loads(payload.decode("utf-8"))
            new_config = LEDServiceConfig.model_validate(config_dict)
            self._on_config_update(new_config)

            # Re-deliver retained topics so state-dependent LEDs recover correctly
            await self.resubscribe_retained_topics()

            await self._send_config_response(success=True, error=None)

        except Exception as exc:
            logger.error("config_update_failed", error=str(exc), exc_info=True)
            await self._send_config_response(success=False, error="invalid_config")

    async def _handle_config_reload(self) -> None:
        """Handle config/reload message."""
        logger.debug("config_reload_received")

        try:
            self._on_config_reload()

            # Re-deliver retained topics so state-dependent LEDs recover correctly
            await self.resubscribe_retained_topics()

            await self._send_config_response(success=True, error=None)
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)
            await self._send_config_response(success=False, error="reload_failed")

    async def _handle_config_get(self) -> None:
        """Handle config/get message.

        This sends the current LED configuration via config/response.
        """
        logger.debug("config_get_received")
        # For now, just acknowledge - full implementation would fetch current config
        await self._send_config_response(success=True, error=None)

    async def _send_config_response(self, success: bool, error: str | None) -> None:
        """Send a config/response message.

        Args:
            success: Whether the operation succeeded.
            error: Error code if operation failed, None otherwise.
        """
        device_id = self._config.env.minabox_device_id
        topic = f"minabox/{device_id}/led/config/response"

        payload = {
            "success": success,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.publish(topic, payload)
