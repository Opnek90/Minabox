"""Configuration manager for the Audio Service."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from .config_schema import AudioConfig

logger = structlog.get_logger(__name__)

class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""
    pass

class ConfigManager:
    """Manages audio configuration with hot-reload support.

    This manager handles:
    - Loading the current audio configuration from JSON
    - Validating and persisting new configurations
    - Hot-reload of audio config
    """

    def __init__(self, config_path: str = "config/audio.json") -> None:
        """Initialize the ConfigManager.

        Args:
            config_path: Path to the audio configuration JSON file.
        """
        self._config_path = Path(config_path)
        self._current_config: AudioConfig | None = None

    def load_config(self) -> AudioConfig:
        """Load the audio configuration from disk.

        Returns:
            The loaded and validated audio configuration.
        """
        if not self._config_path.exists():
            logger.warning(
                "audio_config_not_found_creating_default",
                path=str(self._config_path),
            )
            default_config = AudioConfig()
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_config(default_config)
            self._current_config = default_config
            return default_config

        try:
            raw_text = self._config_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            config = AudioConfig.model_validate(data)
            self._current_config = config
            logger.info(
                "config_loaded",
                path=str(self._config_path),
                max_volume=config.max_volume,
            )
            return config
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(f"Invalid JSON in {self._config_path}: {exc}") from exc
        except Exception as exc:
            raise ConfigLoadError(f"Failed to load {self._config_path}: {exc}") from exc

    def get_current_config(self) -> AudioConfig | None:
        """Get the currently loaded configuration."""
        return self._current_config

    def update_config(self, new_config: AudioConfig) -> None:
        """Validate and persist a new audio configuration.

        Args:
            new_config: The new audio configuration to apply.
        """
        self._save_config(new_config)
        self._current_config = new_config
        logger.info("config_updated", path=str(self._config_path))

    def reload_config(self) -> AudioConfig:
        """Reload the configuration from disk."""
        logger.info("audio_config_reload_started")
        return self.load_config()

    def _save_config(self, config: AudioConfig) -> None:
        """Save audio configuration to JSON file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        config_dict = config.model_dump(mode="json")
        config_json = json.dumps(config_dict, indent=2, ensure_ascii=False)
        self._config_path.write_text(config_json, encoding="utf-8")
