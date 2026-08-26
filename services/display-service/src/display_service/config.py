"""Configuration loading for the display service."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog
from shared_lib.config import load_env

from .config_schema import AppConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
DISPLAY_CONFIG_PATH: Final[Path] = CONFIG_DIR / "display.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(**load_env())


def load_app_config() -> AppConfig:
    """Load and validate the environment configuration.

    ``display.json`` is deliberately *not* read here. It used to be, into an
    ``AppConfig.display`` that nothing ever read: ``DisplayService`` loads the
    same file a second time through ``ConfigManager``, and that is the copy that
    gets used and reloaded. Two parses of one file, and the unread one went
    stale on the first reload.
    """
    env_config = _load_env_config()
    app_config = AppConfig(env=env_config)
    logger.info(
        "config_loaded",
        mqtt_broker=app_config.env.mqtt_broker,
        device_id=app_config.env.minabox_device_id,
    )
    return app_config
