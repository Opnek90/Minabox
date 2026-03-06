"""FastAPI routes for the Audio Service.

Provides health check, status, devices, and switch-device endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, Query

from ..config_schema import AppConfig
from ..core import AudioService
from ..models import (
    DeviceItem,
    DevicesResponse,
    HealthResponse,
    StatusResponse,
    SwitchDeviceBody,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# Global reference to service (set by create_app for route handlers)
_service: AudioService | None = None


def set_service(service: AudioService | None) -> None:
    """Set global service reference for route handlers."""
    global _service
    _service = service


def create_app(service: AudioService, config: AppConfig) -> FastAPI:
    """Create FastAPI application with health at root and API routes under /api/v1."""
    app = FastAPI(
        title="Minabox Audio Service",
        description="VLC-based audio player with MQTT control",
        version="0.1.0",
    )

    set_service(service)

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        if service is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        try:
            uptime = service.get_uptime()
            mqtt_connected = service.is_mqtt_connected()
            vlc_initialized = service.is_vlc_initialized()
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

    app.include_router(router, prefix="/api/v1")
    return app


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
    target = body.sink_name or body.alsa_device
    if not target and body.direction != "next":
        raise HTTPException(
            status_code=400,
            detail="Provide sink_name or direction='next'",
        )
    try:
        status = await _service.switch_output_device(
            sink_name=target,
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
