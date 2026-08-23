"""MQTT client for the RFID service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds:
- the RFID subscription list
- the cmd/set-mode command handler
- the last will that clears the retained tag presence if this process dies
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, get_args

import structlog
from shared_lib.mqtt import BaseMQTTClient

from ..models import TagPresenceEvent

if TYPE_CHECKING:
    from ..config_schema import AppConfig
    from ..core.rfid_manager import Mode

logger = structlog.get_logger(__name__)


def _valid_modes() -> tuple[str, ...]:
    """Accepted values of the set-mode command, derived from the Mode type."""
    from ..core.rfid_manager import Mode

    return get_args(Mode)


class MQTTClient(BaseMQTTClient):
    """MQTT client for the RFID service."""

    def __init__(
        self,
        config: AppConfig,
        on_set_mode_callback: Callable[[Mode], None] | None = None,
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

        self._register_presence_will()

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to."""
        return [
            f"{self._topic_prefix}/cmd/set-mode",
            f"minabox/{self._device_id}/config/general",
        ]

    def _register_presence_will(self) -> None:
        """Let the broker clear the retained presence if this process dies.

        Presence is retained, so a crashed service would leave subscribers
        believing a tag is still on the reader forever. The timestamp in the
        will payload is the one from connection time -- MQTT fixes the payload
        when the session opens -- so consumers must read ``tag_present``, not
        the age of the message.
        """
        reader_id = (
            f"{self._config.rfid.reader.reader_type}_"
            f"{self._config.rfid.reader.interface}"
        )
        event = TagPresenceEvent(
            tag_present=False,
            tag_id=None,
            reader_id=reader_id,
        )
        self.set_will(
            f"{self._topic_prefix}/presence",
            event.model_dump(),
            qos=1,
            retain=True,
        )

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
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("invalid_command_json", error=str(exc))
            return

        mode = data.get("mode") if isinstance(data, dict) else None
        if mode not in _valid_modes():
            logger.warning("invalid_mode", mode=mode)
            return

        logger.info("set_mode_received", mode=mode)
        if self._on_set_mode:
            self._on_set_mode(mode)
