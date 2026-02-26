from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import structlog

from .config_schema import AppConfig, ButtonServiceConfig, EnvConfig


logger = structlog.get_logger(__name__)

# services/button-service/src/button_service/config.py
# -> parents[0] = button_service
# -> parents[1] = src
# -> parents[2] = button-service (service root)
SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
BUTTONS_CONFIG_PATH: Final[Path] = CONFIG_DIR / "buttons.json"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or validated."""
    pass


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig.

    Fails fast with a clear error message if any required variable is missing.
    """
    required_keys = ("MQTT_BROKER", "MQTT_PORT", "MINABOX_DEVICE_ID", "LOG_LEVEL")

    missing = [key for key in required_keys if key not in os.environ]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(sorted(missing))}"
        )

    mqtt_broker = os.environ["MQTT_BROKER"]
    mqtt_port_raw = os.environ["MQTT_PORT"]
    device_id = os.environ["MINABOX_DEVICE_ID"]
    log_level = os.environ["LOG_LEVEL"].upper()

    try:
        mqtt_port = int(mqtt_port_raw)
    except ValueError as exc:
        raise ConfigError(f"MQTT_PORT must be an integer, got '{mqtt_port_raw}'") from exc

    env_config = EnvConfig(
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        minabox_device_id=device_id,
        log_level=log_level,
    )
    return env_config


def _load_buttons_config(path: Path = BUTTONS_CONFIG_PATH) -> ButtonServiceConfig:
    """Load and validate the button service configuration from JSON.

    The structure must match ButtonServiceConfig as defined in config_schema.py.
    """
    if not path.exists():
        raise ConfigError(f"Button configuration file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read button configuration file: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in button configuration file: {path}") from exc

    return ButtonServiceConfig.model_validate(data)


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
