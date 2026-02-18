"""MQTT message handlers for Backend Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

import backend_service.core.db_manager as _db_module
from backend_service.core.session_manager import session_manager
from backend_service.exceptions import ContentNotFoundError
from backend_service.models.database import Playlist, PlaylistTrack, Tag, Track

if TYPE_CHECKING:
    from backend_service.api.websocket import WebSocketManager
    from backend_service.core.mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)

# Last audio status (updated by handle_audio_status); used by routes_audio for play-after-pause
_last_audio_status: dict[str, Any] = {}


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
        logger.info("mqtt_handlers_initialized")

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

        logger.info("rfid_tag_scanned_received", tag_id=tag_id)

        # Check if db_manager is initialized
        if not _db_module.db_manager:
            logger.error("db_manager_not_initialized")
            return

        # Lookup tag in database
        session = _db_module.db_manager.get_session()
        try:
            tag = session.query(Tag).filter(Tag.tag_id == tag_id).first()

            if not tag:
                logger.warning("tag_not_found", tag_id=tag_id)
                # Broadcast to WebUI
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

            logger.info(
                "tag_found",
                tag_id=tag_id,
                content_type=tag.content_type,
                content_id=tag.content_id,
            )

            # Load content and create session
            if tag.content_type == "playlist":
                await self._handle_playlist_playback(session, tag.content_id)
            elif tag.content_type == "track":
                await self._handle_track_playback(session, tag.content_id)

            # Broadcast to WebUI
            if self.websocket_manager:
                await self.websocket_manager.broadcast(
                    {
                        "type": "rfid_scanned",
                        "data": {
                            "tag_id": tag_id,
                            "content_type": tag.content_type,
                            "content_name": tag.name,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    }
                )

        finally:
            session.close()

    async def _handle_playlist_playback(
        self, session: Session, playlist_id: int
    ) -> None:
        """Start playlist playback.

        Args:
            session: Database session
            playlist_id: Playlist ID
        """
        # Load playlist with tracks
        playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()
        if not playlist:
            logger.error("playlist_not_found", playlist_id=playlist_id)
            raise ContentNotFoundError(f"Playlist {playlist_id} not found")

        # Load tracks in order
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

        # Create session
        session_manager.create_session(tracks=tracks, playlist_id=playlist_id)

        # Start playback with first track (audio service expects track_id as str)
        first_track = tracks[0]
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

    async def _handle_track_playback(self, session: Session, track_id: int) -> None:
        """Start single track playback.

        Args:
            session: Database session
            track_id: Track ID
        """
        track = session.query(Track).filter(Track.id == track_id).first()
        if not track:
            logger.error("track_not_found", track_id=track_id)
            raise ContentNotFoundError(f"Track {track_id} not found")

        # Create session with single track
        session_manager.create_session(tracks=[track])

        # Start playback (audio service expects track_id as str)
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

    async def handle_rfid_tag_scanned_learning(
        self,
        topic: str,
        data: dict[str, Any],
    ) -> None:
        """Handle RFID tag scanned event (learning mode).

        Args:
            topic: MQTT topic
            data: Event data with tag_id, reader_id, timestamp
        """
        tag_id = data.get("tag_id")
        if not tag_id:
            logger.warning("rfid_tag_scanned_learning_missing_tag_id", data=data)
            return

        logger.info("rfid_tag_scanned_learning_received", tag_id=tag_id)

        # Check if tag already exists in DB (best-effort; broadcast even if DB unavailable)
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

        # Broadcast to WebUI (always, regardless of DB state)
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

    async def handle_audio_status(self, topic: str, data: dict[str, Any]) -> None:
        """Handle audio status update.

        Enriches status with track title/artist/album from DB for WebUI display.

        Args:
            topic: MQTT topic
            data: Status data
        """
        logger.debug("audio_status_received", data=data)

        # Cache status (module-level for routes_audio play-after-pause)
        self._audio_status_cache = data
        _last_audio_status.clear()
        _last_audio_status.update(data)

        # Enrich with track metadata from DB (audio service only sends track_id)
        payload = dict(data)
        track_id_raw = payload.get("track_id")
        if track_id_raw and _db_module.db_manager:
            try:
                tid = int(track_id_raw)
            except (TypeError, ValueError):
                tid = None
            if tid is not None:
                session = _db_module.db_manager.get_session()
                try:
                    track = session.query(Track).filter(Track.id == tid).first()
                    if track:
                        payload["track_title"] = track.title
                        payload["track_artist"] = track.artist
                        payload["track_album"] = track.album
                finally:
                    session.close()

        # Broadcast to WebUI
        if self.websocket_manager:
            await self.websocket_manager.broadcast(
                {
                    "type": "audio_status",
                    "data": payload,
                }
            )

    async def handle_button_action(self, topic: str, data: dict[str, Any]) -> None:
        """Handle button action event.

        Args:
            topic: MQTT topic (e.g., minabox/box1/button/play-pause)
            data: Event data
        """
        # Extract action from topic
        action = topic.split("/")[-1]
        logger.info("button_action_received", action=action, data=data)

        # Handle different button actions
        if action == "play-pause":
            await self._handle_play_pause()
        elif action == "next":
            await self._handle_next()
        elif action == "prev":
            await self._handle_prev()
        elif action in ("volume-up", "volume-down"):
            # Button service already sends volume commands directly to audio for low latency
            pass
        elif action in ("mute", "mute-toggle"):
            await self.mqtt_client.publish_audio_command("mute-toggle", {})

        # Broadcast to WebUI
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
            await self.mqtt_client.publish_audio_command("pause", {})
        elif current_state == "paused":
            # Resume from paused position (empty payload = audio service resumes with last_position_ms)
            await self.mqtt_client.publish_audio_command("play", {})
        elif current_state == "stopped" and session_manager.session:
            # Resume from session (audio service expects track_id as str)
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
        """Handle next button (audio service expects track_id as str)."""
        next_track = session_manager.next_track()
        if next_track:
            await self.mqtt_client.publish_audio_command(
                "play",
                {
                    "track_id": str(next_track.id),
                    "source_type": next_track.source_type,
                    "source_uri": next_track.source_uri,
                    "start_position_ms": 0,
                },
            )
        else:
            # End of playlist
            await self.mqtt_client.publish_audio_command("stop", {})

    async def _handle_prev(self) -> None:
        """Handle previous button (audio service expects track_id as str)."""
        prev_track = session_manager.prev_track()
        if prev_track:
            await self.mqtt_client.publish_audio_command(
                "play",
                {
                    "track_id": str(prev_track.id),
                    "source_type": prev_track.source_type,
                    "source_uri": prev_track.source_uri,
                    "start_position_ms": 0,
                },
            )
