"""Global configuration loading for Backend Service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import structlog

from backend_service.config_schema import AppConfig, BackendServiceConfig, EnvConfig


logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
BACKEND_CONFIG_PATH: Final[Path] = CONFIG_DIR / "backend.json"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or validated."""
    pass


def _general_settings_path() -> Path:
    """Path to optional general settings override (e.g. /data/general_settings.json)."""
    data_path = os.environ.get("DATA_PATH", "/data")
    return Path(data_path) / "general_settings.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig.

    Fails fast with a clear error message if any required variable is missing.
    Optional: overrides from /data/general_settings.json if present.
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

    # Optional overrides from general_settings.json (takes effect after restart)
    gs_path = _general_settings_path()
    if gs_path.exists():
        try:
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            if "mqtt_broker" in data:
                mqtt_broker = str(data["mqtt_broker"])
            if "mqtt_port" in data:
                mqtt_port_raw = str(data["mqtt_port"])
            if "minabox_device_id" in data:
                device_id = str(data["minabox_device_id"])
            if "log_level" in data:
                log_level = str(data["log_level"]).upper()
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("general_settings_load_failed", path=str(gs_path), error=str(e))

    try:
        mqtt_port = int(mqtt_port_raw)
    except ValueError as exc:
        raise ConfigError(f"MQTT_PORT must be an integer, got '{mqtt_port_raw}'") from exc

    return EnvConfig(
        mqtt_broker=mqtt_broker,
        mqtt_port=mqtt_port,
        minabox_device_id=device_id,
        log_level=log_level,
        api_port=int(os.environ.get("API_PORT", "8080")),
        ws_enabled=os.environ.get("WS_ENABLED", "true").lower() in ("true", "1"),
        database_path=os.environ.get("DATABASE_PATH", "/data/minabox.db"),
        audio_storage_path=os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"),
    )


def _load_backend_config(path: Path = BACKEND_CONFIG_PATH) -> BackendServiceConfig:
    """Load and validate the backend service configuration from JSON."""
    if not path.exists():
        logger.warning("backend_config_not_found_using_defaults", path=str(path))
        return BackendServiceConfig()

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read backend configuration file: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in backend configuration file: {path}") from exc

    return BackendServiceConfig.model_validate(data)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    backend_config = _load_backend_config()

    app_config = AppConfig(env=env_config, backend=backend_config)

    logger.info(
        "config_loaded",
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
        api_port=app_config.env.api_port,
    )
    return app_config


def get_config() -> AppConfig:
    """Convenience function that loads and returns config.

    This is the main entry point for modules that need the configuration.
    """
    return load_app_config()


def reload_config() -> AppConfig:
    """Reload configuration from disk."""
    return load_app_config()
