"""Configuration schema for Backend Service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendConfig(BaseSettings):
    """Backend service configuration schema.

    Loads from environment variables and config/backend.json.
    """

    model_config = SettingsConfigDict(
        env_prefix="MINABOX_BACKEND_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Global settings (from root .env)
    device_id: str = Field(default="box1", description="Device ID for MQTT topics")
    mqtt_broker: str = Field(default="mosquitto", description="MQTT broker hostname")
    mqtt_port: int = Field(default=1883, ge=1, le=65535, description="MQTT broker port")
    log_level: str = Field(default="INFO", description="Logging level")

    # Backend-specific settings (from config/backend.json)
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
                "mqtt_broker": "mosquitto",
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
