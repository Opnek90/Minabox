"""LED service config manager (thin wrapper around shared_lib JsonConfigManager)."""

from __future__ import annotations

from pathlib import Path

from shared_lib.config import JsonConfigManager

from .config import LEDS_CONFIG_PATH
from .config_schema import LEDServiceConfig


class ConfigManager(JsonConfigManager):
    """Manages LED service configuration with hot-reload support."""

    def __init__(self, config_path: Path = LEDS_CONFIG_PATH) -> None:
        super().__init__(config_path, LEDServiceConfig)
