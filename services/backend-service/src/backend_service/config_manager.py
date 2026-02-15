"""Configuration manager with hot-reload support."""

import json
from pathlib import Path

import structlog
from pydantic import ValidationError

from backend_service.config_schema import BackendConfig

logger = structlog.get_logger(__name__)


class ConfigManager:
    """Manages Backend service configuration with hot-reload support."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize config manager.

        Args:
            config_path: Path to config JSON file (default: config/backend.json)
        """
        self.config_path = config_path or Path("config/backend.json")
        self._config: BackendConfig | None = None
        logger.info("config_manager_initialized", config_path=str(self.config_path))

    def load(self) -> BackendConfig:
        """Load configuration from environment and JSON file.

        Returns:
            Loaded and validated configuration

        Raises:
            ValidationError: If configuration is invalid
            FileNotFoundError: If config file doesn't exist
        """
        logger.info("config_loading", path=str(self.config_path))

        # Load base config from environment
        config_dict = {}

        # Load service-specific config from JSON
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    json_config = json.load(f)
                    config_dict.update(json_config)
                logger.info("config_json_loaded", path=str(self.config_path))
            except json.JSONDecodeError as e:
                logger.error(
                    "config_json_invalid", error=str(e), path=str(self.config_path)
                )
                raise
        else:
            logger.warning("config_file_not_found", path=str(self.config_path))

        # Validate and create config
        try:
            self._config = BackendConfig(**config_dict)
            logger.info(
                "config_loaded_successfully",
                device_id=self._config.device_id,
                mqtt_broker=self._config.mqtt_broker,
                api_port=self._config.api_port,
            )
            return self._config
        except ValidationError as e:
            logger.error("config_validation_failed", error=str(e))
            raise

    def reload(self) -> BackendConfig:
        """Reload configuration from disk.

        Returns:
            Reloaded configuration
        """
        logger.info("config_reloading")
        return self.load()

    def save(self, config: BackendConfig) -> None:
        """Save configuration to JSON file.

        Args:
            config: Configuration to save
        """
        logger.info("config_saving", path=str(self.config_path))

        # Extract service-specific fields (not from environment)
        service_config = {
            "api_port": config.api_port,
            "ws_enabled": config.ws_enabled,
            "session_timeout_min": config.session_timeout_min,
            "health_check_interval_sec": config.health_check_interval_sec,
            "max_upload_size_mb": config.max_upload_size_mb,
            "audio_storage_path": config.audio_storage_path,
            "database_path": config.database_path,
        }

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(service_config, f, indent=2)

        logger.info("config_saved_successfully", path=str(self.config_path))

    @property
    def config(self) -> BackendConfig:
        """Get current configuration.

        Returns:
            Current configuration

        Raises:
            RuntimeError: If config not loaded yet
        """
        if self._config is None:
            raise RuntimeError("Configuration not loaded. Call load() first.")
        return self._config
