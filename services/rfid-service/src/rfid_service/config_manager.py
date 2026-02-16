from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

import structlog
from dotenv import load_dotenv

from .config_schema import ServiceConfig

logger = structlog.get_logger(__name__)

ENV_MQTT_BROKER: Final[str] = "MQTT_BROKER"
ENV_MQTT_PORT: Final[str] = "MQTT_PORT"
ENV_DEVICE_ID: Final[str] = "MINABOX_DEVICE_ID"
ENV_LOG_LEVEL: Final[str] = "LOG_LEVEL"

SERVICE_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "config" / "service.json"
)


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


class ConfigManager:
    """Loads and validates configuration for the RFID service.

    This combines global environment variables from the root .env file
    with the service-specific JSON configuration.
    """

    def __init__(self) -> None:
        # Does not override already-set environment variables.
        load_dotenv()
        self._config: ServiceConfig | None = None

    def load(self, *, reload: bool = False) -> ServiceConfig:
        """Load and validate configuration.

        Parameters
        ----------
        reload:
            If True, forces re-reading the JSON file and env vars.

        Raises
        ------
        ConfigError
            If required env vars are missing, JSON cannot be read,
            or validation fails.
        """
        if self._config is not None and not reload:
            return self._config

        env_data = self._load_env()
        file_data = self._load_service_json()

        combined = {
            "device_id": env_data["device_id"],
            "mqtt_broker": env_data["mqtt_broker"],
            "mqtt_port": env_data["mqtt_port"],
            "log_level": env_data["log_level"],
            "reader": file_data.get("reader", {}),
        }

        try:
            self._config = ServiceConfig.model_validate(combined)
        except Exception as exc:  # noqa: BLE001
            logger.error("config_validation_failed", error=str(exc))
            raise ConfigError(f"Invalid configuration: {exc}") from exc

        logger.info("config_loaded", device_id=self._config.device_id)
        return self._config

    def _load_env(self) -> dict[str, object]:
        missing: list[str] = []

        mqtt_broker = os.getenv(ENV_MQTT_BROKER)
        if not mqtt_broker:
            missing.append(ENV_MQTT_BROKER)

        mqtt_port_raw = os.getenv(ENV_MQTT_PORT)
        device_id = os.getenv(ENV_DEVICE_ID)
        if not device_id:
            missing.append(ENV_DEVICE_ID)

        log_level = os.getenv(ENV_LOG_LEVEL)
        if not log_level:
            missing.append(ENV_LOG_LEVEL)

        if missing:
            message = f"Missing required environment variables: {', '.join(missing)}"
            logger.error("config_env_missing", missing=missing)
            raise ConfigError(message)

        try:
            mqtt_port = int(mqtt_port_raw) if mqtt_port_raw is not None else 1883
        except ValueError as exc:
            logger.error("config_env_invalid_port", value=mqtt_port_raw)
            raise ConfigError(f"Invalid MQTT_PORT value: {mqtt_port_raw}") from exc

        return {
            "mqtt_broker": mqtt_broker,
            "mqtt_port": mqtt_port,
            "device_id": device_id,
            "log_level": log_level.upper(),
        }

    def _load_service_json(self) -> dict[str, object]:
        if not SERVICE_CONFIG_PATH.is_file():
            logger.error("config_file_missing", path=str(SERVICE_CONFIG_PATH))
            raise ConfigError(f"Service config file not found: {SERVICE_CONFIG_PATH}")

        try:
            raw = SERVICE_CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError as exc:
            logger.error(
                "config_file_io_error",
                path=str(SERVICE_CONFIG_PATH),
                error=str(exc),
            )
            raise ConfigError(f"Could not read config file: {SERVICE_CONFIG_PATH}") from exc
        except json.JSONDecodeError as exc:
            logger.error(
                "config_file_invalid_json",
                path=str(SERVICE_CONFIG_PATH),
                error=str(exc),
            )
            raise ConfigError(f"Invalid JSON in config file: {SERVICE_CONFIG_PATH}") from exc

        if not isinstance(data, dict):
            logger.error("config_file_unexpected_type", path=str(SERVICE_CONFIG_PATH))
            raise ConfigError("Top-level service.json content must be a JSON object")

        return data

    def get_config(self) -> ServiceConfig:
        if self._config is None:
            return self.load()
        return self._config


config_manager = ConfigManager()
