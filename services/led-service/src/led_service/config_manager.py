from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import structlog

from .config import LEDS_CONFIG_PATH, ConfigError, _load_leds_config
from .config_schema import LEDServiceConfig

logger = structlog.get_logger(__name__)

class ConfigManager:
    """Manages LED service configuration with hot-reload support.
    
    This manager handles:
    - Loading the current LED configuration
    - Validating and persisting new configurations
    - Notifying listeners when configuration changes
    """

    def __init__(self, config_path: Path = LEDS_CONFIG_PATH) -> None:
        """Initialize the config manager.
        
        Args:
            config_path: Path to the leds.json configuration file.
        """
        self._config_path = config_path
        self._current_config: LEDServiceConfig | None = None
        self._reload_callbacks: list[Callable[[LEDServiceConfig], None]] = []

    def load_config(self) -> LEDServiceConfig:
        """Load the LED configuration from disk.
        
        Returns:
            The loaded and validated LED configuration.
            
        Raises:
            ConfigError: If the configuration cannot be loaded or is invalid.
        """
        config = _load_leds_config(self._config_path)
        self._current_config = config
        logger.info(
            "config_loaded",
            path=str(self._config_path),
            leds_count=len(config.leds),
        )
        return config

    def get_current_config(self) -> LEDServiceConfig | None:
        """Get the currently loaded configuration.
        
        Returns:
            The current configuration, or None if not yet loaded.
        """
        return self._current_config

    def update_config(self, new_config: LEDServiceConfig) -> None:
        """Validate and persist a new LED configuration.
        
        This method:
        1. Validates the new configuration (Pydantic already did this)
        2. Writes it to disk
        3. Updates the internal state
        4. Notifies all registered callbacks
        
        Args:
            new_config: The new LED configuration to apply.
            
        Raises:
            ConfigError: If the configuration cannot be written to disk.
        """
        # Serialize to JSON
        try:
            config_dict = new_config.model_dump(mode="json")
            config_json = json.dumps(config_dict, indent=2, ensure_ascii=False)
        except Exception as exc:
            raise ConfigError(f"Failed to serialize new configuration: {exc}") from exc

        # Write to disk
        try:
            self._config_path.write_text(config_json, encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"Failed to write configuration to {self._config_path}: {exc}"
            ) from exc

        # Update internal state
        self._current_config = new_config
        logger.info(
            "config_updated",
            path=str(self._config_path),
            leds_count=len(new_config.leds),
        )

        # Notify listeners
        self._notify_reload_callbacks(new_config)

    def reload_config(self) -> LEDServiceConfig:
        """Reload the configuration from disk and notify listeners.
        
        Returns:
            The reloaded configuration.
            
        Raises:
            ConfigError: If the configuration cannot be loaded or is invalid.
        """
        config = self.load_config()
        self._notify_reload_callbacks(config)
        return config

    def register_reload_callback(
        self, callback: Callable[[LEDServiceConfig], None]
    ) -> None:
        """Register a callback to be called when configuration is reloaded.
        
        The callback will be invoked with the new configuration after any
        successful reload or update operation.
        
        Args:
            callback: A callable that accepts a LEDServiceConfig.
        """
        self._reload_callbacks.append(callback)
        logger.debug("reload_callback_registered", callback=callback.__name__)

    def _notify_reload_callbacks(self, config: LEDServiceConfig) -> None:
        """Notify all registered callbacks about a configuration change."""
        for callback in self._reload_callbacks:
            try:
                callback(config)
            except Exception as exc:
                logger.error(
                    "reload_callback_failed",
                    callback=callback.__name__,
                    error=str(exc),
                    exc_info=True,
                )
