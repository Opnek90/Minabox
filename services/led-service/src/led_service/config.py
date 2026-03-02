from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from shared_lib.config import load_env, load_json_config

from .config_schema import AppConfig, EnvConfig, LEDServiceConfig

logger = structlog.get_logger(__name__)

# services/led-service/src/led_service/config.py
# -> parents[0] = led_service, parents[1] = src, parents[2] = led-service (service root)
SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
LEDS_CONFIG_PATH: Final[Path] = CONFIG_DIR / "leds.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(**load_env())


def _load_leds_config(path: Path = LEDS_CONFIG_PATH) -> LEDServiceConfig:
    """Load and validate the LED service configuration from JSON."""
    return load_json_config(path, LEDServiceConfig)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    leds_config = _load_leds_config()

    app_config = AppConfig(env=env_config, leds=leds_config)

    logger.debug(
        "config_loaded",
        leds_count=len(app_config.leds.leds),
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
    )
    return app_config
