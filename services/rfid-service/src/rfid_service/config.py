from __future__ import annotations

from .config_manager import ConfigManager, config_manager
from .config_schema import ServiceConfig

__all__ = ["get_config", "ServiceConfig", "ConfigManager"]


def get_config() -> ServiceConfig:
    """Return the validated RFID service configuration."""
    return config_manager.get_config()
