"""REST API endpoints for audio control."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.core.playback_stats import get_today_listened_minutes
from backend_service.core.session_manager import (
    RepeatMode,
    SessionTrack,
    session_manager,
)
from backend_service.core.usage_limits import read_daily_limit_settings
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
_mqtt_handlers: MQTTHandlers | None = None


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for audio routes."""
    global _mqtt_client
    _mqtt_client = mqtt_client


def set_mqtt_handlers(handlers: MQTTHandlers) -> None:
    """Set MQTT handlers for audio routes (needed for sleep timer)."""
    global _mqtt_handlers
    _mqtt_handlers = handlers


def _check_daily_limit(db: Session) -> None:
    """Raise HTTPException 403 if daily limit is enabled and exceeded."""
    enabled, limit_minutes = read_daily_limit_settings()
    if not enabled:
        return
    today_min = get_today_listened_minutes(db)
    if today_min >= limit_minutes:
        raise ApiError(
            status_code=403,
            code="daily_limit_exceeded",
            detail="Daily listening limit exceeded",
        )


class SleepTimerRequest(BaseModel):
    minutes: int = Field(default=30, ge=1, le=480)


class SeekRequest(BaseModel):
    position_ms: int = Field(..., ge=0, description="Target position in milliseconds")


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


@router.get("/status")
async def get_audio_status() -> dict:
    """Return the last known audio status from the in-memory cache.

    Used by the WebUI Player page on mount so it renders immediately
    without waiting for the next WebSocket broadcast.
    """
    status = _mqtt_handlers.last_audio_status if _mqtt_handlers else {}
    if not status:
        return {"state": "stopped"}
    return dict(status)


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
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if _mqtt_handlers:
        _mqtt_handlers.playback_intent_active = True

    start_ms = command.start_position_ms or 0

    if command.stream_id:
        _check_daily_limit(db)
        stream = db.query(Stream).filter(Stream.id == command.stream_id).first()
        if not stream:
            raise ApiError(status_code=404, code="stream_not_found", detail="Stream not found")
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

    if command.podcast_id:
        _check_daily_limit(db)
        podcast = db.query(Podcast).filter(Podcast.id == command.podcast_id).first()
        if not podcast:
            raise ApiError(status_code=404, code="podcast_not_found", detail="Podcast not found")
        episode = (
            db.query(PodcastEpisode)
            .filter(PodcastEpisode.podcast_id == podcast.id)
            .order_by(PodcastEpisode.published_at.desc())
            .first()
        )
        if not episode:
            raise ApiError(status_code=400, code="podcast_no_episodes", detail="Podcast has no episodes")
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

    if not command.track_id and not command.playlist_id:
        current_state = (
            _mqtt_handlers.last_audio_status.get("state", "stopped")
            if _mqtt_handlers
            else "stopped"
        )
        if current_state == "paused":
            await _mqtt_client.publish_audio_command("play", {})
            return {"status": "ok", "message": "Resume from pause"}
        track = session_manager.get_current_track()
        if track:
            _check_daily_limit(db)
            payload = _build_play_payload(track, start_ms)
            await _mqtt_client.publish_audio_command("play", payload)
            return {"status": "ok", "message": "Play command sent"}
        await _mqtt_client.publish_audio_command("play", {})
        return {"status": "ok", "message": "Resume command sent"}

    if command.playlist_id:
        _check_daily_limit(db)
        playlist = db.query(Playlist).filter(Playlist.id == command.playlist_id).first()
        if not playlist:
            raise ApiError(status_code=404, code="playlist_not_found", detail="Playlist not found")
        pts = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.playlist_id == playlist.id)
            .order_by(PlaylistTrack.position)
            .all()
        )
        tracks = [pt.track for pt in pts]
        if not tracks:
            raise ApiError(status_code=400, code="playlist_empty", detail="Playlist is empty")
        session = session_manager.create_session(tracks=tracks, playlist_id=playlist.id)
        first_track = session.current_track
        if first_track is None:  # pragma: no cover - tracks was checked above
            raise ApiError(status_code=400, code="playlist_empty", detail="Playlist is empty")
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

    _check_daily_limit(db)
    db_track = db.query(Track).filter(Track.id == command.track_id).first()
    if not db_track:
        raise ApiError(status_code=404, code="track_not_found", detail="Track not found")
    session_manager.create_session(tracks=[db_track])
    db.add(
        PlaybackEvent(
            started_at=datetime.now(UTC),
            content_type="track",
            track_id=db_track.id,
        )
    )
    db.commit()
    payload = _build_play_payload(db_track, start_ms)
    await _mqtt_client.publish_audio_command("play", payload)
    return {"status": "ok", "message": "Play command sent"}


