"""Configuration loading for the display service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import structlog

from .config_schema import AppConfig, DisplayServiceConfig, EnvConfig
from .exceptions import ConfigError

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
DISPLAY_CONFIG_PATH: Final[Path] = CONFIG_DIR / "display.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    required_keys = ("MQTT_BROKER", "MQTT_PORT", "MINABOX_DEVICE_ID", "LOG_LEVEL")
    missing = [key for key in required_keys if key not in os.environ]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(sorted(missing))}"
        )

    mqtt_port_raw = os.environ["MQTT_PORT"]
    try:
        mqtt_port = int(mqtt_port_raw)
    except ValueError as exc:
        raise ConfigError(f"MQTT_PORT must be an integer, got '{mqtt_port_raw}'") from exc

    return EnvConfig(
        mqtt_broker=os.environ["MQTT_BROKER"],
        mqtt_port=mqtt_port,
        minabox_device_id=os.environ["MINABOX_DEVICE_ID"],
        log_level=os.environ["LOG_LEVEL"].upper(),
    )


def _load_display_config(path: Path = DISPLAY_CONFIG_PATH) -> DisplayServiceConfig:
    """Load and validate display configuration from JSON."""
    if not path.exists():
        raise ConfigError(f"Display configuration file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read display configuration: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in display configuration: {path}") from exc

    return DisplayServiceConfig.model_validate(data)


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
