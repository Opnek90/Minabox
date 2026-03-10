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

# Periodic flush interval: how often to persist in-memory accumulated_ms to DB
# to survive unexpected power-loss (fix #58)
_FLUSH_INTERVAL_SEC = 60


class AudioHandler:
    # Stream reconnect tuning constants
    MAX_RECONNECT_ATTEMPTS: int = 5
    MAX_RECONNECT_DELAY_SEC: float = 30.0
    RECONNECT_BASE_DELAY_SEC: float = 2.0

    def __init__(self, dispatcher: "MQTTHandlers") -> None:
        self.dispatcher = dispatcher

        # fix #58: in-memory accumulator for real play time (works for streams too)
        self._play_started_at: datetime | None = None
        self._active_event_id: int | None = None
        self._accumulated_ms: int = 0
        self._flush_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # fix #58: helpers for in-memory listen-time tracking
    # ------------------------------------------------------------------

    def _start_accumulator(self, event_id: int | None) -> None:
        """Called when playback transitions to 'playing'."""
        self._play_started_at = datetime.now(UTC)
        if event_id is not None:
            self._active_event_id = event_id
        # Start periodic flush if not already running
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())

    def _pause_accumulator(self) -> None:
        """Called when playback leaves 'playing' (pause/stop/error).
        Accumulates elapsed ms into self._accumulated_ms.
        """
        if self._play_started_at is not None:
            elapsed_ms = int((datetime.now(UTC) - self._play_started_at).total_seconds() * 1000)
            self._accumulated_ms += elapsed_ms
            self._play_started_at = None

    def _reset_accumulator(self) -> None:
        """Called after a PlaybackEvent is closed. Resets all tracking state."""
        self._play_started_at = None
        self._active_event_id = None
        self._accumulated_ms = 0
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            self._flush_task = None

    def _current_accumulated_ms(self) -> int:
        """Return total accumulated ms including any currently-running segment."""
        total = self._accumulated_ms
        if self._play_started_at is not None:
            total += int((datetime.now(UTC) - self._play_started_at).total_seconds() * 1000)
        return total

    async def _flush_loop(self) -> None:
        """Periodically persist accumulated_ms to DB so power-loss loses at most 60s."""
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL_SEC)
            if self._active_event_id is None:
                continue
            current_total = self._current_accumulated_ms()
            if current_total <= 0 or not _db_module.db_manager:
                continue
            db_session = _db_module.db_manager.get_session()
            try:
                from backend_service.models.database import PlaybackEvent  # local import avoids cycle
                event = db_session.query(PlaybackEvent).get(self._active_event_id)
                if event and event.ended_at is None:
                    event.listened_ms = current_total
                    db_session.commit()
                    logger.debug("playback_stats_flushed", event_id=self._active_event_id, ms=current_total)
            except Exception as exc:
                logger.warning("playback_stats_flush_error", error=str(exc))
            finally:
                db_session.close()

    # ------------------------------------------------------------------

    async def handle_audio_status(self, topic: str, data: dict[str, Any]) -> None:
        logger.debug("audio_status_received", data=data)

        prev_state = self.dispatcher.audio_status_cache.get("state")
        new_state = data.get("state")

        self.dispatcher.audio_status_cache = data
        self.dispatcher._last_audio_status.clear()
        self.dispatcher._last_audio_status.update(data)

        # fix #58: track transition into 'playing'
        if new_state == "playing" and prev_state != "playing":
            if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
                self.dispatcher.stream_reconnect_task.cancel()
            self.dispatcher.stream_reconnect_attempts = 0
            # Look up the current open PlaybackEvent id for the flush loop
            if _db_module.db_manager:
                _db = _db_module.db_manager.get_session()
                try:
                    from backend_service.models.database import PlaybackEvent
                    open_ev = (
                        _db.query(PlaybackEvent)
                        .filter(PlaybackEvent.ended_at.is_(None))
                        .order_by(PlaybackEvent.started_at.desc())
                        .first()
                    )
                    ev_id = open_ev.id if open_ev else None
                finally:
                    _db.close()
            else:
                ev_id = None
            self._start_accumulator(ev_id)

        elif new_state == "playing" and prev_state == "playing":
            # Already playing (e.g. metadata update) — no state change needed
            if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
                self.dispatcher.stream_reconnect_task.cancel()
            self.dispatcher.stream_reconnect_attempts = 0

        if prev_state == "playing" and new_state in ("stopped", "error"):
            # fix #58: pause accumulator before closing event
            self._pause_accumulator()
            accumulated = self._current_accumulated_ms()

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
                        close_open_playback_event(db_session, data, accumulated_ms=accumulated)
                        self._reset_accumulator()
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
                        close_open_playback_event(db_session, data, accumulated_ms=accumulated)
                        self._reset_accumulator()
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
                        # fix #58: on reconnect, do NOT reset accumulator—keep same event accumulating
                        self.dispatcher.stream_reconnect_task = asyncio.create_task(
                            self.dispatcher.schedule_stream_reconnect(track_id_raw, data.get("source_uri"), delay)
                        )
                    else:
                        logger.error("stream_reconnect_gave_up", track_id=track_id_raw)
                        self.dispatcher.playback_intent_active = False
                        self._reset_accumulator()
                else:
                    logger.info("track_ended_naturally_auto_advancing")
                    self._reset_accumulator()
                    await self.dispatcher.button_handler._handle_next()

        if new_state == "stopped" and prev_state != "playing" and _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                close_open_playback_event(db_session, data, accumulated_ms=self._current_accumulated_ms() or None)
                self._reset_accumulator()
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
