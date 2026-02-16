"""Configuration schema for the Audio Service using Pydantic v2.

Defines the structure and validation rules for global and audio-specific
configuration settings.
"""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class OutputDeviceType(str, Enum):
    """Audio output device types."""

    AUTO = "auto"  # Auto-detect best device
    ALSA = "alsa"
    PULSEAUDIO = "pulseaudio"
    DEFAULT = "default"


class AudioConfig(BaseModel):
    """Audio service-specific configuration."""

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


class GlobalConfig(BaseModel):
    """Global configuration shared across all services."""

    mqtt_broker: str = Field(
        ...,
        description="MQTT broker hostname",
    )
    mqtt_port: int = Field(
        default=1883,
        ge=1,
        le=65535,
        description="MQTT broker port",
    )
    minabox_device_id: str = Field(
        ...,
        description="Unique device identifier for MQTT topics",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    audio_service_host: str = Field(
        default="0.0.0.0",
        description="FastAPI host binding",
    )
    audio_service_port: int = Field(
        default=8003,
        ge=1,
        le=65535,
        description="FastAPI port",
    )
    audio_config_path: Path = Field(
        default=Path("config/audio.json"),
        description="Path to audio-specific configuration file",
    )
    audio_state_path: Path = Field(
        default=Path("state/audio_state.json"),
        description="Path to audio state persistence file",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard levels."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()


class ServiceConfig(BaseModel):
    """Complete service configuration combining global and audio settings."""

    global_config: GlobalConfig
    audio_config: AudioConfig

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Generate MQTT topic following Minabox topic schema.

        Args:
            domain: Domain name (e.g., 'audio', 'system')
            action: Action/event name (e.g., 'play', 'status')

        Returns:
            Formatted MQTT topic: minabox/{device_id}/{domain}/{action}
        """
        return f"minabox/{self.global_config.minabox_device_id}/{domain}/{action}"
