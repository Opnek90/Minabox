"""MQTT client for the button service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds:
- Publishing button action events
- Publishing raw button events (optional, for debugging)
- Config API (config/get, config/update, config/reload, config/response)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import structlog
from shared_lib.mqtt import BaseMQTTClient

from ..config_schema import ButtonServiceConfig

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
    """MQTT client for the button service."""

    def __init__(
        self,
        config: AppConfig,
        on_config_update_callback: Callable[[ButtonServiceConfig], None],
        on_config_reload_callback: Callable[[], None],
    ) -> None:
        super().__init__(
            config.env.mqtt_broker,
            config.env.mqtt_port,
            identifier=f"button-service-{config.env.minabox_device_id}",
            service_name="button",
        )
        self._config = config
        self._on_config_update = on_config_update_callback
        self._on_config_reload = on_config_reload_callback
        self._device_id = config.env.minabox_device_id

        # Build topic prefixes via get_mqtt_topic() for consistency (issue #16)
        self._topic_prefix = config.get_mqtt_topic("button", "").rstrip("/")
        self._audio_topic_prefix = config.get_mqtt_topic("audio", "").rstrip("/")

        # Registered up front; the base client applies them on every connect.
        for topic in self._build_subscription_topics():
            self._subscriptions[topic] = 1

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to (issue #16)."""
        return [
            self._config.get_mqtt_topic("button", "config/update"),
            self._config.get_mqtt_topic("button", "config/reload"),
            self._config.get_mqtt_topic("button", "config/get"),
            self._config.get_mqtt_topic("config", "general"),
        ]

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Dispatch an incoming message to the button handlers."""
        if topic.endswith("/button/config/update"):
            await self._handle_config_update(payload)
        elif topic.endswith("/button/config/reload"):
            await self._handle_config_reload()
        elif topic.endswith("/button/config/get"):
            await self._handle_config_get()
        elif topic.endswith("/config/general"):
            await self.apply_general_config(payload)
        else:
            logger.warning("mqtt_unknown_topic", topic=topic)

    async def publish_action(self, action: str, source: str, event_type: str) -> None:
        """Publish a button action event."""
        topic = f"{self._topic_prefix}/{action.replace('_', '-')}"
        payload = {
            "source": source,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(topic, payload, qos=1, retain=False)
        logger.debug(
            "action_published",
            action=action,
            source=source,
            event_type=event_type,
            topic=topic,
        )

    async def publish_audio_command(self, action: str, payload: dict | None = None) -> None:
        """Publish directly to audio service topic (e.g. volume-up, volume-down)."""
        topic = f"{self._audio_topic_prefix}/{action.replace('_', '-')}"
        await self.publish(topic, payload or {}, qos=0, retain=False)
        logger.debug("audio_command_published", action=action, topic=topic)

    async def publish_raw_event(
        self,
        button_id: str,
        name: str,
        button_type: str,
        event_type: str,
    ) -> None:
        """Publish a raw button event."""
        topic = f"{self._topic_prefix}/raw-event"
        payload = {
            "button_id": button_id,
            "name": name,
            "type": button_type,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(topic, payload, qos=1, retain=False)
        logger.debug("raw_event_published", button_id=button_id, event_type=event_type)

    async def _handle_config_update(self, payload: bytes) -> None:
        """Handle config/update message."""
        logger.debug("config_update_received")
        try:
            config_dict = json.loads(payload.decode("utf-8"))
            new_config = ButtonServiceConfig.model_validate(config_dict)
            self._on_config_update(new_config)
            await self._send_config_response(success=True, error=None)
        except Exception as exc:
            logger.error("config_update_failed", error=str(exc), exc_info=True)
            await self._send_config_response(success=False, error="invalid_config")

    async def _handle_config_reload(self) -> None:
        """Handle config/reload message."""
        logger.debug("config_reload_received")
        try:
            self._on_config_reload()
            await self._send_config_response(success=True, error=None)
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)
            await self._send_config_response(success=False, error="reload_failed")

    async def _handle_config_get(self) -> None:
        """Handle config/get message."""
        logger.debug("config_get_received")
        await self._send_config_response(success=True, error=None)

    async def _send_config_response(self, success: bool, error: str | None) -> None:
        """Send a config/response message."""
        topic = f"{self._topic_prefix}/config/response"
        payload = {
            "success": success,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(topic, payload)
