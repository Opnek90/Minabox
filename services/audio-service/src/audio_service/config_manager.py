"""Configuration manager for the Audio Service."""

import json
from pathlib import Path

import structlog
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from .config_schema import AudioConfig, GlobalConfig, ServiceConfig

logger = structlog.get_logger(__name__)


class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""

    pass


class ConfigManager:
    """Manages configuration loading, validation, and hot-reloading.

    Responsibilities:
    - Load global config from environment variables
    - Load audio config from JSON file
    - Validate all configurations
    - Support hot-reload of audio config
    - Fail-fast on missing required configuration
    """

    def __init__(self) -> None:
        """Initialize the ConfigManager."""
        self._global_config: GlobalConfig | None = None
        self._audio_config: AudioConfig | None = None
        self._service_config: ServiceConfig | None = None

    def load(self) -> ServiceConfig:
        """Load and validate all configuration.

        Returns:
            ServiceConfig: Combined configuration

        Raises:
            ConfigLoadError: If any required config is missing or invalid
        """
        logger.info("config_loading_started")

        try:
            # Load global config from environment
            self._global_config = self._load_global_config()
            logger.info(
                "global_config_loaded",
                device_id=self._global_config.minabox_device_id,
                mqtt_broker=self._global_config.mqtt_broker,
                log_level=self._global_config.log_level,
            )

            # Load audio config from JSON file
            self._audio_config = self._load_audio_config(
                self._global_config.audio_config_path
            )
            logger.info(
                "audio_config_loaded",
                config_path=str(self._global_config.audio_config_path),
                max_volume=self._audio_config.max_volume,
                output_device=self._audio_config.output_device_name,
            )

            # Combine configurations
            self._service_config = ServiceConfig(
                global_config=self._global_config,
                audio_config=self._audio_config,
            )

            logger.info("config_loading_completed")
            return self._service_config

        except ValidationError as e:
            logger.error("config_validation_failed", error=str(e))
            raise ConfigLoadError(f"Configuration validation failed: {e}") from e
        except Exception as e:
            logger.error("config_loading_failed", error=str(e))
            raise ConfigLoadError(f"Failed to load configuration: {e}") from e

    def _load_global_config(self) -> GlobalConfig:
        """Load global configuration from environment variables.

        Returns:
            GlobalConfig: Validated global configuration

        Raises:
            ValidationError: If required env vars are missing
        """

        class GlobalSettings(BaseSettings):
            """Settings loader for global configuration."""

            mqtt_broker: str
            mqtt_port: int = 1883
            minabox_device_id: str
            log_level: str
            audio_service_host: str = "0.0.0.0"
            audio_service_port: int = 8003
            audio_config_path: Path = Path("config/audio.json")
            audio_state_path: Path = Path("state/audio_state.json")

            model_config = {
                "env_prefix": "",
                "env_file": ".env",
                "env_file_encoding": "utf-8",
                "extra": "ignore",
            }

        settings = GlobalSettings()
        return GlobalConfig(**settings.model_dump())

    def _load_audio_config(self, config_path: Path) -> AudioConfig:
        """Load audio configuration from JSON file.

        Args:
            config_path: Path to audio config JSON file

        Returns:
            AudioConfig: Validated audio configuration

        Raises:
            ConfigLoadError: If file doesn't exist or is invalid
        """
        if not config_path.exists():
            logger.warning(
                "audio_config_not_found_creating_default",
                path=str(config_path),
            )
            # Create default config
            default_config = AudioConfig()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_audio_config(config_path, default_config)
            return default_config

        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return AudioConfig(**data)
        except json.JSONDecodeError as e:
            raise ConfigLoadError(f"Invalid JSON in {config_path}: {e}") from e
        except Exception as e:
            raise ConfigLoadError(f"Failed to load {config_path}: {e}") from e

    def _save_audio_config(self, config_path: Path, config: AudioConfig) -> None:
        """Save audio configuration to JSON file.

        Args:
            config_path: Path to save config
            config: AudioConfig to save
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)

    def reload_audio_config(self) -> AudioConfig:
        """Reload audio configuration from file (hot-reload).

        Returns:
            AudioConfig: Newly loaded configuration

        Raises:
            ConfigLoadError: If reload fails
        """
        if self._global_config is None:
            raise ConfigLoadError("Cannot reload audio config before initial load")

        logger.info("audio_config_reload_started")
        self._audio_config = self._load_audio_config(
            self._global_config.audio_config_path
        )

        # Update service config
        self._service_config = ServiceConfig(
            global_config=self._global_config,
            audio_config=self._audio_config,
        )

        logger.info("audio_config_reload_completed")
        return self._audio_config

    def update_audio_config(self, new_config: AudioConfig) -> None:
        """Update audio configuration (from MQTT config update).

        Args:
            new_config: New AudioConfig to apply

        Raises:
            ConfigLoadError: If update fails
        """
        if self._global_config is None:
            raise ConfigLoadError("Cannot update audio config before initial load")

        logger.info("audio_config_update_started")

        try:
            # Validate new config
            validated_config = AudioConfig(**new_config.model_dump())

            # Save to file
            self._save_audio_config(
                self._global_config.audio_config_path, validated_config
            )

            # Update in-memory config
            self._audio_config = validated_config
            self._service_config = ServiceConfig(
                global_config=self._global_config,
                audio_config=self._audio_config,
            )

            logger.info("audio_config_update_completed")

        except Exception as e:
            logger.error("audio_config_update_failed", error=str(e))
            raise ConfigLoadError(f"Failed to update audio config: {e}") from e

    @property
    def config(self) -> ServiceConfig:
        """Get current service configuration.

        Returns:
            ServiceConfig: Current configuration

        Raises:
            ConfigLoadError: If config hasn't been loaded yet
        """
        if self._service_config is None:
            raise ConfigLoadError("Configuration not loaded. Call load() first.")
        return self._service_config
