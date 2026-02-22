"""MQTT client for the LED service.

This module handles:
- Subscribing to relevant MQTT topics
- Processing incoming messages
- Config API (config/get, config/update, config/reload, config/response)
- Connection management with automatic reconnection
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Callable

import structlog
from aiomqtt import Client, MqttError
from datetime import datetime, timezone
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config_schema import LEDServiceConfig
from .exceptions import MinaboxLEDError

if TYPE_CHECKING:
    from .config import AppConfig

logger = structlog.get_logger(__name__)

class MQTTClient:
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
        self._config = config
        self._on_message = on_message_callback
        self._on_config_update = on_config_update_callback
        self._on_config_reload = on_config_reload_callback
        
        self._client: Client | None = None
        self._running = False
        self._topics = self._build_subscription_topics()

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
            
            # System events
            f"{prefix}/system/service-started",
            f"{prefix}/system/service-error",
            f"{prefix}/system/booting",
            
            # Button events
            f"{prefix}/button/raw-event",
            
            # Backend status
            f"{prefix}/backend/unreachable",
            
            # Config API
            f"{prefix}/led/config/update",
            f"{prefix}/led/config/reload",
            f"{prefix}/led/config/get",
        ]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(MqttError),
    )
    async def connect(self) -> None:
        """Connect to the MQTT broker with automatic retry."""
        logger.info(
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
            
            # Subscribe to all topics
            for topic in self._topics:
                await self._client.subscribe(topic, qos=1)
                logger.debug("mqtt_subscribed", topic=topic)
            
            logger.info("mqtt_connected")
            
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
                logger.info("mqtt_disconnected")
            except Exception as exc:
                logger.warning("mqtt_disconnect_error", error=str(exc))
            finally:
                self._client = None

    async def run(self) -> None:
        """Run the MQTT client message loop with automatic reconnection on broker restart."""
        self._running = True
        logger.info("mqtt_client_running")
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

                    # Handle config API messages
                    if topic.endswith("/led/config/update"):
                        await self._handle_config_update(payload)
                    elif topic.endswith("/led/config/reload"):
                        await self._handle_config_reload()
                    elif topic.endswith("/led/config/get"):
                        await self._handle_config_get()
                    else:
                        # Regular message - pass to callback
                        try:
                            self._on_message(topic, payload)
                        except Exception as exc:
                            logger.error(
                                "message_callback_error",
                                topic=topic,
                                error=str(exc),
                                exc_info=True,
                            )
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
        logger.info("mqtt_client_stopping")
        self._running = False

    async def publish(self, topic: str, payload: dict) -> None:
        """Publish a message to an MQTT topic.
        
        Args:
            topic: The MQTT topic.
            payload: The message payload (will be JSON-serialized).
        """
        if not self._client:
            logger.warning("mqtt_publish_skipped_not_connected", topic=topic)
            return
        
        try:
            payload_json = json.dumps(payload)
            await self._client.publish(topic, payload_json, qos=1)
            logger.debug("mqtt_published", topic=topic)
        except Exception as exc:
            logger.error(
                "mqtt_publish_failed",
                topic=topic,
                error=str(exc),
                exc_info=True,
            )

    async def _handle_config_update(self, payload: bytes) -> None:
        """Handle config/update message.
        
        Args:
            payload: The new LED configuration as JSON.
        """
        logger.info("config_update_received")
        
        try:
            # Parse JSON
            config_dict = json.loads(payload.decode("utf-8"))
            
            # Validate with Pydantic
            new_config = LEDServiceConfig.model_validate(config_dict)
            
            # Pass to callback
            self._on_config_update(new_config)
            
            # Send success response
            await self._send_config_response(success=True, error=None)
            
        except Exception as exc:
            logger.error(
                "config_update_failed",
                error=str(exc),
                exc_info=True,
            )
            await self._send_config_response(success=False, error="invalid_config")

    async def _handle_config_reload(self) -> None:
        """Handle config/reload message."""
        logger.info("config_reload_received")
        
        try:
            self._on_config_reload()
            await self._send_config_response(success=True, error=None)
        except Exception as exc:
            logger.error(
                "config_reload_failed",
                error=str(exc),
                exc_info=True,
            )
            await self._send_config_response(success=False, error="reload_failed")

    async def _handle_config_get(self) -> None:
        """Handle config/get message.
        
        This sends the current LED configuration via config/response.
        """
        logger.info("config_get_received")
        # For now, just acknowledge - full implementation would fetch current config
        await self._send_config_response(success=True, error=None)

    async def _send_config_response(
        self,
        success: bool,
        error: str | None,
    ) -> None:
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
