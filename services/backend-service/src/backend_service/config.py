"""Global configuration loading for Backend Service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import structlog
from shared_lib.config import load_env, load_general_settings, load_json_config

from backend_service.config_schema import AppConfig, BackendServiceConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
BACKEND_CONFIG_PATH: Final[Path] = CONFIG_DIR / "backend.json"


def _general_settings_path() -> Path:
    """Path to optional general settings override (e.g. /data/general_settings.json)."""
    data_path = os.environ.get("DATA_PATH", "/data")
    return Path(data_path) / "general_settings.json"


def _load_env_config() -> EnvConfig:
    """Load required env and optional overrides from general_settings.json."""
    base = load_env()
    gs_path = _general_settings_path()
    data = load_general_settings(gs_path)
    if data:
        if "mqtt_broker" in data:
            base["mqtt_broker"] = str(data["mqtt_broker"])
        if "mqtt_port" in data:
            base["mqtt_port"] = int(data["mqtt_port"])
        if "minabox_device_id" in data:
            base["minabox_device_id"] = str(data["minabox_device_id"])
        if "log_level" in data:
            base["log_level"] = str(data["log_level"]).upper()

    return EnvConfig(
        **base,
        api_port=int(os.environ.get("API_PORT", "8080")),
        ws_enabled=os.environ.get("WS_ENABLED", "true").lower() in ("true", "1"),
        database_path=os.environ.get("DATABASE_PATH", "/data/minabox.db"),
        audio_storage_path=os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"),
    )


def _load_backend_config(path: Path = BACKEND_CONFIG_PATH) -> BackendServiceConfig:
    """Load and validate the backend service configuration from JSON."""
    return load_json_config(
        path,
        BackendServiceConfig,
        create_if_missing=True,
        default_factory=BackendServiceConfig,
    )


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    backend_config = _load_backend_config()

    app_config = AppConfig(env=env_config, backend=backend_config)

    logger.debug(
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
