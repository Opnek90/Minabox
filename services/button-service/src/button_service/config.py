from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog
from shared_lib.config import load_env

from .config_schema import AppConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
BUTTONS_CONFIG_PATH: Final[Path] = CONFIG_DIR / "buttons.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(
        **load_env(optional_defaults={"API_PORT": 8000, "DISABLE_GPIO": False})
    )


def load_app_config() -> AppConfig:
    """Load and validate the environment configuration.

    This function is the single entry point the rest of the service should use.

    It deliberately does not touch ``buttons.json``. That file is owned by the
    ConfigManager, which can reload it at runtime and survive a broken one --
    reading it here as well meant an unparsable file took the whole process
    down before the API was even up, leaving no way to repair it from the WebUI.
    """
    app_config = AppConfig(env=_load_env_config())

    logger.debug(
        "config_loaded",
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
        api_port=app_config.env.api_port,
        disable_gpio=app_config.env.disable_gpio,
    )
    return app_config
