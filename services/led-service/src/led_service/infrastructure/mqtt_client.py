"""MQTT client for the LED service.

Connection lifecycle, reconnection and status replay come from
``shared_lib.mqtt.BaseMQTTClient``. This module adds:
- the LED subscription list
- the config API (config/reload, config/response)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from shared_lib.mqtt import BaseMQTTClient

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient(BaseMQTTClient):
    """MQTT client for the LED service."""

    def __init__(
        self,
        config: AppConfig,
        on_message_callback: Callable[[str, bytes], Awaitable[None]],
        on_config_reload_callback: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize the MQTT client.

        Both callbacks are awaited rather than dispatched into their own task.
        That is what makes the ordering deterministic: the base client's
        receive loop hands over one message at a time, so states are applied in
        the order the broker delivered them.

        Args:
            config: Application configuration.
            on_message_callback: Callback for regular MQTT messages (topic, payload).
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
        self._on_config_reload = on_config_reload_callback

        # Registered up front; the base client applies them on every connect.
        for topic in self._build_subscription_topics():
            self._subscriptions[topic] = 1

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to.

        Must cover every topic StateManager knows a rule for -- a rule without
        a subscription is a logical state the WebUI offers and that never
        fires. tests/test_mqtt_subscriptions.py holds the two lists together.

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
            # A blocked tag was published by the backend and derived by the
            # state manager, but never subscribed to -- so a binding on
            # rfid_tag_blocked silently did nothing.
            f"{prefix}/rfid/tag-blocked",
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
            f"{prefix}/led/config/reload",
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
        if topic.endswith("/led/config/reload"):
            await self._handle_config_reload()
        elif topic.endswith("/config/general"):
            await self.apply_general_config(payload)
        else:
            await self._on_message(topic, payload)

    async def _handle_config_reload(self) -> None:
        """Re-read leds.json and report the real outcome.

        The reload is awaited before the response goes out. It used to be
        dispatched into a background task while success was reported straight
        away, so a config the service could not apply still looked like it had
        been saved.
        """
        logger.debug("config_reload_received")

        try:
            await self._on_config_reload()
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc), exc_info=True)
            await self._send_config_response(success=False, error="reload_failed")
            return

        # Re-deliver retained topics so state-dependent LEDs recover correctly
        await self.resubscribe_retained_topics()
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
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await self.publish(topic, payload)
