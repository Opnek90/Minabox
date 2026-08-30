"""FastAPI routes for the Audio Service.

Provides health check, status, devices, and switch-device endpoints.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, Query
from shared_lib.version import get_version

from ..config_schema import AppConfig
from ..core import AudioService
from ..core.service import TEST_TONE_PATH as _TEST_TONE_PATH
from ..core.service import TEST_TONE_TIMEOUT
from ..models import (
    DeviceItem,
    DevicesResponse,
    HealthResponse,
    StatusResponse,
    SwitchDeviceBody,
    TestToneBody,
    TestToneResponse,
    TroubleshootResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

# Defined next to the service, which plays the same asset for the sound
# troubleshooter.
TEST_TONE_PATH = Path(_TEST_TONE_PATH)

# The chain ends with the tone, so it cannot be shorter than the tone's own
# limit. The rest is the pactl calls, which are capped at 5 s each.
TROUBLESHOOT_TIMEOUT = TEST_TONE_TIMEOUT + 20.0

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
        version=get_version(),
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
            # Broker up and VLC up used to be the whole check - and both were
            # true while the sound card had vanished and the box was silent.
            device_ok, device_name = await service.check_output_device()
            healthy = mqtt_connected and vlc_initialized and device_ok
            return HealthResponse(
                status="healthy" if healthy else "degraded",
                service="audio",
                version=get_version(),
                uptime_seconds=uptime,
                mqtt_connected=mqtt_connected,
                vlc_initialized=vlc_initialized,
                output_device=device_name,
                output_device_available=device_ok,
                timestamp=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/devices", response_model=DevicesResponse)
async def get_devices(
    enabled_only: bool = Query(
        False, description="Return only devices in enabled_output_devices"
    ),
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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("switch_device_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/troubleshoot", response_model=TroubleshootResponse)
async def troubleshoot() -> TroubleshootResponse:
    """Walk the sound-repair chain and end with the test tone.

    Steps 2 to 6 of the sound-repair chain - the sink, the stream
    and the service's own volume and mute. Steps 1 and 7 need
    /proc/asound/cards and amixer, which this container cannot reach; the
    backend adds them from the host-helper.

    Repairs happen without asking, and are safe to: every one of them is
    idempotent and only fires on a value nobody could have meant. Running this
    twice does nothing the second time.
    """
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not TEST_TONE_PATH.is_file():
        logger.error("test_tone_missing", path=str(TEST_TONE_PATH))
        raise HTTPException(status_code=503, detail="Test tone asset not found")

    try:
        result = await asyncio.wait_for(
            _service.troubleshoot(), TROUBLESHOOT_TIMEOUT
        )
    except TimeoutError:
        logger.warning("audio_troubleshoot_timeout")
        raise HTTPException(
            status_code=504, detail="Troubleshooting timed out"
        ) from None
    except Exception as e:  # noqa: BLE001 - reported to the caller as 500
        logger.error("audio_troubleshoot_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e

    return TroubleshootResponse(
        steps=result["steps"],
        fixed=result["fixed"],
        cause=result["cause"],
        tone_played=result["tone_played"],
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.post("/test-tone", response_model=TestToneResponse)
async def play_test_tone(body: TestToneBody) -> TestToneResponse:
    """Play a short test tone on the given (or active) sink.

    Routed through libVLC on a throwaway player, not through paplay. paplay
    runs under ``application.name:paplay``, a different PipeWire stream role
    with its own remembered volume and mute - so on a box whose *music* role
    was remembered as muted, the test tone was audible while nothing else was.
    A tone that cannot fail the way the music fails is not a test.

    The throwaway player is what keeps the old promise: the wizard checks the
    speaker while something is playing, and taking over the service's player
    would stop the music and leave the session in a state the user did not ask
    for.
    """
    if _service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not TEST_TONE_PATH.is_file():
        logger.error("test_tone_missing", path=str(TEST_TONE_PATH))
        raise HTTPException(status_code=503, detail="Test tone asset not found")

    # Unknown sinks have to be caught here. Neither paplay before nor libVLC
    # now reports an error for them: both fall back to the default output
    # silently and report success. In the wizard that would be the worst
    # outcome - the user picks output A, hears sound from B, and believes A is
    # verified.
    if body.sink_name:
        try:
            known = await _service.get_audio_devices(force_refresh=True)
        except Exception as e:  # noqa: BLE001 - device list is advisory at best
            logger.warning("test_tone_device_lookup_failed", error=str(e))
            known = []
        if known and not any(d.get("id") == body.sink_name for d in known):
            raise HTTPException(
                status_code=404,
                detail=f"Unknown sink '{body.sink_name}'",
            )

    try:
        await asyncio.wait_for(
            _service.play_test_tone(
                str(TEST_TONE_PATH),
                body.sink_name,
                timeout_sec=TEST_TONE_TIMEOUT,
            ),
            TEST_TONE_TIMEOUT + 2.0,
        )
    except TimeoutError:
        logger.warning("test_tone_timeout", sink=body.sink_name)
        raise HTTPException(status_code=504, detail="Test tone timed out") from None
    except Exception as e:  # noqa: BLE001 - reported to the caller as 502
        logger.warning("test_tone_failed", sink=body.sink_name, error=str(e))
        raise HTTPException(
            status_code=502, detail=str(e) or "Test tone playback failed"
        ) from e

    logger.info("test_tone_played", sink=body.sink_name)
    return TestToneResponse(
        played=True,
        sink_name=body.sink_name,
        timestamp=datetime.now(UTC).isoformat(),
    )
