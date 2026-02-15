"""REST API endpoints for audio control."""

import structlog
from fastapi import APIRouter, HTTPException

from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import AudioPlayCommand, AudioVolumeCommand

logger = structlog.get_logger(__name__)
router = APIRouter()

# MQTT client will be injected at startup
_mqtt_client: MQTTClient | None = None


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for audio routes.

    Args:
        mqtt_client: MQTT client instance
    """
    global _mqtt_client
    _mqtt_client = mqtt_client


@router.post("/play")
async def play_audio(command: AudioPlayCommand) -> dict:
    """Start audio playback.

    Args:
        command: Play command with optional track_id/playlist_id

    Returns:
        Success response
    """
    logger.info("api_audio_play", command=command.model_dump())

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    # TODO: Load track/playlist data and create session
    # For now, just forward command
    await _mqtt_client.publish_audio_command("play", command.model_dump())

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

    await _mqtt_client.publish_audio_command("stop", {})

    return {"status": "ok", "message": "Stop command sent"}


@router.post("/next")
async def next_track() -> dict:
    """Skip to next track.

    Returns:
        Success response
    """
    logger.info("api_audio_next")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    # TODO: Use session manager
    await _mqtt_client.publish_audio_command("next", {})

    return {"status": "ok", "message": "Next command sent"}


@router.post("/prev")
async def previous_track() -> dict:
    """Skip to previous track.

    Returns:
        Success response
    """
    logger.info("api_audio_prev")

    if not _mqtt_client:
        raise HTTPException(status_code=500, detail="MQTT client not initialized")

    # TODO: Use session manager
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
