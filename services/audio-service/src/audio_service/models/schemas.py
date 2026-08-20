"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..infrastructure.audio_backend import AudioStatus


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


class TestToneBody(BaseModel):
    """Request body for POST /test-tone."""

    sink_name: str | None = Field(
        default=None,
        description="Sink to play the tone on; defaults to the active output",
    )


class TestToneResponse(BaseModel):
    """Response for POST /test-tone."""

    played: bool
    sink_name: str | None = None
    timestamp: str


class SwitchDeviceBody(BaseModel):
    """Request body for POST /switch-device."""

    sink_name: str | None = Field(
        default=None, description="PulseAudio/PipeWire sink name to switch to"
    )
    alsa_device: str | None = Field(
        default=None, description="Deprecated alias for sink_name; kept for backwards compatibility"
    )
    direction: str | None = Field(
        default=None, description="'next' to cycle to next enabled device"
    )
