from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import structlog

from .config_schema import AppConfig, AudioConfig, EnvConfig


logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
AUDIO_CONFIG_PATH: Final[Path] = CONFIG_DIR / "audio.json"


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

    return EnvConfig(
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        minabox_device_id=device_id,
        log_level=log_level,
        audio_service_host=os.environ.get("AUDIO_SERVICE_HOST", "0.0.0.0"),
        audio_service_port=int(os.environ.get("AUDIO_SERVICE_PORT", "8003")),
        audio_config_path=os.environ.get("AUDIO_CONFIG_PATH", "config/audio.json"),
        audio_state_path=os.environ.get("AUDIO_STATE_PATH", "state/audio_state.json"),
    )


def _load_audio_config(path: Path | None = None) -> AudioConfig:
    """Load and validate the audio service configuration from JSON."""
    if path is None:
        path = AUDIO_CONFIG_PATH

    if not path.exists():
        logger.warning("audio_config_not_found_using_defaults", path=str(path))
        return AudioConfig()

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read audio configuration file: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in audio configuration file: {path}") from exc

    return AudioConfig.model_validate(data)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    audio_config = _load_audio_config(Path(env_config.audio_config_path))

    app_config = AppConfig(env=env_config, audio=audio_config)

    logger.debug(
        "config_loaded",
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
        max_volume=app_config.audio.max_volume,
    )
    return app_config
