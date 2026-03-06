"""Audio MQTT handlers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

import backend_service.core.db_manager as _db_module
from backend_service.core.handlers.utils import close_open_playback_event
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.session_manager import session_manager
from backend_service.core.usage_limits import read_daily_limit_settings
from backend_service.models.database import Podcast, Stream, Track

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)


class AudioHandler:
    # Stream reconnect tuning constants (issue #29)
    MAX_RECONNECT_ATTEMPTS: int = 5
    MAX_RECONNECT_DELAY_SEC: float = 30.0
    RECONNECT_BASE_DELAY_SEC: float = 2.0

    def __init__(self, dispatcher: "MQTTHandlers") -> None:
        self.dispatcher = dispatcher

    async def handle_audio_status(self, topic: str, data: dict[str, Any]) -> None:
        logger.debug("audio_status_received", data=data)

        prev_state = self.dispatcher.audio_status_cache.get("state")
        new_state = data.get("state")

        self.dispatcher.audio_status_cache = data
        self.dispatcher._last_audio_status.clear()
        self.dispatcher._last_audio_status.update(data)

        if new_state == "playing":
            if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
                self.dispatcher.stream_reconnect_task.cancel()
            self.dispatcher.stream_reconnect_attempts = 0

        if prev_state == "playing" and new_state in ("stopped", "error"):
            if not self.dispatcher.playback_intent_active:
                logger.info("auto_advance_skipped_no_playback_intent")
            elif self.dispatcher.deliberate_stop:
                self.dispatcher.deliberate_stop = False
                logger.info("auto_advance_skipped_deliberate_stop")
            else:
                daily_enabled, daily_minutes = read_daily_limit_settings()
                if daily_enabled and _db_module.db_manager:
                    db_session = _db_module.db_manager.get_session()
                    try:
                        close_open_playback_event(db_session, data)
                        today_min = get_today_listened_minutes(db_session)
                        if today_min >= daily_minutes:
                            logger.info("daily_limit_exceeded_fadeout")
                            await self.dispatcher.timer_handler._trigger_daily_limit_fade()
                            return
                    finally:
                        db_session.close()
                elif _db_module.db_manager:
                    db_session = _db_module.db_manager.get_session()
                    try:
                        close_open_playback_event(db_session, data)
                    finally:
                        db_session.close()

                track_id_raw = data.get("track_id")
                is_stream = isinstance(track_id_raw, str) and (
                    track_id_raw.startswith("stream-") or track_id_raw.startswith("podcast-")
                )

                if is_stream:
                    logger.warning("stream_ended_unexpectedly", track_id=track_id_raw)
                    if self.dispatcher.stream_reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
                        self.dispatcher.stream_reconnect_attempts += 1
                        delay = min(
                            self.RECONNECT_BASE_DELAY_SEC ** self.dispatcher.stream_reconnect_attempts,
                            self.MAX_RECONNECT_DELAY_SEC,
                        )
                        logger.info(
                            "stream_reconnect_scheduled",
                            attempt=self.dispatcher.stream_reconnect_attempts,
                            delay_sec=delay,
                        )
                        if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
                            self.dispatcher.stream_reconnect_task.cancel()
                        self.dispatcher.stream_reconnect_task = asyncio.create_task(
                            self.dispatcher.schedule_stream_reconnect(track_id_raw, data.get("source_uri"), delay)
                        )
                    else:
                        logger.error("stream_reconnect_gave_up", track_id=track_id_raw)
                        self.dispatcher.playback_intent_active = False
                else:
                    logger.info("track_ended_naturally_auto_advancing")
                    await self.dispatcher.button_handler._handle_next()

        if new_state == "stopped" and prev_state != "playing" and _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                close_open_playback_event(db_session, data)
            finally:
                db_session.close()

        payload = dict(data)
        track_id_raw = payload.get("track_id")
        if track_id_raw is not None and _db_module.db_manager:
            session = _db_module.db_manager.get_session()
            try:
                if isinstance(track_id_raw, str) and track_id_raw.startswith("stream-"):
                    try:
                        stream_id = int(track_id_raw.split("-", 1)[1], 10)
                        stream = session.query(Stream).filter(Stream.id == stream_id).first()
                        if stream:
                            payload["track_title"] = stream.title
                            payload["track_artist"] = stream.artist
                            payload["track_cover_art_url"] = getattr(stream, "cover_art_url", None)
                            if payload.get("state") == "playing":
                                stream.last_played_at = datetime.now(UTC)
                                session.commit()
                    except (ValueError, IndexError):
                        pass
                elif isinstance(track_id_raw, str) and track_id_raw.startswith("podcast-"):
                    try:
                        podcast_id = int(track_id_raw.split("-", 1)[1], 10)
                        podcast = session.query(Podcast).filter(Podcast.id == podcast_id).first()
                        if podcast:
                            payload["track_title"] = podcast.title
                            payload["track_artist"] = None
                            payload["track_cover_art_url"] = getattr(podcast, "cover_art_url", None)
                            if payload.get("state") == "playing":
                                podcast.last_played_at = datetime.now(UTC)
                                session.commit()
                    except (ValueError, IndexError):
                        pass
                else:
                    try:
                        tid = int(track_id_raw)
                    except (TypeError, ValueError):
                        tid = None
                    if tid is not None:
                        track = session.query(Track).filter(Track.id == tid).first()
                        if track:
                            payload["track_title"] = track.title
                            payload["track_artist"] = track.artist
                            payload["track_album"] = track.album
                            payload["track_cover_art_url"] = getattr(track, "cover_art_url", None)
                            if payload.get("state") == "playing":
                                track.last_played_at = datetime.now(UTC)
                                session.commit()
            finally:
                session.close()

        sess = session_manager.session
        if sess and sess.tracks and payload.get("track_id") is not None:
            try:
                current_tid = sess.current_track.id if sess.current_track else None
                raw_tid = payload.get("track_id")
                if current_tid is not None and raw_tid is not None:
                    if str(raw_tid) == str(current_tid):
                        payload["playlist_position"] = sess.current_track_index + 1
                        payload["playlist_total"] = len(sess.tracks)
            except (TypeError, ValueError, AttributeError):
                pass

        if self.dispatcher.websocket_manager:
            self.dispatcher.websocket_manager.set_last_audio_status_payload(payload)
            await self.dispatcher.websocket_manager.broadcast(
                {
                    "type": "audio_status",
                    "data": payload,
                }
            )
