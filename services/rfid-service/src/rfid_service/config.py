from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from shared_lib.config import load_env, load_json_config

from .config_schema import AppConfig, EnvConfig, RFIDServiceConfig

logger = structlog.get_logger(__name__)

SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONFIG_DIR: Final[Path] = SERVICE_ROOT / "config"
RFID_CONFIG_PATH: Final[Path] = CONFIG_DIR / "rfid.json"


def _load_env_config() -> EnvConfig:
    """Load required environment variables into an EnvConfig."""
    return EnvConfig(**load_env())


def _load_rfid_config(path: Path = RFID_CONFIG_PATH) -> RFIDServiceConfig:
    """Load and validate the RFID service configuration from JSON."""
    return load_json_config(path, RFIDServiceConfig)


def load_app_config() -> AppConfig:
    """Load and validate the full application configuration.

    This function is the single entry point the rest of the service should use.
    """
    env_config = _load_env_config()
    rfid_config = _load_rfid_config()

    app_config = AppConfig(env=env_config, rfid=rfid_config)

    logger.info(
        "config_loaded",
        mqtt_broker=app_config.env.mqtt_broker,
        mqtt_port=app_config.env.mqtt_port,
        device_id=app_config.env.minabox_device_id,
        reader_type=app_config.rfid.reader.reader_type,
    )
    return app_config
