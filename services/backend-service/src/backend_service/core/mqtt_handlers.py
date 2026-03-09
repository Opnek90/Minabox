"""MQTT message handlers for Backend Service."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

import backend_service.core.db_manager as _db_module
from backend_service.core.handlers.audio_handler import AudioHandler
from backend_service.core.handlers.button_handler import ButtonHandler
from backend_service.core.handlers.rfid_handler import RFIDHandler
from backend_service.core.handlers.timer_handler import TimerHandler
from backend_service.core.resume_position import save_resume_position

if TYPE_CHECKING:
    from backend_service.api.websocket import WebSocketManager
    from backend_service.core.mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)


class MQTTHandlers:
    """Handles incoming MQTT messages and triggers appropriate actions."""

    def __init__(
        self,
        mqtt_client: "MQTTClient",
        websocket_manager: "WebSocketManager" | None = None,
    ) -> None:
        """Initialize MQTT handlers.

        Args:
            mqtt_client: MQTT client instance
            websocket_manager: WebSocket manager for broadcasting events (optional)
        """
        self.mqtt_client = mqtt_client
        self.websocket_manager = websocket_manager

        # Shared state
        self.audio_status_cache: dict[str, Any] = {}
        self._last_audio_status: dict[str, Any] = {}
        self.playback_intent_active: bool = False
        self.stream_reconnect_task: asyncio.Task | None = None
        self.stream_reconnect_attempts: int = 0
        self.deliberate_stop: bool = False

        # Initialize sub-handlers
        self.rfid_handler = RFIDHandler(self)
        self.audio_handler = AudioHandler(self)
        self.button_handler = ButtonHandler(self)
        self.timer_handler = TimerHandler(self)

        logger.debug("mqtt_handlers_initialized")

    @property
    def last_audio_status(self) -> dict[str, Any]:
        """Backward compatibility property for external modules accessing this directly."""
        return self._last_audio_status

    def mark_deliberate_stop(self) -> None:
        """Signal that the next 'stopped' status is from an explicit stop command."""
        self.deliberate_stop = True

    async def handle_rfid_tag_scanned(self, topic: str, data: dict[str, Any]) -> None:
        await self.rfid_handler.handle_rfid_tag_scanned(topic, data)

    async def handle_rfid_tag_scanned_learning(self, topic: str, data: dict[str, Any]) -> None:
        await self.rfid_handler.handle_rfid_tag_scanned_learning(topic, data)

    async def handle_rfid_tag_removed(self, topic: str, data: dict[str, Any]) -> None:
        await self.rfid_handler.handle_rfid_tag_removed(topic, data)

    async def handle_audio_status(self, topic: str, data: dict[str, Any]) -> None:
        await self.audio_handler.handle_audio_status(topic, data)

    async def handle_button_action(self, topic: str, data: dict[str, Any]) -> None:
        await self.button_handler.handle_button_action(topic, data)

    async def handle_button_raw_event(self, topic: str, data: dict[str, Any]) -> None:
        """Delegate raw button hardware events to the button handler."""
        await self.button_handler.handle_button_raw_event(topic, data)

    async def handle_audio_position_report(self, topic: str, data: dict[str, Any]) -> None:
        """Persist the playback position reported by audio-service on stop/pause.

        Expected payload fields:
            source_uri  (str)        -- content identifier
            source_type (str)        -- 'track' | 'podcast' | 'stream'
            position_ms (int)        -- current position in ms
            duration_ms (int | None) -- total duration in ms, if known

        Streams are ignored — they have no meaningful resume position.
        """
        source_uri: str | None = data.get("source_uri")
        source_type: str = data.get("source_type", "")
        position_ms: int = int(data.get("position_ms") or 0)
        duration_ms_raw = data.get("duration_ms")
        duration_ms: int | None = int(duration_ms_raw) if duration_ms_raw else None

        if not source_uri or source_type == "stream":
            return

        if not _db_module.db_manager:
            logger.error("db_manager_not_initialized")
            return

        session = _db_module.db_manager.get_session()
        try:
            save_resume_position(
                session=session,
                source_uri=source_uri,
                position_ms=position_ms,
                content_type=source_type,
                duration_ms=duration_ms,
            )
        finally:
            session.close()

    def get_sleep_timer_status(self) -> dict[str, Any]:
        return self.timer_handler.get_sleep_timer_status()

    async def start_sleep_timer(self, minutes: int) -> None:
        await self.timer_handler.start_sleep_timer(minutes)

    async def cancel_sleep_timer(self) -> None:
        await self.timer_handler.cancel_sleep_timer()

    async def publish_play_track(self, track: Any) -> None:
        """Publish a play command for the given track object."""
        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": str(track.id),
                "source_type": track.source_type,
                "source_uri": track.source_uri,
                "start_position_ms": 0,
            },
        )

    async def notify_usage_denied(self, tag_id: str, now: datetime) -> None:
        """Publish usage-denied to LED service and broadcast to WebSocket clients."""
        topic = self.mqtt_client.config.get_mqtt_topic("led", "usage-denied")
        await self.mqtt_client.publish(
            topic,
            {"event": "usage_denied", "timestamp": now.isoformat()},
        )
        if self.websocket_manager:
            await self.websocket_manager.broadcast(
                {
                    "type": "usage_denied",
                    "data": {"tag_id": tag_id, "timestamp": now.isoformat()},
                }
            )

    async def schedule_stream_reconnect(
        self,
        track_id_raw: str,
        source_uri: str | None,
        delay: float,
    ) -> None:
        """Wait `delay` seconds then replay the stream if intent is still active."""
        try:
            await asyncio.sleep(delay)
            if self.playback_intent_active and not self.deliberate_stop:
                logger.info("stream_reconnecting_now", track_id=track_id_raw)
                await self.mqtt_client.publish_audio_command(
                    "play",
                    {
                        "track_id": track_id_raw,
                        "source_type": "stream",
                        "source_uri": source_uri,
                        "start_position_ms": 0,
                    },
                )
        except asyncio.CancelledError:
            pass
