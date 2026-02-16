"""FastAPI routes for the Audio Service.

Provides health check and status endpoints.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..audio_backend import AudioStatus

logger = structlog.get_logger(__name__)

router = APIRouter()

# Global reference to service (will be set by main.py)
_service = None


def set_service(service) -> None:
    """Set global service reference for route handlers.

    Args:
        service: AudioService instance
    """
    global _service
    _service = service


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    service: str
    uptime_seconds: float
    mqtt_connected: bool
    vlc_initialized: bool
    timestamp: str


class StatusResponse(BaseModel):
    """Audio status response schema."""

    status: AudioStatus
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        HealthResponse with service health information
    """
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        uptime = _service.get_uptime()
        mqtt_connected = _service.is_mqtt_connected()
        vlc_initialized = _service.is_vlc_initialized()

        status = "healthy" if (mqtt_connected and vlc_initialized) else "degraded"

        return HealthResponse(
            status=status,
            service="audio",
            uptime_seconds=uptime,
            mqtt_connected=mqtt_connected,
            vlc_initialized=vlc_initialized,
            timestamp=datetime.now(UTC).isoformat(),
        )

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get current audio playback status.

    Returns:
        StatusResponse with current audio status
    """
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        audio_status = await _service.get_audio_status()

        return StatusResponse(
            status=audio_status,
            timestamp=datetime.now(UTC).isoformat(),
        )

    except Exception as e:
        logger.error("get_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
