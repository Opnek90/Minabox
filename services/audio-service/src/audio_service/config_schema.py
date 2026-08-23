"""Configuration schema for the Audio Service using Pydantic v2.

Defines the structure and validation rules for environment and
audio-specific configuration settings.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator
from shared_lib.config import EnvConfigBase


class OutputDeviceType(str, Enum):  # noqa: UP042 - see note below
    """Audio output device types.

    The product runtime is Pulse/PipeWire-only. Legacy values remain as
    compatibility aliases so older configs can be migrated on load.

    Deliberately not a StrEnum: str(OutputDeviceType.PULSEAUDIO) would then
    yield "pulseaudio" instead of "OutputDeviceType.PULSEAUDIO", which changes
    what already-shipped log lines print. Not worth the churn before go-live.
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
    min_volume: int = Field(
        default=5,
        ge=0,
        le=100,
        description="Minimum volume level (prevents accidental silencing)",
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

    @model_validator(mode="after")
    def validate_volume_bounds(self) -> AudioConfig:
        """Keep min < max and default inside [min_volume, max_volume]."""
        # Clamp min_volume below max_volume
        if self.min_volume >= self.max_volume:
            self.min_volume = max(0, self.max_volume - 1)
        # Clamp default_volume within [min_volume, max_volume]
        if self.default_volume > self.max_volume:
            self.default_volume = self.max_volume
        if self.default_volume < self.min_volume:
            self.default_volume = self.min_volume
        return self


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
