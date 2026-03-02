"""Backend service config manager (thin wrapper around shared_lib JsonConfigManager)."""

from __future__ import annotations

from pathlib import Path

from shared_lib.config import JsonConfigManager

from backend_service.config import BACKEND_CONFIG_PATH
from backend_service.config_schema import BackendServiceConfig


class ConfigManager(JsonConfigManager):
    """Manages Backend service configuration with hot-reload support."""

    def __init__(self, config_path: Path = BACKEND_CONFIG_PATH) -> None:
        super().__init__(
            config_path,
            BackendServiceConfig,
            create_if_missing=True,
            default_factory=BackendServiceConfig,
        )
