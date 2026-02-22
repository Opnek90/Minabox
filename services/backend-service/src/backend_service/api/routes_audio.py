"""REST API endpoints for audio control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import _last_audio_status, mark_deliberate_stop
from backend_service.core.session_manager import session_manager
from backend_service.models.database import Playlist, PlaylistTrack, Stream, Track
from backend_service.models.schemas import AudioPlayCommand, AudioVolumeCommand

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)
router = APIRouter()

# MQTT client and handlers will be injected at startup
_mqtt_client: MQTTClient | None = None
_mqtt_handlers: "MQTTHandlers | None" = None


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for audio routes."""
    global _mqtt_client
    _mqtt_client = mqtt_client


def set_mqtt_handlers(handlers: "MQTTHandlers") -> None:
    """Set MQTT handlers for audio routes (needed for sleep timer)."""
    global _mqtt_handlers
    _mqtt_handlers = handlers


class SleepTimerRequest(BaseModel):
    minutes: int = Field(default=30, ge=1, le=480)


def _build_play_payload(track: Track, start_position_ms: int = 0) -> dict:
    """Build play command payload for audio service."""
    return {
        "track_id": str(track.id),
        "source_type": track.source_type,
        "source_uri": track.source_uri,
        "start_position_ms": start_position_ms,
    }


@router.post("/play")
async def play_audio(
    command: AudioPlayCommand,
    db: Session = Depends(get_db),
) -> dict:
    """Start audio playback.

    Accepts track_id or playlist_id; loads from DB and creates session as needed.
    If neither is given: resume from pause (empty play) or from current session.
    """
    logger.info("api_audio_play", command=command.model_dump())

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    start_ms = command.start_position_ms or 0

    # Play by stream_id: load stream and play (no session)
    if command.stream_id:
        stream = db.query(Stream).filter(Stream.id == command.stream_id).first()
        if not stream:
            raise HTTPException(status_code=404, detail="Stream not found")
        payload = {
            "track_id": f"stream-{stream.id}",
            "source_type": "stream",
            "source_uri": stream.source_uri,
            "start_position_ms": start_ms,
        }
        await _mqtt_client.publish_audio_command("play", payload)
        return {"status": "ok", "message": "Stream playback started"}

    # No track/playlist/stream: resume from pause, from session, or from audio service persisted state
    if not command.track_id and not command.playlist_id:
        current_state = _last_audio_status.get("state", "stopped")
        if current_state == "paused":
            await _mqtt_client.publish_audio_command("play", {})
            return {"status": "ok", "message": "Resume from pause"}
        track = session_manager.get_current_track()
        if track:
            payload = _build_play_payload(track, start_ms)
            await _mqtt_client.publish_audio_command("play", payload)
            return {"status": "ok", "message": "Play command sent"}
        # Let audio service resume from its persisted state (e.g. last stream or file)
        await _mqtt_client.publish_audio_command("play", {})
        return {"status": "ok", "message": "Resume command sent"}

    # Play by playlist_id: load playlist, create session, play first track
    if command.playlist_id:
        playlist = db.query(Playlist).filter(Playlist.id == command.playlist_id).first()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        pts = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.playlist_id == playlist.id)
            .order_by(PlaylistTrack.position)
            .all()
        )
        tracks = [pt.track for pt in pts]
        if not tracks:
            raise HTTPException(status_code=400, detail="Playlist is empty")
        session_manager.create_session(tracks=tracks, playlist_id=playlist.id)
        payload = _build_play_payload(tracks[0], start_ms)
        await _mqtt_client.publish_audio_command("play", payload)
        return {"status": "ok", "message": "Playlist playback started"}

    # Play by track_id: load track and play
    track = db.query(Track).filter(Track.id == command.track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    session_manager.create_session(tracks=[track])
    payload = _build_play_payload(track, start_ms)
    await _mqtt_client.publish_audio_command("play", payload)
    return {"status": "ok", "message": "Play command sent"}


@router.post("/pause")
async def pause_audio() -> dict:
    """Pause audio playback.

    Returns:
        Success response
    """
    logger.info("api_audio_pause")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    await _mqtt_client.publish_audio_command("pause", {})

    return {"status": "ok", "message": "Pause command sent"}


@router.post("/stop")
async def stop_audio() -> dict:
    """Stop audio playback.

    Returns:
        Success response
    """
    logger.info("api_audio_stop")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    mark_deliberate_stop()
    await _mqtt_client.publish_audio_command("stop", {})

    return {"status": "ok", "message": "Stop command sent"}


@router.post("/next")
async def next_track() -> dict:
    """Skip to next track.

    Uses session manager (same logic as button next): advance index and send
    audio/play with the new track, or audio/stop at end of playlist.
    """
    logger.info("api_audio_next")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    if _mqtt_handlers:
        await _mqtt_handlers._handle_next()
    else:
        await _mqtt_client.publish_audio_command("next", {})

    return {"status": "ok", "message": "Next command sent"}


@router.post("/prev")
async def previous_track() -> dict:
    """Skip to previous track.

    Uses session manager (same logic as button prev): go back one track and
    send audio/play with that track.
    """
    logger.info("api_audio_prev")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    if _mqtt_handlers:
        await _mqtt_handlers._handle_prev()
    else:
        await _mqtt_client.publish_audio_command("prev", {})

    return {"status": "ok", "message": "Previous command sent"}


@router.post("/volume")
async def set_volume(command: AudioVolumeCommand) -> dict:
    """Set audio volume.

    Args:
        command: Volume command with level (0-100)

    Returns:
        Success response
    """
    logger.info("api_audio_set_volume", volume=command.volume)

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    await _mqtt_client.publish_audio_command("set-volume", {"volume": command.volume})

    return {"status": "ok", "message": f"Volume set to {command.volume}"}


@router.get("/sleep-timer")
async def get_sleep_timer() -> dict:
    """Return current sleep timer status."""
    if not _mqtt_handlers:
        return {"active": False, "remaining_ms": None}
    return _mqtt_handlers.get_sleep_timer_status()


@router.post("/sleep-timer")
async def start_sleep_timer(command: SleepTimerRequest) -> dict:
    """Start (or restart) the sleep timer."""
    if not _mqtt_handlers:
        raise HTTPException(status_code=500, detail="Handlers not initialized")
    logger.info("api_sleep_timer_start", minutes=command.minutes)
    await _mqtt_handlers.start_sleep_timer(command.minutes)
    return {"status": "ok", "active": True, "minutes": command.minutes}


@router.delete("/sleep-timer")
async def cancel_sleep_timer() -> dict:
    """Cancel the running sleep timer."""
    if not _mqtt_handlers:
        raise HTTPException(status_code=500, detail="Handlers not initialized")
    logger.info("api_sleep_timer_cancel")
    await _mqtt_handlers.cancel_sleep_timer()
    return {"status": "ok", "active": False}
