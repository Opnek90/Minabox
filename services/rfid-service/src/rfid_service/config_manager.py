from __future__ import annotations

from pathlib import Path

import structlog

from .config import RFID_CONFIG_PATH, _load_rfid_config
from .config_schema import RFIDServiceConfig

logger = structlog.get_logger(__name__)

class ConfigManager:
    """Manages RFID service configuration with hot-reload support.

    This manager handles:
    - Loading the current RFID configuration
    - Validating and persisting new configurations
    """

    def __init__(self, config_path: Path = RFID_CONFIG_PATH) -> None:
        """Initialize the config manager.

        Args:
            config_path: Path to the service.json configuration file.
        """
        self._config_path = config_path
        self._current_config: RFIDServiceConfig | None = None

    def load_config(self) -> RFIDServiceConfig:
        """Load the RFID configuration from disk.

        Returns:
            The loaded and validated RFID configuration.
        """
        config = _load_rfid_config(self._config_path)
        self._current_config = config
        logger.info(
            "config_loaded",
            path=str(self._config_path),
            reader_type=config.reader.reader_type,
        )
        return config

    def get_current_config(self) -> RFIDServiceConfig | None:
        """Get the currently loaded configuration."""
        return self._current_config

    def reload_config(self) -> RFIDServiceConfig:
        """Reload the configuration from disk.

        Returns:
            The reloaded configuration.
        """
        return self.load_config()
