"""MQTT client for the button service.

This module handles:
- Publishing button action events
- Publishing raw button events (optional, for debugging)
- Config API (config/get, config/update, config/reload, config/response)
- Connection management with automatic reconnection
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import structlog
from aiomqtt import Client, MqttError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from shared_lib.logging import setup_structlog

from ..config_schema import ButtonServiceConfig
from ..exceptions import MinaboxButtonError

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)


class MQTTClient:
    """MQTT client for the button service."""

    def __init__(
        self,
        config: AppConfig,
        on_config_update_callback: Callable[[ButtonServiceConfig], None],
        on_config_reload_callback: Callable[[], None],
    ) -> None:
        self._config = config
        self._on_config_update = on_config_update_callback
        self._on_config_reload = on_config_reload_callback

        self._client: Client | None = None
        self._running = False
        self._device_id = config.env.minabox_device_id

        # Build topic prefixes via get_mqtt_topic() for consistency (issue #16)
        self._topic_prefix = config.get_mqtt_topic("button", "").rstrip("/")
        self._audio_topic_prefix = config.get_mqtt_topic("audio", "").rstrip("/")

        self._topics = self._build_subscription_topics()

    @property
    def is_connected(self) -> bool:
        """True if MQTT client is connected and running."""
        return self._client is not None and self._running

    def _build_subscription_topics(self) -> list[str]:
        """Build list of MQTT topics to subscribe to (issue #16)."""
        return [
            self._config.get_mqtt_topic("button", "config/update"),
            self._config.get_mqtt_topic("button", "config/reload"),
            self._config.get_mqtt_topic("button", "config/get"),
            self._config.get_mqtt_topic("config", "general"),
        ]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MqttError),
    )
    async def connect(self) -> None:
        """Connect to the MQTT broker with automatic retry."""
        logger.debug(
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

            logger.debug("mqtt_connected")

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
                logger.debug("mqtt_disconnected")
            except Exception as exc:
                logger.warning("mqtt_disconnect_error", error=str(exc))
            finally:
                self._client = None

    async def run(self) -> None:
        """Run the MQTT client message loop with automatic reconnection."""
        self._running = True
        logger.debug("mqtt_client_running")
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

                    if topic.endswith("/button/config/update"):
                        await self._handle_config_update(payload)
                    elif topic.endswith("/button/config/reload"):
                        await self._handle_config_reload()
                    elif topic.endswith("/button/config/get"):
                        await self._handle_config_get()
                    elif topic.endswith("/config/general"):
                        try:
                            data = json.loads(payload.decode("utf-8"))
                            level = (data.get("log_level") or "INFO").upper()
                            if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                                setup_structlog(level)
                                logger.info("log_level_applied", log_level=level)
                            else:
                                logger.warning("invalid_log_level", log_level=level)
                        except (json.JSONDecodeError, TypeError) as exc:
                            logger.warning("config_general_parse_failed", error=str(exc))
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
        logger.debug("mqtt_client_stopping")
        self._running = False

    async def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        """Publish a message to an MQTT topic."""
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

    async def publish_action(
        self,
        action: str,
        source: str,
        event_type: str,
    ) -> None:
        """Publish a button action event."""
        topic = f"{self._topic_prefix}/{action.replace('_', '-')}"
        payload = {
            "source": source,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(topic, payload, qos=1, retain=False)
        logger.debug("action_published", action=action, source=source, event_type=event_type, topic=topic)

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
