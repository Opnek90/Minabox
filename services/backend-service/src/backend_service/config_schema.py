"""Configuration schema for Backend Service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt

from shared_lib.config import EnvConfigBase


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the backend (extends shared base)."""

    api_port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="REST API port.",
    )
    ws_enabled: bool = Field(
        default=True,
        description="Enable WebSocket support.",
    )
    database_path: str = Field(
        default="/data/minabox.db",
        description="SQLite database path.",
    )
    audio_storage_path: str = Field(
        default="/mnt/audio/tracks",
        description="Audio files storage path.",
    )


class BackendServiceConfig(BaseModel):
    """Backend-specific configuration loaded from config/backend.json."""

    session_timeout_min: int = Field(
        default=60,
        ge=1,
        description="Playback session timeout in minutes.",
    )
    health_check_interval_sec: int = Field(
        default=30,
        ge=5,
        description="Health check interval in seconds.",
    )
    max_upload_size_mb: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Max file upload size in MB.",
    )


class AppConfig(BaseModel):
    """Combined configuration for the backend service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    backend: BackendServiceConfig

    @property
    def mqtt_topic_prefix(self) -> str:
        """Get MQTT topic prefix for this device."""
        return f"minabox/{self.env.minabox_device_id}"

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Build MQTT topic for given domain and action.

        Args:
            domain: Service domain (e.g., 'rfid', 'audio', 'button')
            action: Action name (e.g., 'tag-scanned', 'play', 'status')

        Returns:
            Full MQTT topic: minabox/<device-id>/<domain>/<action>
        """
        return f"{self.mqtt_topic_prefix}/{domain}/{action}"

    # Compatibility aliases for code that accesses flat config fields
    @property
    def device_id(self) -> str:
        return self.env.minabox_device_id

    @property
    def mqtt_broker(self) -> str:
        return self.env.mqtt_broker

    @property
    def mqtt_port(self) -> int:
        return self.env.mqtt_port

    @property
    def api_port(self) -> int:
        return self.env.api_port

    @property
    def database_path(self) -> str:
        return self.env.database_path

    @property
    def audio_storage_path(self) -> str:
        return self.env.audio_storage_path

    @property
    def log_level(self) -> str:
        return self.env.log_level


# Backward-compatible alias — existing code that imports BackendConfig still works
BackendConfig = AppConfig
