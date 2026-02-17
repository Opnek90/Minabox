"""Configuration schema for the Audio Service using Pydantic v2.

Defines the structure and validation rules for environment and
audio-specific configuration settings.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator


class OutputDeviceType(str, Enum):
    """Audio output device types."""

    AUTO = "auto"
    ALSA = "alsa"
    PULSEAUDIO = "pulseaudio"
    DEFAULT = "default"


class AudioConfig(BaseModel):
    """Audio service-specific configuration loaded from config/audio.json."""

    output_device_type: OutputDeviceType = Field(
        default=OutputDeviceType.AUTO,
        description="Audio output device type (auto, alsa, pulseaudio, default)",
    )
    output_device_name: str = Field(
        default="auto",
        description="Audio output device name (e.g., 'hw:0,0', 'default', 'auto')",
    )
    max_volume: int = Field(
        default=70,
        ge=0,
        le=100,
        description="Maximum volume level (child protection)",
    )
    default_volume: int = Field(
        default=40,
        ge=0,
        le=100,
        description="Default volume on service start",
    )

    @field_validator("default_volume")
    @classmethod
    def validate_default_volume(cls, v: int, info) -> int:
        """Ensure default_volume doesn't exceed max_volume."""
        max_vol = info.data.get("max_volume", 100)
        if v > max_vol:
            return max_vol
        return v


class EnvConfig(BaseModel):
    """Environment-based configuration shared across Minabox services."""

    mqtt_broker: str = Field(
        min_length=1,
        description="Hostname of the MQTT broker (e.g. 'mqtt').",
    )
    mqtt_port: PositiveInt = Field(
        description="Port of the MQTT broker (e.g. 1883).",
    )
    minabox_device_id: str = Field(
        min_length=1,
        description="Device ID used in MQTT topics (e.g. 'box1').",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        description="Global log level for this service.",
    )
    audio_service_host: str = Field(
        default="0.0.0.0",
        description="FastAPI host binding.",
    )
    audio_service_port: int = Field(
        default=8003,
        ge=1,
        le=65535,
        description="FastAPI port.",
    )
    audio_config_path: str = Field(
        default="config/audio.json",
        description="Path to audio-specific configuration file.",
    )
    audio_state_path: str = Field(
        default="state/audio_state.json",
        description="Path to audio state persistence file.",
    )


class AppConfig(BaseModel):
    """Combined configuration for the audio service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    audio: AudioConfig

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Generate MQTT topic following Minabox topic schema.

        Args:
            domain: Domain name (e.g., 'audio', 'system')
            action: Action/event name (e.g., 'play', 'status')

        Returns:
            Formatted MQTT topic: minabox/{device_id}/{domain}/{action}
        """
        return f"minabox/{self.env.minabox_device_id}/{domain}/{action}"
