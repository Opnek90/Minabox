"""Config manager for the display service with hot-reload support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import structlog

from .config import DISPLAY_CONFIG_PATH, ConfigError, _load_display_config
from .config_schema import DisplayServiceConfig

logger = structlog.get_logger(__name__)


class ConfigManager:
    """Manages display service configuration with hot-reload support."""

    def __init__(self, config_path: Path = DISPLAY_CONFIG_PATH) -> None:
        self._config_path = config_path
        self._current_config: DisplayServiceConfig | None = None
        self._reload_callbacks: list[Callable[[DisplayServiceConfig], None]] = []

    def load_config(self) -> DisplayServiceConfig:
        """Load display configuration from disk."""
        config = _load_display_config(self._config_path)
        self._current_config = config
        logger.info("config_loaded", path=str(self._config_path))
        return config

    def get_current_config(self) -> DisplayServiceConfig | None:
        """Get the currently loaded configuration."""
        return self._current_config

    def reload_config(self) -> DisplayServiceConfig:
        """Reload configuration from disk and notify listeners."""
        config = self.load_config()
        for cb in self._reload_callbacks:
            try:
                cb(config)
            except Exception as exc:
                logger.error("reload_callback_failed", error=str(exc), exc_info=True)
        return config

    def register_reload_callback(
        self, callback: Callable[[DisplayServiceConfig], None]
    ) -> None:
        """Register a callback to be called when configuration is reloaded."""
        self._reload_callbacks.append(callback)
