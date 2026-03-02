"""Configuration loading for the display service."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from shared_lib.config import load_env, load_json_config

from .config_schema import AppConfig, DisplayServiceConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
DISPLAY_CONFIG_PATH: Final[Path] = CONFIG_DIR / "display.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(**load_env())


def _load_display_config(path: Path = DISPLAY_CONFIG_PATH) -> DisplayServiceConfig:
    """Load and validate display configuration from JSON."""
    return load_json_config(path, DisplayServiceConfig)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration."""
    env_config = _load_env_config()
    display_config = _load_display_config()

    app_config = AppConfig(env=env_config, display=display_config)
    logger.info(
        "config_loaded",
        display_enabled=app_config.display.enabled,
        elements_count=len(app_config.display.elements),
        mqtt_broker=app_config.env.mqtt_broker,
        device_id=app_config.env.minabox_device_id,
    )
    return app_config
