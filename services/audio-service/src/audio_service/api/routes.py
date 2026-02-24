"""FastAPI routes for the Audio Service.

Provides health check, status, devices, and switch-device endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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


class DeviceItem(BaseModel):
    """Single detected audio device."""

    id: str
    name: str
    card_name: str
    alsa_device: str
    priority: int


class DevicesResponse(BaseModel):
    """List of detected audio devices."""

    devices: list[DeviceItem]


class SwitchDeviceBody(BaseModel):
    """Request body for POST /switch-device."""

    alsa_device: str | None = Field(default=None, description="Pulse sink name to switch to")
    direction: str | None = Field(default=None, description="'next' to cycle to next enabled device")


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


@router.get("/devices", response_model=DevicesResponse)
async def get_devices(
    enabled_only: bool = Query(False, description="Return only devices in enabled_output_devices"),
) -> DevicesResponse:
    """List detected Pulse sinks (refresh on each call)."""
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        items = await _service.get_audio_devices(enabled_only=enabled_only)
        return DevicesResponse(
            devices=[DeviceItem(**d) for d in items],
        )
    except Exception as e:
        logger.error("get_devices_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switch-device", response_model=StatusResponse)
async def switch_device(body: SwitchDeviceBody) -> StatusResponse:
    """Switch output device; re-initializes VLC and optionally resumes playback."""
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if not body.alsa_device and body.direction != "next":
        raise HTTPException(
            status_code=400,
            detail="Provide alsa_device or direction='next'",
        )
    try:
        status = await _service.switch_output_device(
            alsa_device=body.alsa_device,
            direction=body.direction,
        )
        return StatusResponse(
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("switch_device_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