@router.post("/seek")
async def seek_audio(command: SeekRequest) -> dict:
    """Seek to a specific position in the currently playing/paused track.

    Publishes a play command with the current source_uri and the requested
    start_position_ms.  Returns 409 if no track is active or if a live
    stream is playing (streams have no meaningful seek position).
    """
    logger.info("api_audio_seek", position_ms=command.position_ms)

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if not _mqtt_handlers:
        raise ApiError(status_code=500, code="mqtt_handlers_not_initialized", detail="MQTT handlers not initialized")

    status = _mqtt_handlers.last_audio_status
    state = status.get("state", "stopped")
    source_uri = status.get("source_uri")
    source_type = status.get("source_type", "")
    track_id = status.get("track_id")

    if state not in ("playing", "paused") or not source_uri:
        raise ApiError(status_code=409, code="no_active_playback", detail="No active playback to seek in")

    if source_type == "stream":
        raise ApiError(status_code=409, code="seek_not_supported_live", detail="Cannot seek in a live stream")

    payload = {
        "track_id": str(track_id) if track_id else "",
        "source_type": source_type,
        "source_uri": source_uri,
        "start_position_ms": command.position_ms,
    }
    await _mqtt_client.publish_audio_command("play", payload)
    return {"status": "ok", "position_ms": command.position_ms}


@router.post("/pause")
async def pause_audio() -> dict:
    """Pause audio playback."""
    logger.info("api_audio_pause")

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if _mqtt_handlers:
        _mqtt_handlers.mark_deliberate_stop()
        _mqtt_handlers.playback_intent_active = False

    await _mqtt_client.publish_audio_command("pause", {})
    return {"status": "ok", "message": "Pause command sent"}


@router.post("/stop")
async def stop_audio() -> dict:
    """Stop audio playback."""
    logger.info("api_audio_stop")

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if _mqtt_handlers:
        _mqtt_handlers.mark_deliberate_stop()
        _mqtt_handlers.playback_intent_active = False
    await _mqtt_client.publish_audio_command("stop", {})

    return {"status": "ok", "message": "Stop command sent"}


@router.post("/next")
async def next_track() -> dict:
    """Skip to next track."""
    logger.info("api_audio_next")

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if _mqtt_handlers:
        await _mqtt_handlers.button_handler._handle_next()
    else:
        await _mqtt_client.publish_audio_command("next", {})

    return {"status": "ok", "message": "Next command sent"}


@router.post("/prev")
async def previous_track() -> dict:
    """Skip to previous track."""
    logger.info("api_audio_prev")

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

    if _mqtt_handlers:
        await _mqtt_handlers.button_handler._handle_prev()
    else:
        await _mqtt_client.publish_audio_command("prev", {})

    return {"status": "ok", "message": "Previous command sent"}


@router.post("/volume")
async def set_volume(command: AudioVolumeCommand) -> dict:
    """Set audio volume."""
    logger.info("api_audio_set_volume", volume=command.volume)

    if not _mqtt_client:
        raise ApiError(status_code=500, code="mqtt_not_initialized", detail="MQTT client not initialized")

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
        raise ApiError(status_code=500, code="mqtt_handlers_not_initialized", detail="Handlers not initialized")
    logger.info("api_sleep_timer_start", minutes=command.minutes)
    await _mqtt_handlers.start_sleep_timer(command.minutes)
    return {"status": "ok", "active": True, "minutes": command.minutes}


