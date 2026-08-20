"""FastAPI routes for the Audio Service.

Provides health check, status, devices, and switch-device endpoints.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, Query
from shared_lib.version import get_version

from ..config_schema import AppConfig
from ..core import AudioService
from ..models import (
    DeviceItem,
    DevicesResponse,
    HealthResponse,
    StatusResponse,
    SwitchDeviceBody,
    TestToneBody,
    TestToneResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# Mitgelieferter Testton fuer den Ersteinrichtungs-Assistenten. Bewusst ein
# eigenes Asset und kein Titel aus der Mediathek: auf einer frisch
# aufgesetzten Box ist die leer.
TEST_TONE_PATH = Path(
    os.getenv("AUDIO_TEST_TONE_PATH", "/app/assets/test-tone.wav")
)
TEST_TONE_TIMEOUT = 15.0

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
                version=get_version(),
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
        # Explicit user-facing query: bypass the detector cache so a speaker
        # switched on a second ago actually shows up.
        items = await _service.get_audio_devices(
            enabled_only=enabled_only, force_refresh=True
        )
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


@router.post("/test-tone", response_model=TestToneResponse)
async def play_test_tone(body: TestToneBody) -> TestToneResponse:
    """Play a short test tone on the given (or active) sink.

    Deliberately routed through paplay instead of the VLC backend: the wizard
    must be able to check the speaker while something is playing, and taking
    over the player would stop the music and leave the session in a state the
    user did not ask for.
    """
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not TEST_TONE_PATH.is_file():
        logger.error("test_tone_missing", path=str(TEST_TONE_PATH))
        raise HTTPException(status_code=503, detail="Test tone asset not found")

    # Unbekannte Sinks muessen hier abgefangen werden. paplay meldet dafuer
    # KEINEN Fehler, sondern faellt still auf den Standardausgang zurueck und
    # beendet sich mit 0. Im Assistenten waere das die schlimmste Variante:
    # der Nutzer waehlt Ausgang A, hoert Ton aus B und haelt A fuer geprueft.
    if body.sink_name:
        try:
            known = await _service.get_audio_devices(force_refresh=True)
        except Exception as e:  # noqa: BLE001 - Geraeteliste ist bestenfalls beratend
            logger.warning("test_tone_device_lookup_failed", error=str(e))
            known = []
        if known and not any(d.get("id") == body.sink_name for d in known):
            raise HTTPException(
                status_code=404,
                detail=f"Unknown sink '{body.sink_name}'",
            )

    cmd = ["paplay"]
    if body.sink_name:
        cmd.append(f"--device={body.sink_name}")
    cmd.append(str(TEST_TONE_PATH))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("test_tone_paplay_missing")
        raise HTTPException(status_code=503, detail="paplay not available") from None

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), TEST_TONE_TIMEOUT)
    except TimeoutError:
        proc.kill()
        logger.warning("test_tone_timeout", sink=body.sink_name)
        raise HTTPException(status_code=504, detail="Test tone timed out") from None

    if proc.returncode != 0:
        detail = (stderr or b"").decode(errors="replace").strip()
        logger.warning(
            "test_tone_failed", sink=body.sink_name, rc=proc.returncode, error=detail
        )
        raise HTTPException(
            status_code=502, detail=detail or "Test tone playback failed"
        )

    logger.info("test_tone_played", sink=body.sink_name)
    return TestToneResponse(
        played=True,
        sink_name=body.sink_name,
        timestamp=datetime.now(UTC).isoformat(),
    )
