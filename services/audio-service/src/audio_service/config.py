from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import structlog
from shared_lib.config import load_env, load_json_config

from .config_schema import AppConfig, AudioConfig, EnvConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
AUDIO_CONFIG_PATH: Final[Path] = CONFIG_DIR / "audio.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    base = load_env()
    return EnvConfig(
        **base,
        audio_service_host=os.environ.get("AUDIO_SERVICE_HOST", "0.0.0.0"),
        audio_service_port=int(os.environ.get("AUDIO_SERVICE_PORT", "8003")),
        audio_config_path=os.environ.get("AUDIO_CONFIG_PATH", "config/audio.json"),
        audio_state_path=os.environ.get("AUDIO_STATE_PATH", "state/audio_state.json"),
    )


def _load_audio_config(path: Path | None = None) -> AudioConfig:
    """Load and validate the audio service configuration from JSON."""
    if path is None:
        path = AUDIO_CONFIG_PATH
    return load_json_config(
        path,
        AudioConfig,
        create_if_missing=True,
        default_factory=AudioConfig,
    )


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
