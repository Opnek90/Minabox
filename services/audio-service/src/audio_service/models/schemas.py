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


class SwitchDeviceBody(BaseModel):
    """Request body for POST /switch-device."""

    alsa_device: str | None = Field(
        default=None, description="Pulse sink name to switch to"
    )
    direction: str | None = Field(
        default=None, description="'next' to cycle to next enabled device"
    )
