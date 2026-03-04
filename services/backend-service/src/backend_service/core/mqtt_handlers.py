"""MQTT message handlers for Backend Service."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

import backend_service.core.db_manager as _db_module
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.session_manager import session_manager
from backend_service.core.sleep_settings import (
    read_bedtime_fade_settings,
    read_sleep_timer_minutes,
)
from backend_service.core.usage_limits import (
    is_within_allowed_usage_time,
    read_allowed_usage_times,
    read_daily_limit_settings,
    read_stop_playback_on_tag_remove,
)
from backend_service.exceptions import ContentNotFoundError
from backend_service.models.database import (
    PlaybackEvent,
    Playlist,
    PlaylistTrack,
    Podcast,
    PodcastEpisode,
    Stream,
    Tag,
    Track,
)

if TYPE_CHECKING:
    from backend_service.api.websocket import WebSocketManager
    from backend_service.core.mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)

# Seconds to ignore the same tag_id after we started playback
TAG_SCAN_COOLDOWN_SEC = 5.0


def _close_open_playback_event(db_session: Session, status_data: dict[str, Any] | None = None) -> None:
    """Close the latest open playback event; set listened_ms from status_data if present."""
    open_event = (
        db_session.query(PlaybackEvent)
        .filter(PlaybackEvent.ended_at.is_(None))
        .order_by(PlaybackEvent.started_at.desc())
        .first()
    )
    if not open_event:
        return
    open_event.ended_at = datetime.now(UTC)
    if status_data:
        pos = status_data.get("position_ms")
        dur = status_data.get("duration_ms")
        if pos is not None and isinstance(pos, (int, float)):
            ms = int(pos)
            if dur is not None and isinstance(dur, (int, float)) and int(dur) > 0:
                ms = min(ms, int(dur))
            if ms >= 0:
                open_event.listened_ms = ms
    db_session.commit()


def _create_playback_event_for_current_track(db_session: Session) -> bool:
    """Create a new PlaybackEvent for session_manager's current track. Returns True if created."""
    sess = session_manager.session
    if not sess or not sess.current_track:
        return False
    track = sess.current_track
    content_type = "playlist" if sess.playlist_id is not None else "track"
    event = PlaybackEvent(
        started_at=datetime.now(UTC),
        content_type=content_type,
        track_id=track.id,
        playlist_id=sess.playlist_id,
        tag_id=None,
    )
    db_session.add(event)
    db_session.commit()
    return True


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
        self._audio_status_cache: dict[str, Any] = {}
        self._tag_scan_cooldown_until: dict[str, float] = {}
        self._sleep_timer_task: asyncio.Task | None = None
        self._sleep_timer_start_time: float = 0.0
        self._sleep_timer_duration_ms: int = 0
        self._bedtime_fade_task: asyncio.Task | None = None

        # Debounce tracking for tags to prevent restart flutter
        self._last_played_tag_id: str | None = None
        self._last_played_tag_time: float = 0.0

        # Track active playback intent (to prevent unwanted auto-advance loops)
        self._playback_intent_active: bool = False

        # Stream reconnect state
        self._stream_reconnect_task: asyncio.Task | None = None
        self._stream_reconnect_attempts: int = 0

        # Audio status cache for external access (e.g. REST routes)
        self._last_audio_status: dict[str, Any] = {}

        # Set to True by mark_deliberate_stop() so that the resulting playing→stopped
        # state transition does NOT trigger auto-advance to the next track.
        self._deliberate_stop: bool = False

        logger.debug("mqtt_handlers_initialized")

    # -------------------------------------------------------------------------
    # Public state accessors
    # -------------------------------------------------------------------------

    @property
    def last_audio_status(self) -> dict[str, Any]:
        """Return the last known audio status (read-only view)."""
        return self._last_audio_status

    def mark_deliberate_stop(self) -> None:
        """Signal that the next 'stopped' status is from an explicit stop command."""
        self._deliberate_stop = True

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _publish_play_track(self, track: Any) -> None:
        """Publish a play command for the given track object.

        Centralises the repeated publish_audio_command('play', ...) block that
        appears in _handle_next() and _handle_prev().
        """
        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": str(track.id),
                "source_type": track.source_type,
                "source_uri": track.source_uri,
                "start_position_ms": 0,
            },
        )

    async def _notify_usage_denied(self, tag_id: str, now: datetime) -> None:
        """Publish usage-denied to LED service and broadcast to WebSocket clients.

        Used for both allowed-time-window and daily-limit violations so the
        two call sites in handle_rfid_tag_scanned() share a single implementation.
        """
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

    async def _schedule_stream_reconnect(
        self,
        track_id_raw: str,
        source_uri: str | None,
        delay: float,
    ) -> None:
        """Wait `delay` seconds then replay the stream if intent is still active.

        Replaces the inline ``_reconnect`` closure previously defined inside
        handle_audio_status() — makes it independently testable and readable.
        """
        try:
            await asyncio.sleep(delay)
            if self._playback_intent_active and not self._deliberate_stop:
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

    # -------------------------------------------------------------------------
    # RFID handlers
    # -------------------------------------------------------------------------

    async def handle_rfid_tag_scanned(self, topic: str, data: dict[str, Any]) -> None:
        """Handle RFID tag scanned event (normal mode).

        Args:
            topic: MQTT topic
            data: Event data with tag_id, reader_id, timestamp
        """
        tag_id = data.get("tag_id")
        if not tag_id:
            logger.warning("rfid_tag_scanned_missing_tag_id", data=data)
            return

        now_sec = time.time()

        if now_sec < self._tag_scan_cooldown_until.get(tag_id, 0):
            logger.info(
                "rfid_tag_scan_ignored_cooldown",
                tag_id=tag_id,
                cooldown_sec=TAG_SCAN_COOLDOWN_SEC,
            )
            return

        current_state = self._audio_status_cache.get("state")
        if current_state == "playing" and self._last_played_tag_id == tag_id:
            time_since_start = now_sec - self._last_played_tag_time
            if time_since_start < 15.0:
                logger.info(
                    "rfid_tag_scan_ignored_already_playing",
                    tag_id=tag_id,
                    time_since_start=time_since_start,
                )
                self._tag_scan_cooldown_until[tag_id] = now_sec + 2.0
                return

        logger.info("rfid_tag_scanned_received", tag_id=tag_id)

        if self._stream_reconnect_task and not self._stream_reconnect_task.done():
            self._stream_reconnect_task.cancel()
            self._stream_reconnect_attempts = 0

        if not _db_module.db_manager:
            logger.error("db_manager_not_initialized")
            return

        session = _db_module.db_manager.get_session()
        try:
            tag = session.query(Tag).filter(Tag.tag_id == tag_id).first()

            if not tag:
                logger.warning("tag_not_found", tag_id=tag_id)
                unknown_tag_topic = self.mqtt_client.config.get_mqtt_topic("rfid", "unknown-tag")
                await self.mqtt_client.publish(
                    unknown_tag_topic,
                    {
                        "tag_id": tag_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
                if self.websocket_manager:
                    await self.websocket_manager.broadcast(
                        {
                            "type": "tag_not_found",
                            "data": {
                                "tag_id": tag_id,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        }
                    )
                return

            now = datetime.now(UTC)

            # Check allowed usage times (parental control)
            slots = read_allowed_usage_times()
            if slots and not is_within_allowed_usage_time(now, slots):
                logger.info("tag_scanned_outside_allowed_time", tag_id=tag_id)
                await self._notify_usage_denied(tag_id, now)
                return

            # Check daily limit (parental control)
            daily_enabled, daily_minutes = read_daily_limit_settings()
            if daily_enabled:
                today_min = get_today_listened_minutes(session)
                if today_min >= daily_minutes:
                    logger.info("tag_scanned_daily_limit_exceeded", tag_id=tag_id)
                    await self._notify_usage_denied(tag_id, now)
                    return

            tag.last_scanned_at = now
            session.commit()

            logger.info(
                "tag_found",
                tag_id=tag_id,
                content_type=tag.content_type,
                content_id=tag.content_id,
            )

            self._last_played_tag_id = tag_id
            self._last_played_tag_time = now_sec
            self._playback_intent_active = True
            self._stream_reconnect_attempts = 0

            self._tag_scan_cooldown_until[tag_id] = now_sec + TAG_SCAN_COOLDOWN_SEC
            self._tag_scan_cooldown_until = {
                tid: until
                for tid, until in self._tag_scan_cooldown_until.items()
                if until > now_sec
            }

            tag_db_id = tag.id
            if tag.content_type == "playlist":
                await self._handle_playlist_playback(session, tag.content_id, tag_id=tag_db_id)
            elif tag.content_type == "track":
                await self._handle_track_playback(session, tag.content_id, tag_id=tag_db_id)
            elif tag.content_type == "stream":
                await self._handle_stream_playback(session, tag.content_id, tag_id=tag_db_id)
            elif tag.content_type == "podcast":
                await self._handle_podcast_playback(session, tag.content_id, tag_id=tag_db_id)

            if self.websocket_manager:
                await self.websocket_manager.broadcast(
                    {
                        "type": "rfid_scanned",
                        "data": {
                            "tag_id": tag.tag_id,
                            "content_type": tag.content_type,
                            "content_name": tag.name,
                            "content_id": tag.content_id,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    }
                )

        finally:
            session.close()

    async def _handle_playlist_playback(
        self, session: Session, playlist_id: int, tag_id: int | None = None
    ) -> None:
        """Start playlist playback."""
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()
        if not playlist:
            logger.error("playlist_not_found", playlist_id=playlist_id)
            raise ContentNotFoundError(f"Playlist {playlist_id} not found")

        playlist_tracks = (
            session.query(PlaylistTrack)
            .filter(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position)
            .all()
        )
        if not playlist_tracks:
            logger.warning("playlist_empty", playlist_id=playlist_id)
            return

        tracks = [pt.track for pt in playlist_tracks]
        session_manager.create_session(tracks=tracks, playlist_id=playlist_id, shuffle=True)
        first_track = session_manager.session.current_track if session_manager.session else tracks[0]

        event = PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="playlist",
            playlist_id=playlist_id,
            tag_id=tag_id,
        )
        session.add(event)
        session.commit()

        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": str(first_track.id),
                "source_type": first_track.source_type,
                "source_uri": first_track.source_uri,
                "start_position_ms": 0,
            },
        )
        logger.info(
            "playlist_playback_started",
            playlist_id=playlist_id,
            track_count=len(tracks),
            first_track_id=first_track.id,
        )

    async def _handle_track_playback(
        self, session: Session, track_id: int, tag_id: int | None = None
    ) -> None:
        """Start single track playback."""
        track = session.query(Track).filter(Track.id == track_id).first()
        if not track:
            logger.error("track_not_found", track_id=track_id)
            raise ContentNotFoundError(f"Track {track_id} not found")

        session_manager.create_session(tracks=[track])
        event = PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="track",
            track_id=track_id,
            tag_id=tag_id,
        )
        session.add(event)
        session.commit()

        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": str(track.id),
                "source_type": track.source_type,
                "source_uri": track.source_uri,
                "start_position_ms": 0,
            },
        )
        logger.info("track_playback_started", track_id=track_id, title=track.title)

    async def _handle_stream_playback(
        self, session: Session, stream_id: int, tag_id: int | None = None
    ) -> None:
        """Start stream playback (no session)."""
        stream = session.query(Stream).filter(Stream.id == stream_id).first()
        if not stream:
            logger.error("stream_not_found", stream_id=stream_id)
            raise ContentNotFoundError(f"Stream {stream_id} not found")

        if session_manager.session:
            session_manager.session.reset()

        event = PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="stream",
            stream_id=stream_id,
            tag_id=tag_id,
        )
        session.add(event)
        session.commit()

        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": f"stream-{stream.id}",
                "source_type": "stream",
                "source_uri": stream.source_uri,
                "start_position_ms": 0,
            },
        )
        logger.info("stream_playback_started", stream_id=stream_id, title=stream.title)

    async def _handle_podcast_playback(
        self, session: Session, podcast_id: int, tag_id: int | None = None
    ) -> None:
        """Start podcast playback (latest episode)."""
        podcast = session.query(Podcast).filter(Podcast.id == podcast_id).first()
        if not podcast:
            logger.error("podcast_not_found", podcast_id=podcast_id)
            raise ContentNotFoundError(f"Podcast {podcast_id} not found")

        episode = (
            session.query(PodcastEpisode)
            .filter(PodcastEpisode.podcast_id == podcast_id)
            .order_by(PodcastEpisode.published_at.desc())
            .first()
        )
        if not episode:
            logger.warning("podcast_no_episodes", podcast_id=podcast_id)
            return

        podcast.last_played_at = datetime.now(UTC)
        event = PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="podcast",
            podcast_id=podcast_id,
            tag_id=tag_id,
        )
        session.add(event)
        session.commit()

        if session_manager.session:
            session_manager.session.reset()

        await self.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": f"podcast-{podcast.id}",
                "source_type": "podcast",
                "source_uri": episode.source_uri,
                "start_position_ms": 0,
            },
        )
        logger.info(
            "podcast_playback_started",
            podcast_id=podcast_id,
            episode_id=episode.id,
            title=episode.title,
        )

    async def handle_rfid_tag_scanned_learning(
        self,
        topic: str,
        data: dict[str, Any],
    ) -> None:
        """Handle RFID tag scanned event (learning mode)."""
        tag_id = data.get("tag_id")
        if not tag_id:
            logger.warning("rfid_tag_scanned_learning_missing_tag_id", data=data)
            return

        logger.info("rfid_tag_scanned_learning_received", tag_id=tag_id)

        already_assigned = False
        if _db_module.db_manager:
            session = _db_module.db_manager.get_session()
            try:
                existing_tag = session.query(Tag).filter(Tag.tag_id == tag_id).first()
                already_assigned = existing_tag is not None
                logger.info(
                    "rfid_tag_learning_result",
                    tag_id=tag_id,
                    already_assigned=already_assigned,
                )
            finally:
                session.close()
        else:
            logger.warning("db_manager_not_initialized_using_fallback", tag_id=tag_id)

        if self.websocket_manager:
            await self.websocket_manager.broadcast(
                {
                    "type": "rfid_scanned_learning",
                    "data": {
                        "tag_id": tag_id,
                        "already_assigned": already_assigned,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )

    async def handle_rfid_tag_removed(self, topic: str, data: dict[str, Any]) -> None:
        """Handle RFID tag removed: optionally stop playback when tag is taken off reader."""
        tag_id = data.get("tag_id", "")

        if self._last_played_tag_id == tag_id:
            self._last_played_tag_id = None

        if not read_stop_playback_on_tag_remove():
            return

        logger.info("rfid_tag_removed_stopping_playback", tag_id=tag_id)

        if self._stream_reconnect_task and not self._stream_reconnect_task.done():
            self._stream_reconnect_task.cancel()

        self.mark_deliberate_stop()
        self._playback_intent_active = False
        await self.mqtt_client.publish_audio_command("stop", {})

    # -------------------------------------------------------------------------
    # Audio status handler
    # -------------------------------------------------------------------------

    async def handle_audio_status(self, topic: str, data: dict[str, Any]) -> None:
        """Handle audio status update.

        Enriches status with track title/artist/album from DB for WebUI display.
        """
        logger.debug("audio_status_received", data=data)

        prev_state = self._audio_status_cache.get("state")
        new_state = data.get("state")

        self._audio_status_cache = data
        self._last_audio_status.clear()
        self._last_audio_status.update(data)

        if new_state == "playing":
            if self._stream_reconnect_task and not self._stream_reconnect_task.done():
                self._stream_reconnect_task.cancel()
            self._stream_reconnect_attempts = 0

        if prev_state == "playing" and new_state in ("stopped", "error"):
            if not self._playback_intent_active:
                logger.info("auto_advance_skipped_no_playback_intent")
            elif self._deliberate_stop:
                self._deliberate_stop = False
                logger.info("auto_advance_skipped_deliberate_stop")
            else:
                daily_enabled, daily_minutes = read_daily_limit_settings()
                if daily_enabled and _db_module.db_manager:
                    db_session = _db_module.db_manager.get_session()
                    try:
                        _close_open_playback_event(db_session, data)
                        today_min = get_today_listened_minutes(db_session)
                        if today_min >= daily_minutes:
                            logger.info("daily_limit_exceeded_fadeout")
                            await self._trigger_daily_limit_fade()
                            return
                    finally:
                        db_session.close()
                elif _db_module.db_manager:
                    db_session = _db_module.db_manager.get_session()
                    try:
                        _close_open_playback_event(db_session, data)
                    finally:
                        db_session.close()

                track_id_raw = data.get("track_id")
                is_stream = isinstance(track_id_raw, str) and (
                    track_id_raw.startswith("stream-") or track_id_raw.startswith("podcast-")
                )

                if is_stream:
                    logger.warning("stream_ended_unexpectedly", track_id=track_id_raw)
                    if self._stream_reconnect_attempts < 5:
                        self._stream_reconnect_attempts += 1
                        delay = min(2 ** self._stream_reconnect_attempts, 30)
                        logger.info(
                            "stream_reconnect_scheduled",
                            attempt=self._stream_reconnect_attempts,
                            delay_sec=delay,
                        )
                        if self._stream_reconnect_task and not self._stream_reconnect_task.done():
                            self._stream_reconnect_task.cancel()
                        self._stream_reconnect_task = asyncio.create_task(
                            self._schedule_stream_reconnect(
                                track_id_raw, data.get("source_uri"), delay
                            )
                        )
                    else:
                        logger.error("stream_reconnect_gave_up", track_id=track_id_raw)
                        self._playback_intent_active = False
                else:
                    logger.info("track_ended_naturally_auto_advancing")
                    await self._handle_next()

        if new_state == "stopped" and prev_state != "playing" and _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                _close_open_playback_event(db_session, data)
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

        if self.websocket_manager:
            self.websocket_manager.set_last_audio_status_payload(payload)

        if self.websocket_manager:
            await self.websocket_manager.broadcast(
                {
                    "type": "audio_status",
                    "data": payload,
                }
            )

    # -------------------------------------------------------------------------
    # Button handler
    # -------------------------------------------------------------------------

    async def handle_button_action(self, topic: str, data: dict[str, Any]) -> None:
        """Handle button action event."""
        action_from_topic = topic.split("/")[-1]
        action = action_from_topic.replace("-", "_")
        logger.info("button_action_received", action=action, data=data)

        self._playback_intent_active = True

        if self._stream_reconnect_task and not self._stream_reconnect_task.done():
            self._stream_reconnect_task.cancel()
            self._stream_reconnect_attempts = 0

        if action == "play_pause":
            await self._handle_play_pause()
        elif action == "next":
            await self._handle_next()
        elif action == "prev":
            await self._handle_prev()
        elif action in ("volume_up", "volume_down"):
            pass
        elif action in ("mute", "mute_toggle"):
            await self.mqtt_client.publish_audio_command("mute-toggle", {})
        elif action == "sleep_timer_toggle":
            await self._handle_sleep_timer_toggle()
        elif action == "repeat_cycle":
            await self._handle_repeat_cycle()
        elif action == "shuffle_toggle":
            await self._handle_shuffle_toggle()
        elif action == "next_output_device":
            await self.mqtt_client.publish_audio_command("switch-device", {"direction": "next"})

        if self.websocket_manager:
            await self.websocket_manager.broadcast(
                {
                    "type": "button_action",
                    "data": {
                        "action": action,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )

    async def _handle_play_pause(self) -> None:
        """Handle play/pause button."""
        current_state = self._audio_status_cache.get("state", "stopped")

        if current_state == "playing":
            self.mark_deliberate_stop()
            self._playback_intent_active = False
            await self.mqtt_client.publish_audio_command("pause", {})
        elif current_state == "paused":
            await self.mqtt_client.publish_audio_command("play", {})
        elif current_state == "stopped" and session_manager.session:
            track = session_manager.get_current_track()
            if track:
                await self.mqtt_client.publish_audio_command(
                    "play",
                    {
                        "track_id": str(track.id),
                        "source_type": track.source_type,
                        "source_uri": track.source_uri,
                        "start_position_ms": 0,
                    },
                )

    async def _handle_next(self) -> None:
        """Handle next button; respects repeat all. Closes current event and creates one per track."""
        sess = session_manager.session
        if not sess or not sess.tracks:
            self._playback_intent_active = False
            await self.mqtt_client.publish_audio_command("stop", {})
            return

        if _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                _close_open_playback_event(db_session, self._audio_status_cache)
                repeat = sess.repeat_mode
                if repeat == "all" and not sess.has_next:
                    sess.reset()
                    first = sess.current_track
                    if first:
                        _create_playback_event_for_current_track(db_session)
                        await self._publish_play_track(first)
                    return
                next_track = session_manager.next_track()
                if next_track:
                    _create_playback_event_for_current_track(db_session)
                    await self._publish_play_track(next_track)
                else:
                    self._playback_intent_active = False
                    await self.mqtt_client.publish_audio_command("stop", {})
            finally:
                db_session.close()
        else:
            repeat = sess.repeat_mode
            if repeat == "all" and not sess.has_next:
                sess.reset()
                first = sess.current_track
                if first:
                    await self._publish_play_track(first)
                return
            next_track = session_manager.next_track()
            if next_track:
                await self._publish_play_track(next_track)
            else:
                self._playback_intent_active = False
                await self.mqtt_client.publish_audio_command("stop", {})

    async def _handle_prev(self) -> None:
        """Handle previous button. Closes current event and creates one per track."""
        if _db_module.db_manager:
            db_session = _db_module.db_manager.get_session()
            try:
                _close_open_playback_event(db_session, self._audio_status_cache)
                prev_track = session_manager.prev_track()
                if prev_track:
                    _create_playback_event_for_current_track(db_session)
                    await self._publish_play_track(prev_track)
            finally:
                db_session.close()
        else:
            prev_track = session_manager.prev_track()
            if prev_track:
                await self._publish_play_track(prev_track)

    async def _handle_repeat_cycle(self) -> None:
        """Cycle repeat mode: none <-> all."""
        current = session_manager.get_repeat_mode()
        next_mode = "all" if current == "none" else "none"
        session_manager.set_repeat_mode(next_mode)
        if self.websocket_manager:
            await self.websocket_manager.broadcast({
                "type": "repeat_mode",
                "data": {"repeat_mode": next_mode},
            })

    async def _handle_shuffle_toggle(self) -> None:
        """Toggle shuffle for current session."""
        new_shuffle = session_manager.toggle_shuffle()
        if self.websocket_manager:
            await self.websocket_manager.broadcast({
                "type": "shuffle_mode",
                "data": {"shuffle": new_shuffle},
            })

    # -------------------------------------------------------------------------
    # Sleep Timer
    # -------------------------------------------------------------------------

    async def _trigger_daily_limit_fade(self) -> None:
        """Run bedtime-style fade then stop (when daily limit exceeded)."""
        self._cancel_bedtime_fade()
        enabled, duration_min, interval_sec, step_pct = read_bedtime_fade_settings()
        if not enabled:
            self.mark_deliberate_stop()
            self._playback_intent_active = False
            await self.mqtt_client.publish_audio_command("stop", {})
            return
        try:
            vol = self._audio_status_cache.get("volume")
            if vol is not None and isinstance(vol, (int, float)):
                initial_volume = max(0, min(100, int(vol)))
            else:
                initial_volume = 50
        except (TypeError, ValueError):
            initial_volume = 50
        self._bedtime_fade_task = asyncio.create_task(
            self._bedtime_fade_coroutine(initial_volume, duration_min, interval_sec, step_pct)
        )
        try:
            await self._bedtime_fade_task
        except asyncio.CancelledError:
            pass
        finally:
            self._bedtime_fade_task = None
        self.mark_deliberate_stop()
        self._playback_intent_active = False
        await self.mqtt_client.publish_audio_command("stop", {})

    def get_sleep_timer_status(self) -> dict[str, Any]:
        """Return current sleep timer status (for REST GET endpoint)."""
        if self._sleep_timer_task and not self._sleep_timer_task.done():
            elapsed_ms = int((time.time() - self._sleep_timer_start_time) * 1000)
            remaining_ms = max(0, self._sleep_timer_duration_ms - elapsed_ms)
            return {"active": True, "remaining_ms": remaining_ms}
        return {"active": False, "remaining_ms": None}

    def _cancel_bedtime_fade(self) -> None:
        """Cancel the bedtime volume fade task if running."""
        if self._bedtime_fade_task and not self._bedtime_fade_task.done():
            self._bedtime_fade_task.cancel()
            self._bedtime_fade_task = None

    async def start_sleep_timer(self, minutes: int) -> None:
        """Start (or restart) the sleep timer for the given number of minutes."""
        if self._sleep_timer_task and not self._sleep_timer_task.done():
            self._sleep_timer_task.cancel()
            try:
                await self._sleep_timer_task
            except asyncio.CancelledError:
                pass
        self._cancel_bedtime_fade()
        self._sleep_timer_task = asyncio.create_task(
            self._sleep_timer_coroutine(minutes)
        )
        enabled, duration_min, interval_sec, step_pct = read_bedtime_fade_settings()
        if enabled:
            try:
                vol = self._audio_status_cache.get("volume")
                if vol is not None and isinstance(vol, (int, float)):
                    initial_volume = max(0, min(100, int(vol)))
                else:
                    initial_volume = 50
            except (TypeError, ValueError):
                initial_volume = 50
            self._bedtime_fade_task = asyncio.create_task(
                self._bedtime_fade_coroutine(initial_volume, duration_min, interval_sec, step_pct)
            )

    async def cancel_sleep_timer(self) -> None:
        """Cancel the running sleep timer."""
        self._cancel_bedtime_fade()
        if self._sleep_timer_task and not self._sleep_timer_task.done():
            self._sleep_timer_task.cancel()
            try:
                await self._sleep_timer_task
            except asyncio.CancelledError:
                pass

    async def _handle_sleep_timer_toggle(self) -> None:
        """Toggle sleep timer: start with configured duration or cancel if running."""
        if self._sleep_timer_task and not self._sleep_timer_task.done():
            await self.cancel_sleep_timer()
        else:
            minutes = read_sleep_timer_minutes()
            await self.start_sleep_timer(minutes)

    async def _bedtime_fade_coroutine(
        self, initial_volume: int, duration_minutes: int, interval_seconds: int, step_percent: float
    ) -> None:
        """Fade volume down to 0 over duration_minutes by step_percent every interval_seconds."""
        current = max(0, initial_volume)
        steps_total = max(1, int(duration_minutes * 60 / interval_seconds))
        step = max(0, min(100, int(step_percent)))
        try:
            for _ in range(steps_total):
                await asyncio.sleep(interval_seconds)
                if self._sleep_timer_task is None or self._sleep_timer_task.done():
                    return
                current = max(0, current - step)
                await self.mqtt_client.publish_audio_command("set-volume", {"volume": current})
                if current <= 0:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self._bedtime_fade_task = None

    async def _sleep_timer_coroutine(self, minutes: int) -> None:
        """Run the sleep timer: broadcast start, wait, then stop playback."""
        self._sleep_timer_start_time = time.time()
        self._sleep_timer_duration_ms = minutes * 60_000
        logger.info("sleep_timer_started", minutes=minutes)

        if self.websocket_manager:
            await self.websocket_manager.broadcast({
                "type": "sleep_timer_status",
                "data": {"active": True, "remaining_ms": self._sleep_timer_duration_ms},
            })
        try:
            await asyncio.sleep(minutes * 60)
            self.mark_deliberate_stop()
            self._playback_intent_active = False
            await self.mqtt_client.publish_audio_command("stop", {})
            logger.info("sleep_timer_fired", minutes=minutes)
        except asyncio.CancelledError:
            logger.info("sleep_timer_cancelled")
        finally:
            self._cancel_bedtime_fade()
            self._sleep_timer_task = None
            if self.websocket_manager:
                await self.websocket_manager.broadcast({
                    "type": "sleep_timer_status",
                    "data": {"active": False, "remaining_ms": None},
                })
