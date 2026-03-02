from __future__ import annotations

from pydantic import BaseModel, Field


class ButtonConfig(BaseModel):
    """Schema for button service configuration."""

    # Simplified - actual schema depends on button service architecture
    debounce_ms: int = Field(
        50,
        ge=10,
        le=500,
        description="Debounce time in milliseconds",
    )
    long_press_ms: int = Field(
        1000,
        ge=100,
        le=5000,
        description="Long press threshold",
    )


class LEDConfig(BaseModel):
    """Schema for LED service configuration."""

    # Simplified - actual schema depends on LED service architecture
    brightness: int = Field(
        50,
        ge=0,
        le=100,
        description="LED brightness (0-100)",
    )
    animation_speed: int = Field(
        100,
        ge=10,
        le=1000,
        description="Animation speed in ms",
    )


class AudioConfig(BaseModel):
    """Schema for audio service configuration."""

    default_volume: int = Field(
        50,
        ge=0,
        le=100,
        description="Default volume (0-100)",
    )
    max_volume: int = Field(
        100,
        ge=0,
        le=100,
        description="Maximum volume (0-100)",
    )


class RFIDConfig(BaseModel):
    """Schema for RFID service configuration."""

    scan_interval_ms: int = Field(
        500,
        ge=100,
        le=2000,
        description="Scan interval in ms",
    )
    retry_attempts: int = Field(
        3,
        ge=1,
        le=10,
        description="Retry attempts on read failure",
    )


__all__ = [
    "ButtonConfig",
    "LEDConfig",
    "AudioConfig",
    "RFIDConfig",
]