@router.delete("/sleep-timer")
async def cancel_sleep_timer() -> dict:
    """Cancel the running sleep timer."""
    if not _mqtt_handlers:
        raise ApiError(status_code=500, code="mqtt_handlers_not_initialized", detail="Handlers not initialized")
    logger.info("api_sleep_timer_cancel")
    await _mqtt_handlers.cancel_sleep_timer()
    return {"status": "ok", "active": False}


class RepeatModeRequest(BaseModel):
    mode: RepeatMode


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


@router.get("/devices")
async def get_audio_devices(
    enabled_only: bool = Query(False, description="Return only enabled devices"),
) -> dict:
    """List detected PulseAudio/PipeWire sinks (proxied to audio-service)."""
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
        raise ApiError(status_code=503, code="audio_service_timeout", detail="Audio service timeout") from None
    except httpx.HTTPStatusError as e:
        logger.warning("audio_service_devices_error", status=e.response.status_code)
        raise ApiError(
            status_code=502 if e.response.status_code >= 500 else 400,
            code="audio_service_error",
            detail=e.response.text or "Audio service error",
        ) from e
    except Exception as e:
        logger.warning("audio_service_devices_failed", error=str(e))
        raise ApiError(status_code=503, code="audio_service_unavailable", detail="Audio service unavailable") from e


class SwitchDeviceRequest(BaseModel):
    """Request body for POST /switch-device."""

    sink_name: str | None = Field(default=None, description="PulseAudio/PipeWire sink to switch to")
    alsa_device: str | None = Field(
        default=None,
        description="Deprecated alias for sink_name; kept for backwards compatibility",
    )
    direction: str | None = Field(default=None, description="'next' to cycle devices")


@router.post("/switch-device")
async def switch_audio_device(body: SwitchDeviceRequest) -> dict:
    """Switch audio output sink (proxied to audio-service)."""
    sink_name = body.sink_name or body.alsa_device
    if not sink_name and body.direction != "next":
        raise ApiError(
            status_code=400,
            code="audio_output_target_required",
            detail="Provide sink_name or direction='next'",
        )
    payload = {}
    if sink_name:
        payload["sink_name"] = sink_name
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
        raise ApiError(status_code=503, code="audio_service_timeout", detail="Audio service timeout") from None
    except httpx.HTTPStatusError as e:
        logger.warning("audio_service_switch_device_error", status=e.response.status_code)
        raise ApiError(
            status_code=502 if e.response.status_code >= 500 else 400,
            code="audio_service_error",
            detail=e.response.text or "Audio service error",
        ) from e
    except Exception as e:
        logger.warning("audio_service_switch_device_failed", error=str(e))
        raise ApiError(status_code=503, code="audio_service_unavailable", detail="Audio service unavailable") from e


class TestToneRequest(BaseModel):
    """Request body for POST /test-tone."""

    sink_name: str | None = Field(
        default=None,
        description="Sink to play the tone on; defaults to the active output",
    )


@router.post("/test-tone")
async def play_test_tone(body: TestToneRequest | None = None) -> dict:
    """Play a short test tone (proxied to audio-service).

    Used by the setup wizard to verify the speaker actually works. The tone is
    played alongside any current playback, not instead of it.
    """
    payload = {"sink_name": body.sink_name if body else None}
    # The budget has to exceed the tone plus its start-up time, or the proxy
    # times out while the tone is still playing.
    timeout = AUDIO_SERVICE_TIMEOUT + 10.0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{AUDIO_SERVICE_BASE}/api/v1/test-tone",
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        logger.warning("audio_service_test_tone_timeout")
        raise ApiError(status_code=503, code="audio_service_timeout", detail="Audio service timeout") from None
    except httpx.HTTPStatusError as e:
        logger.warning("audio_service_test_tone_error", status=e.response.status_code)
        raise ApiError(
            status_code=502 if e.response.status_code >= 500 else e.response.status_code,
            code="audio_service_error",
            detail=e.response.text or "Audio service error",
        ) from e
    except Exception as e:
        logger.warning("audio_service_test_tone_failed", error=str(e))
        raise ApiError(status_code=503, code="audio_service_unavailable", detail="Audio service unavailable") from e
