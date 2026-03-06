"""Configuration schema for the Audio Service using Pydantic v2.

Defines the structure and validation rules for environment and
audio-specific configuration settings.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from shared_lib.config import EnvConfigBase


class OutputDeviceType(str, Enum):
    """Audio output device types.

    The product runtime is Pulse/PipeWire-only. Legacy values remain as
    compatibility aliases so older configs can be migrated on load.
    """

    AUTO = "auto"
    ALSA = "alsa"
    PULSEAUDIO = "pulseaudio"
    DEFAULT = "default"


class AudioConfig(BaseModel):
    """Audio service-specific configuration loaded from config/audio.json."""

    output_device_type: OutputDeviceType = Field(
        default=OutputDeviceType.PULSEAUDIO,
        description="Output type. Runtime uses pulseaudio/PipeWire.",
    )
    output_device_name: str = Field(
        default="",
        description="Pulse sink name; empty string means host default sink.",
    )
    enabled_output_devices: list[str] = Field(
        default_factory=list,
        description="Pulse sink names allowed in device selector (empty = all).",
    )
    device_display_names: dict[str, str] = Field(
        default_factory=dict,
        description="Sink name -> custom display name (optional).",
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


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the audio service (extends shared base)."""

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
