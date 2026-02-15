"""Configuration schema for Backend Service."""

import os
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendConfig(BaseSettings):
    """Backend service configuration schema.

    Global settings (device_id, mqtt_broker, mqtt_port, log_level) are loaded
    from environment variables WITHOUT the MINABOX_BACKEND_ prefix.
    
    Backend-specific settings use the MINABOX_BACKEND_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="MINABOX_BACKEND_",  # Only for backend-specific settings!
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Global settings (loaded WITHOUT prefix, REQUIRED)
    device_id: str = Field(description="Device ID for MQTT topics")
    mqtt_broker: str = Field(description="MQTT broker hostname")
    mqtt_port: int = Field(ge=1, le=65535, description="MQTT broker port")
    log_level: str = Field(description="Logging level")

    # Backend-specific settings (loaded WITH prefix via model_config)
    api_port: int = Field(default=8080, ge=1024, le=65535, description="REST API port")
    ws_enabled: bool = Field(default=True, description="Enable WebSocket support")
    session_timeout_min: int = Field(
        default=60, ge=1, description="Playback session timeout in minutes"
    )
    health_check_interval_sec: int = Field(
        default=30, ge=5, description="Health check interval in seconds"
    )
    max_upload_size_mb: int = Field(
        default=100, ge=1, le=1000, description="Max file upload size in MB"
    )
    audio_storage_path: str = Field(
        default="/mnt/audio/tracks", description="Audio files storage path"
    )
    database_path: str = Field(
        default="/data/minabox.db", description="SQLite database path"
    )

    @model_validator(mode="before")
    @classmethod
    def load_global_settings(cls, data: Any) -> Any:
        """Load global settings from environment variables without prefix.
        
        This ensures that global settings like MQTT_BROKER, MINABOX_DEVICE_ID
        are loaded directly, not with the MINABOX_BACKEND_ prefix.
        
        Raises:
            ValueError: If required environment variables are missing.
        """
        if not isinstance(data, dict):
            data = {}

        # Load global settings from environment (without MINABOX_BACKEND_ prefix)
        if "device_id" not in data or data["device_id"] is None:
            data["device_id"] = os.getenv("MINABOX_DEVICE_ID")
        
        if "mqtt_broker" not in data or data["mqtt_broker"] is None:
            data["mqtt_broker"] = os.getenv("MQTT_BROKER")
        
        if "mqtt_port" not in data or data["mqtt_port"] is None:
            port_str = os.getenv("MQTT_PORT")
            if port_str:
                data["mqtt_port"] = int(port_str)
        
        if "log_level" not in data or data["log_level"] is None:
            data["log_level"] = os.getenv("LOG_LEVEL")

        # Validate that required global settings are present
        required_global = {
            "device_id": "MINABOX_DEVICE_ID",
            "mqtt_broker": "MQTT_BROKER",
            "mqtt_port": "MQTT_PORT",
            "log_level": "LOG_LEVEL",
        }
        
        missing = [
            env_name
            for field_name, env_name in required_global.items()
            if not data.get(field_name)
        ]
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Please set these in your .env file or docker-compose.yml."
            )

        return data

    # MQTT Topics (computed)
    @property
    def mqtt_topic_prefix(self) -> str:
        """Get MQTT topic prefix for this device."""
        return f"minabox/{self.device_id}"

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Build MQTT topic for given domain and action.

        Args:
            domain: Service domain (e.g., 'rfid', 'audio', 'button')
            action: Action name (e.g., 'tag-scanned', 'play', 'status')

        Returns:
            Full MQTT topic: minabox/<device-id>/<domain>/<action>
        """
        return f"{self.mqtt_topic_prefix}/{domain}/{action}"

    class ConfigDict:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "device_id": "box1",
                "mqtt_broker": "mqtt",
                "mqtt_port": 1883,
                "log_level": "INFO",
                "api_port": 8080,
                "ws_enabled": True,
                "session_timeout_min": 60,
                "health_check_interval_sec": 30,
                "max_upload_size_mb": 100,
                "audio_storage_path": "/mnt/audio/tracks",
                "database_path": "/data/minabox.db",
            }
        }
