"""Configuration manager with hot-reload support."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from backend_service.config import BACKEND_CONFIG_PATH, _load_backend_config
from backend_service.config_schema import AppConfig, BackendServiceConfig

logger = structlog.get_logger(__name__)

class ConfigManager:
    """Manages Backend service configuration with hot-reload support."""

    def __init__(self, config_path: Path = BACKEND_CONFIG_PATH) -> None:
        """Initialize the config manager.

        Args:
            config_path: Path to the backend.json configuration file.
        """
        self._config_path = config_path
        self._current_config: BackendServiceConfig | None = None

    def load_config(self) -> BackendServiceConfig:
        """Load the backend configuration from disk."""
        config = _load_backend_config(self._config_path)
        self._current_config = config
        logger.info("config_loaded", path=str(self._config_path))
        return config

    def get_current_config(self) -> BackendServiceConfig | None:
        """Get the currently loaded configuration."""
        return self._current_config

    def update_config(self, new_config: BackendServiceConfig) -> None:
        """Validate and persist a new backend configuration."""
        try:
            config_dict = new_config.model_dump(mode="json")
            config_json = json.dumps(config_dict, indent=2, ensure_ascii=False)
        except Exception as exc:
            raise RuntimeError(f"Failed to serialize new configuration: {exc}") from exc

        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(config_json, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(
                f"Failed to write configuration to {self._config_path}: {exc}"
            ) from exc

        self._current_config = new_config
        logger.info("config_updated", path=str(self._config_path))

    def reload_config(self) -> BackendServiceConfig:
        """Reload the configuration from disk."""
        return self.load_config()
