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
from backend_service.core.playback_settings import read_loop_guard_minutes
from backend_service.core.session_manager import (
    PlaybackSession,
    SessionTrack,
    session_manager,
)

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)


class ButtonHandler:
    def __init__(self, dispatcher: MQTTHandlers) -> None:
        self.dispatcher = dispatcher

    async def handle_button_action(self, topic: str, data: dict[str, Any]) -> None:
        action_from_topic = topic.split("/")[-1]

        # raw-event topics are handled by handle_button_raw_event.
        # Returning early prevents wrong side-effects such as setting
        # playback_intent_active or cancelling stream_reconnect_task.
        if action_from_topic == "raw-event":
            return

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

    async def handle_button_raw_event(self, topic: str, data: dict[str, Any]) -> None:
        """Forward raw hardware button events to WebSocket clients.

        Called for every physical button press on minabox/{id}/button/raw-event,
        regardless of whether an action mapping exists. This powers the WebUI
        hardware test-mode so it shows feedback even for unmapped buttons.
        """
        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast(
                {
                    "type": "button_raw_event",
                    "data": {
                        "button_id": data.get("button_id"),
                        "name": data.get("name"),
                        "event_type": data.get("event_type"),
                        "timestamp": data.get("timestamp"),
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

    def _loop_decision(self, sess: PlaybackSession) -> tuple[bool, str]:
        """May the session start over? Returns (allowed, reason when refused).

        Called at the end of the last track. The minutes guard is a backstop
        here -- normally `TimerHandler`'s loop guard has already faded the box
        out mid-track; this catches the case where a single pass outlasts the
        limit on its own.
        """
        if sess.repeat_mode != "all":
            return False, "no_repeat"
        if sess.loop_requires_tag and not self.dispatcher.rfid_handler.tag_present:
            return False, "tag_removed"
        guard_minutes = read_loop_guard_minutes()
        if guard_minutes and sess.loop_elapsed_seconds() >= guard_minutes * 60:
            return False, "loop_guard"
        return True, ""

    async def _advance(self, sess: PlaybackSession, db_session: Any | None) -> str:
        """Move to the next track. Returns "played", "stop" or "loop_guard".

        Stopping is left to the caller so the DB session is not held open
        across a fade that can run for minutes.
        """
        if not sess.has_next:
            may_loop, reason = self._loop_decision(sess)
            if may_loop:
                first_loop = sess.loop_started_at is None
                sess.mark_loop_started()
                sess.reset()
                first = sess.current_track
                if first:
                    if first_loop:
                        self.dispatcher.timer_handler.start_loop_guard(
                            read_loop_guard_minutes(), sess
                        )
                    logger.info(
                        "session_looping",
                        playlist_id=sess.playlist_id,
                        requires_tag=sess.loop_requires_tag,
                    )
                    await self._play(first, db_session)
                    return "played"
            logger.info("session_end", reason=reason)
            return "loop_guard" if reason == "loop_guard" else "stop"

        next_track = session_manager.next_track()
        if not next_track:
            return "stop"
        await self._play(next_track, db_session)
        return "played"

    async def _play(self, track: SessionTrack, db_session: Any | None) -> None:
        if db_session is not None:
            create_playback_event_for_current_track(db_session)
        await self.dispatcher.publish_play_track(track)

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
                outcome = await self._advance(sess, db_session)
            finally:
                db_session.close()
        else:
            outcome = await self._advance(sess, None)

        if outcome == "loop_guard":
            # Playback already ran out on its own, so there is nothing left to
            # fade -- just make sure the box stays quiet and the player toggle
            # reflects it.
            await self._stop_repeat("loop_guard")
        elif outcome == "stop":
            self.dispatcher.playback_intent_active = False
            await self.dispatcher.mqtt_client.publish_audio_command("stop", {})

    async def _stop_repeat(self, reason: str) -> None:
        session_manager.set_repeat_mode("none")
        self.dispatcher.mark_deliberate_stop()
        self.dispatcher.playback_intent_active = False
        await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast({
                "type": "repeat_mode",
                "data": {"repeat_mode": "none"},
            })
        logger.info("repeat_stopped", reason=reason)

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
