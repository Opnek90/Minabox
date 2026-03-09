"""RFID MQTT handlers."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

import backend_service.core.db_manager as _db_module
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.resume_position import get_resume_position
from backend_service.core.rfid_settings import (
    read_resume_on_tag_rescan,
    read_stop_playback_on_tag_remove,
)
from backend_service.core.session_manager import session_manager
from backend_service.core.usage_limits import (
    is_within_allowed_usage_time,
    read_allowed_usage_times,
    read_daily_limit_settings,
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
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)

TAG_SCAN_COOLDOWN_SEC = 5.0

class RFIDHandler:
    def __init__(self, dispatcher: "MQTTHandlers") -> None:
        self.dispatcher = dispatcher
        self.tag_scan_cooldown_until: dict[str, float] = {}
        self.last_played_tag_id: str | None = None
        self.last_played_tag_time: float = 0.0

    async def handle_rfid_tag_scanned(self, topic: str, data: dict[str, Any]) -> None:
        tag_id = data.get("tag_id")
        if not tag_id:
            logger.warning("rfid_tag_scanned_missing_tag_id", data=data)
            return

        now_sec = time.time()

        if now_sec < self.tag_scan_cooldown_until.get(tag_id, 0):
            logger.info("rfid_tag_scan_ignored_cooldown", tag_id=tag_id, cooldown_sec=TAG_SCAN_COOLDOWN_SEC)
            return

        current_state = self.dispatcher.audio_status_cache.get("state")
        if current_state == "playing" and self.last_played_tag_id == tag_id:
            time_since_start = now_sec - self.last_played_tag_time
            if time_since_start < 15.0:
                logger.info("rfid_tag_scan_ignored_already_playing", tag_id=tag_id, time_since_start=time_since_start)
                self.tag_scan_cooldown_until[tag_id] = now_sec + 2.0
                return

        logger.info("rfid_tag_scanned_received", tag_id=tag_id)

        if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
            self.dispatcher.stream_reconnect_task.cancel()
            self.dispatcher.stream_reconnect_attempts = 0

        if not _db_module.db_manager:
            logger.error("db_manager_not_initialized")
            return

        session = _db_module.db_manager.get_session()
        try:
            tag = session.query(Tag).filter(Tag.tag_id == tag_id).first()

            if not tag:
                logger.warning("tag_not_found", tag_id=tag_id)
                unknown_tag_topic = self.dispatcher.mqtt_client.config.get_mqtt_topic("rfid", "unknown-tag")
                await self.dispatcher.mqtt_client.publish(
                    unknown_tag_topic,
                    {"tag_id": tag_id, "timestamp": datetime.now(UTC).isoformat()},
                )
                if self.dispatcher.websocket_manager:
                    await self.dispatcher.websocket_manager.broadcast(
                        {
                            "type": "tag_not_found",
                            "data": {"tag_id": tag_id, "timestamp": datetime.now(UTC).isoformat()},
                        }
                    )
                return

            now = datetime.now(UTC)

            slots = read_allowed_usage_times()
            if slots and not is_within_allowed_usage_time(now, slots):
                logger.info("tag_scanned_outside_allowed_time", tag_id=tag_id)
                await self.dispatcher.notify_usage_denied(tag_id, now)
                return

            daily_enabled, daily_minutes = read_daily_limit_settings()
            if daily_enabled:
                today_min = get_today_listened_minutes(session)
                if today_min >= daily_minutes:
                    logger.info("tag_scanned_daily_limit_exceeded", tag_id=tag_id)
                    await self.dispatcher.notify_usage_denied(tag_id, now)
                    return

            tag.last_scanned_at = now
            session.commit()

            logger.info("tag_found", tag_id=tag_id, content_type=tag.content_type, content_id=tag.content_id)

            self.last_played_tag_id = tag_id
            self.last_played_tag_time = now_sec
            self.dispatcher.playback_intent_active = True
            self.dispatcher.stream_reconnect_attempts = 0

            self.tag_scan_cooldown_until[tag_id] = now_sec + TAG_SCAN_COOLDOWN_SEC
            self.tag_scan_cooldown_until = {
                tid: until for tid, until in self.tag_scan_cooldown_until.items() if until > now_sec
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

            if self.dispatcher.websocket_manager:
                await self.dispatcher.websocket_manager.broadcast(
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

    async def _handle_playlist_playback(self, session: Session, playlist_id: int, tag_id: int | None = None) -> None:
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()
        if not playlist:
            logger.error("playlist_not_found", playlist_id=playlist_id)
            raise ContentNotFoundError(f"Playlist {playlist_id} not found")

        playlist_tracks = session.query(PlaylistTrack).filter(PlaylistTrack.playlist_id == playlist_id).order_by(PlaylistTrack.position).all()
        if not playlist_tracks:
            logger.warning("playlist_empty", playlist_id=playlist_id)
            return

        tracks = [pt.track for pt in playlist_tracks]
        session_manager.create_session(tracks=tracks, playlist_id=playlist_id, shuffle=True)
        first_track = session_manager.session.current_track if session_manager.session else tracks[0]

        event = PlaybackEvent(started_at=datetime.now(UTC), content_type="playlist", playlist_id=playlist_id, tag_id=tag_id)
        session.add(event)
        session.commit()

        await self.dispatcher.mqtt_client.publish_audio_command(
            "play",
            {"track_id": str(first_track.id), "source_type": first_track.source_type, "source_uri": first_track.source_uri, "start_position_ms": 0}
        )
        logger.info("playlist_playback_started", playlist_id=playlist_id, track_count=len(tracks), first_track_id=first_track.id)

    async def _handle_track_playback(self, session: Session, track_id: int, tag_id: int | None = None) -> None:
        track = session.query(Track).filter(Track.id == track_id).first()
        if not track:
            logger.error("track_not_found", track_id=track_id)
            raise ContentNotFoundError(f"Track {track_id} not found")

        session_manager.create_session(tracks=[track])
        event = PlaybackEvent(started_at=datetime.now(UTC), content_type="track", track_id=track_id, tag_id=tag_id)
        session.add(event)
        session.commit()

        resume_enabled = read_resume_on_tag_rescan()
        resume_pos = get_resume_position(session, track.source_uri) if resume_enabled else 0
        logger.info(
            "track_playback_started",
            track_id=track_id,
            title=track.title,
            resume_enabled=resume_enabled,
            resume_pos_ms=resume_pos,
        )

        await self.dispatcher.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": str(track.id),
                "source_type": track.source_type,
                "source_uri": track.source_uri,
                "start_position_ms": resume_pos,
            }
        )

    async def _handle_stream_playback(self, session: Session, stream_id: int, tag_id: int | None = None) -> None:
        stream = session.query(Stream).filter(Stream.id == stream_id).first()
        if not stream:
            logger.error("stream_not_found", stream_id=stream_id)
            raise ContentNotFoundError(f"Stream {stream_id} not found")

        if session_manager.session:
            session_manager.session.reset()

        event = PlaybackEvent(started_at=datetime.now(UTC), content_type="stream", stream_id=stream_id, tag_id=tag_id)
        session.add(event)
        session.commit()

        await self.dispatcher.mqtt_client.publish_audio_command(
            "play",
            {"track_id": f"stream-{stream.id}", "source_type": "stream", "source_uri": stream.source_uri, "start_position_ms": 0}
        )
        logger.info("stream_playback_started", stream_id=stream_id, title=stream.title)

    async def _handle_podcast_playback(self, session: Session, podcast_id: int, tag_id: int | None = None) -> None:
        podcast = session.query(Podcast).filter(Podcast.id == podcast_id).first()
        if not podcast:
            logger.error("podcast_not_found", podcast_id=podcast_id)
            raise ContentNotFoundError(f"Podcast {podcast_id} not found")

        episode = session.query(PodcastEpisode).filter(PodcastEpisode.podcast_id == podcast_id).order_by(PodcastEpisode.published_at.desc()).first()
        if not episode:
            logger.warning("podcast_no_episodes", podcast_id=podcast_id)
            return

        podcast.last_played_at = datetime.now(UTC)
        event = PlaybackEvent(started_at=datetime.now(UTC), content_type="podcast", podcast_id=podcast_id, tag_id=tag_id)
        session.add(event)
        session.commit()

        if session_manager.session:
            session_manager.session.reset()

        resume_enabled = read_resume_on_tag_rescan()
        resume_pos = get_resume_position(session, episode.source_uri) if resume_enabled else 0
        logger.info(
            "podcast_playback_started",
            podcast_id=podcast_id,
            episode_id=episode.id,
            title=episode.title,
            resume_enabled=resume_enabled,
            resume_pos_ms=resume_pos,
        )

        await self.dispatcher.mqtt_client.publish_audio_command(
            "play",
            {
                "track_id": f"podcast-{podcast.id}",
                "source_type": "podcast",
                "source_uri": episode.source_uri,
                "start_position_ms": resume_pos,
            }
        )

    async def handle_rfid_tag_scanned_learning(self, topic: str, data: dict[str, Any]) -> None:
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
                logger.info("rfid_tag_learning_result", tag_id=tag_id, already_assigned=already_assigned)
            finally:
                session.close()
        else:
            logger.warning("db_manager_not_initialized_using_fallback", tag_id=tag_id)

        if self.dispatcher.websocket_manager:
            await self.dispatcher.websocket_manager.broadcast(
                {
                    "type": "rfid_scanned_learning",
                    "data": {"tag_id": tag_id, "already_assigned": already_assigned, "timestamp": datetime.now(UTC).isoformat()},
                }
            )

    async def handle_rfid_tag_removed(self, topic: str, data: dict[str, Any]) -> None:
        tag_id = data.get("tag_id", "")

        if self.last_played_tag_id == tag_id:
            self.last_played_tag_id = None

        if not read_stop_playback_on_tag_remove():
            return

        logger.info("rfid_tag_removed_stopping_playback", tag_id=tag_id)

        if self.dispatcher.stream_reconnect_task and not self.dispatcher.stream_reconnect_task.done():
            self.dispatcher.stream_reconnect_task.cancel()

        self.dispatcher.mark_deliberate_stop()
        self.dispatcher.playback_intent_active = False
        await self.dispatcher.mqtt_client.publish_audio_command("stop", {})
