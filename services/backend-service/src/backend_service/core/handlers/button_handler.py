"""Button MQTT handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

import backend_service.core.db_manager as _db_module
from backend_service.core.handlers.utils import (
    close_open_playback_event,
    create_playback_event_for_current_track,
)
from backend_service.core.session_manager import session_manager

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)


class ButtonHandler:
    def __init__(self, dispatcher: "MQTTHandlers") -> None:
        self.dispatcher = dispatcher

    async def handle_button_action(self, topic: str, data: dict[str, Any]) -> None:
        action_from_topic = topic.split("/")[-1]
        action = action_from_topic.replace("-", "_")
        logger.info("button_action_received", action=action, data=data)

        self.dispatcher.playback_intent_active = True

        if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
            self.dispatcher.stream_reconnect_task.cancel()
            self.dispatcher.stream_reconnect_attempts = 0

        if action == "play_pause":
            await self._handle_play_pause()
        elif action == "next":
            await self._handle_next()
        elif action == "prev":
            await self._handle_prev()
        elif action in ("volume_up", "volume_down"):
            pass
        elif action in ("mute", "mute_toggle"):
            await self.dispatcher.mqtt_client.publish_audio_command("mute-toggle", {})
        elif action == "sleep_timer_toggle":
            await self.dispatcher.timer_handler._handle_sleep_timer_toggle()
        elif action == "repeat_cycle":
            await self._handle_repeat_cycle()
        elif action == "shuffle_toggle":
            await self._handle_shuffle_toggle()
        elif action == "next_output_device":
            await self.dispatcher.mqtt_client.publish_audio_command("switch-device", {"direction": "next"})

        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast(
                {
                    "type": "button_action",
                    "data": {
                        "action": action,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )

    async def _handle_play_pause(self) -> None:
        current_state = self.dispatcher.audio_status_cache.get("state", "stopped")

        if current_state == "playing":
            self.dispatcher.mark_deliberate_stop()
            self.dispatcher.playback_intent_active = False
            await self.dispatcher.mqtt_client.publish_audio_command("pause", {})
        elif current_state == "paused":
            await self.dispatcher.mqtt_client.publish_audio_command("play", {})
        elif current_state == "stopped" and session_manager.session:
            track = session_manager.get_current_track()
            if track:
                await self.dispatcher.mqtt_client.publish_audio_command(
                    "play",
                    {
                        "track_id": str(track.id),
                        "source_type": track.source_type,
                        "source_uri": track.source_uri,
                        "start_position_ms": 0,
                    },
                )

    async def _handle_next(self) -> None:
        sess = session_manager.session
        if not sess or not sess.tracks:
            self.dispatcher.playback_intent_active = False
            await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
            return

        if _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                close_open_playback_event(db_session, self.dispatcher.audio_status_cache)
                repeat = sess.repeat_mode
                if repeat == "all" and not sess.has_next:
                    sess.reset()
                    first = sess.current_track
                    if first:
                        create_playback_event_for_current_track(db_session)
                        await self.dispatcher.publish_play_track(first)
                    return
                next_track = session_manager.next_track()
                if next_track:
                    create_playback_event_for_current_track(db_session)
                    await self.dispatcher.publish_play_track(next_track)
                else:
                    self.dispatcher.playback_intent_active = False
                    await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
            finally:
                db_session.close()
        else:
            repeat = sess.repeat_mode
            if repeat == "all" and not sess.has_next:
                sess.reset()
                first = sess.current_track
                if first:
                    await self.dispatcher.publish_play_track(first)
                return
            next_track = session_manager.next_track()
            if next_track:
                await self.dispatcher.publish_play_track(next_track)
            else:
                self.dispatcher.playback_intent_active = False
                await self.dispatcher.mqtt_client.publish_audio_command("stop", {})

    async def _handle_prev(self) -> None:
        if _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                close_open_playback_event(db_session, self.dispatcher.audio_status_cache)
                prev_track = session_manager.prev_track()
                if prev_track:
                    create_playback_event_for_current_track(db_session)
                    await self.dispatcher.publish_play_track(prev_track)
            finally:
                db_session.close()
        else:
            prev_track = session_manager.prev_track()
            if prev_track:
                await self.dispatcher.publish_play_track(prev_track)

    async def _handle_repeat_cycle(self) -> None:
        current = session_manager.get_repeat_mode()
        next_mode = "all" if current == "none" else "none"
        session_manager.set_repeat_mode(next_mode)
        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast({
                "type": "repeat_mode",
                "data": {"repeat_mode": next_mode},
            })

    async def _handle_shuffle_toggle(self) -> None:
        new_shuffle = session_manager.toggle_shuffle()
        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast({
                "type": "shuffle_mode",
                "data": {"shuffle": new_shuffle},
            })
