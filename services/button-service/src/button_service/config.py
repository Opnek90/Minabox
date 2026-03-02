from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from shared_lib.config import load_env, load_json_config

from .config_schema import AppConfig, ButtonServiceConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
BUTTONS_CONFIG_PATH: Final[Path] = CONFIG_DIR / "buttons.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(**load_env())


def _load_buttons_config(path: Path = BUTTONS_CONFIG_PATH) -> ButtonServiceConfig:
    """Load and validate the button service configuration from JSON."""
    return load_json_config(path, ButtonServiceConfig)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    buttons_config = _load_buttons_config()

    app_config = AppConfig(env=env_config, buttons=buttons_config)

    logger.debug(
        "config_loaded",
        buttons_count=len(app_config.buttons.buttons),
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
    )
    return app_config
