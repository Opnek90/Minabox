"""Audio service config manager with ALSA→Pulse migration (uses shared_lib + custom load)."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from shared_lib.config import JsonConfigManager
from shared_lib.exceptions import ConfigError

from .config_schema import AudioConfig

logger = structlog.get_logger(__name__)


class ConfigManager(JsonConfigManager):
    """Manages audio configuration with hot-reload and ALSA→Pulse migration on load."""

    def __init__(self, config_path: str | Path = "config/audio.json") -> None:
        path = Path(config_path) if isinstance(config_path, str) else config_path
        super().__init__(
            path,
            AudioConfig,
            create_if_missing=True,
            default_factory=AudioConfig,
        )

    def load_config(self) -> AudioConfig:
        """Load from disk; create default if missing; migrate ALSA to Pulse and persist if needed."""
        if not self._config_path.exists():
            logger.warning(
                "audio_config_not_found_creating_default",
                path=str(self._config_path),
            )
            default_config = AudioConfig()
            self.update_config(default_config)
            return default_config

        try:
            raw_text = self._config_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except OSError as exc:
            raise ConfigError(f"Failed to read {self._config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {self._config_path}: {exc}") from exc

        migrated = False
        if data.get("output_device_type") == "alsa":
            data["output_device_type"] = "pulseaudio"
            data["output_device_name"] = ""
            migrated = True
            logger.debug("audio_config_migrated_alsa_to_pulse")

        config = AudioConfig.model_validate(data)
        self._current_config = config
        logger.debug("config_loaded", path=str(self._config_path), max_volume=config.max_volume)

        if migrated:
            self.update_config(config)

        return config
