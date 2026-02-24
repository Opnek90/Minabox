"""REST API endpoints for audio control."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.mqtt_handlers import _last_audio_status, mark_deliberate_stop
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.session_manager import SessionTrack, session_manager
from backend_service.models.database import (
    PlaybackEvent,
    Playlist,
    PlaylistTrack,
    Podcast,
    PodcastEpisode,
    Stream,
    Track,
)
from backend_service.models.schemas import AudioPlayCommand, AudioVolumeCommand

if TYPE_CHECKING:
    from backend_service.core.mqtt_handlers import MQTTHandlers

logger = structlog.get_logger(__name__)
router = APIRouter()

AUDIO_SERVICE_BASE = "http://audio:8003"
AUDIO_SERVICE_TIMEOUT = 10.0

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


def _read_daily_limit() -> tuple[bool, int]:
    """Read daily_limit_enabled and daily_limit_minutes from general_settings.json."""
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            enabled = bool(data.get("daily_limit_enabled", False))
            minutes = max(1, min(1440, int(data.get("daily_limit_minutes", 120))))
            return (enabled, minutes)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        pass
    return (False, 120)


def _check_daily_limit(db: Session) -> None:
    """Raise HTTPException 403 if daily limit is enabled and exceeded."""
    enabled, limit_minutes = _read_daily_limit()
    if not enabled:
        return
    today_min = get_today_listened_minutes(db)
    if today_min >= limit_minutes:
        raise HTTPException(
            status_code=403,
            detail="Daily listening limit exceeded",
        )


class SleepTimerRequest(BaseModel):
    minutes: int = Field(default=30, ge=1, le=480)


def _build_play_payload(
    track: Track | SessionTrack, start_position_ms: int = 0
) -> dict:
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
        _check_daily_limit(db)
        stream = db.query(Stream).filter(Stream.id == command.stream_id).first()
        if not stream:
            raise HTTPException(status_code=404, detail="Stream not found")
        db.add(
            PlaybackEvent(
                started_at=datetime.now(UTC),
                content_type="stream",
                stream_id=stream.id,
            )
        )
        db.commit()
        payload = {
            "track_id": f"stream-{stream.id}",
            "source_type": "stream",
            "source_uri": stream.source_uri,
            "start_position_ms": start_ms,
        }
        await _mqtt_client.publish_audio_command("play", payload)
        return {"status": "ok", "message": "Stream playback started"}

    # Play by podcast_id: load podcast, play latest episode (no session)
    if command.podcast_id:
        _check_daily_limit(db)
        podcast = db.query(Podcast).filter(Podcast.id == command.podcast_id).first()
        if not podcast:
            raise HTTPException(status_code=404, detail="Podcast not found")
        episode = (
            db.query(PodcastEpisode)
            .filter(PodcastEpisode.podcast_id == podcast.id)
            .order_by(PodcastEpisode.published_at.desc())
            .first()
        )
        if not episode:
            raise HTTPException(status_code=400, detail="Podcast has no episodes")
        podcast.last_played_at = datetime.now(UTC)
        db.add(
            PlaybackEvent(
                started_at=datetime.now(UTC),
                content_type="podcast",
                podcast_id=podcast.id,
            )
        )
        db.commit()
        payload = {
            "track_id": f"podcast-{podcast.id}",
            "source_type": "podcast",
            "source_uri": episode.source_uri,
            "start_position_ms": start_ms,
        }
        await _mqtt_client.publish_audio_command("play", payload)
        return {"status": "ok", "message": "Podcast playback started"}

    # No track/playlist/stream/podcast: resume from pause, from session, or from audio service persisted state
    if not command.track_id and not command.playlist_id:
        current_state = _last_audio_status.get("state", "stopped")
        if current_state == "paused":
            await _mqtt_client.publish_audio_command("play", {})
            return {"status": "ok", "message": "Resume from pause"}
        track = session_manager.get_current_track()
        if track:
            _check_daily_limit(db)
            payload = _build_play_payload(track, start_ms)
            await _mqtt_client.publish_audio_command("play", payload)
            return {"status": "ok", "message": "Play command sent"}
        # Let audio service resume from its persisted state (e.g. last stream or file)
        await _mqtt_client.publish_audio_command("play", {})
        return {"status": "ok", "message": "Resume command sent"}

    # Play by playlist_id: load playlist, create session, play first track
    if command.playlist_id:
        _check_daily_limit(db)
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
        session_manager.create_session(tracks=tracks, playlist_id=playlist.id, shuffle=True)
        sess = session_manager.session
        first_track = sess.current_track
        db.add(
            PlaybackEvent(
                started_at=datetime.now(UTC),
                content_type="playlist",
                playlist_id=playlist.id,
            )
        )
        db.commit()
        payload = _build_play_payload(first_track, start_ms)
        await _mqtt_client.publish_audio_command("play", payload)
        return {"status": "ok", "message": "Playlist playback started"}

    # Play by track_id: load track and play
    _check_daily_limit(db)
    track = db.query(Track).filter(Track.id == command.track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    session_manager.create_session(tracks=[track])
    db.add(
        PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="track",
            track_id=track.id,
        )
    )
    db.commit()
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


class RepeatModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(none|all)$")


@router.get("/session")
async def get_audio_session() -> dict:
    """Return current queue/session and repeat mode (for WebUI 'what's next')."""
    queue = session_manager.get_queue()
    repeat_mode = session_manager.get_repeat_mode()
    sess = session_manager.session
    shuffle = sess.shuffle if sess else False
    return {
        "queue": queue if queue else [],
        "repeat_mode": repeat_mode,
        "shuffle": shuffle,
    }


@router.post("/repeat")
async def set_repeat_mode(command: RepeatModeRequest) -> dict:
    """Set repeat mode (none, all)."""
    session_manager.set_repeat_mode(command.mode)
    return {"status": "ok", "repeat_mode": command.mode}


class ShuffleRequest(BaseModel):
    shuffle: bool = Field(..., description="Shuffle on/off")


@router.post("/shuffle")
async def set_shuffle_mode(command: ShuffleRequest) -> dict:
    """Set shuffle for current session."""
    session_manager.set_shuffle(command.shuffle)
    sess = session_manager.session
    return {"status": "ok", "shuffle": sess.shuffle if sess else False}


# ── Audio output device (proxy to audio-service) ───────────────────────────

@router.get("/devices")
async def get_audio_devices(
    enabled_only: bool = Query(False, description="Return only enabled devices"),
) -> dict:
    """List detected ALSA audio devices (proxied to audio-service)."""
    try:
        async with httpx.AsyncClient(timeout=AUDIO_SERVICE_TIMEOUT) as client:
            r = await client.get(
                f"{AUDIO_SERVICE_BASE}/api/v1/devices",
                params={"enabled_only": enabled_only},
            )
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        logger.warning("audio_service_devices_timeout")
        raise HTTPException(status_code=503, detail="Audio service timeout")
    except httpx.HTTPStatusError as e:
        logger.warning("audio_service_devices_error", status=e.response.status_code)
        raise HTTPException(
            status_code=502 if e.response.status_code >= 500 else 400,
            detail=e.response.text or "Audio service error",
        )
    except Exception as e:
        logger.warning("audio_service_devices_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Audio service unavailable")


class SwitchDeviceRequest(BaseModel):
    """Request body for POST /switch-device."""

    alsa_device: str | None = Field(default=None, description="ALSA device to switch to")
    direction: str | None = Field(default=None, description="'next' to cycle devices")


@router.post("/switch-device")
async def switch_audio_device(body: SwitchDeviceRequest) -> dict:
    """Switch audio output device (proxied to audio-service)."""
    if not body.alsa_device and body.direction != "next":
        raise HTTPException(
            status_code=400,
            detail="Provide alsa_device or direction='next'",
        )
    payload = {}
    if body.alsa_device:
        payload["alsa_device"] = body.alsa_device
    if body.direction:
        payload["direction"] = body.direction
    try:
        async with httpx.AsyncClient(timeout=AUDIO_SERVICE_TIMEOUT) as client:
            r = await client.post(
                f"{AUDIO_SERVICE_BASE}/api/v1/switch-device",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        logger.warning("audio_service_switch_device_timeout")
        raise HTTPException(status_code=503, detail="Audio service timeout")
    except httpx.HTTPStatusError as e:
        logger.warning("audio_service_switch_device_error", status=e.response.status_code)
        raise HTTPException(
            status_code=502 if e.response.status_code >= 500 else 400,
            detail=e.response.text or "Audio service error",
        )
    except Exception as e:
        logger.warning("audio_service_switch_device_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Audio service unavailable")
