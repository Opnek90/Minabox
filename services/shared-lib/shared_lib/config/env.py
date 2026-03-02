"""Common environment config and loader for Minabox services.

Services can use EnvConfigBase as a base for their EnvConfig (adding
service-specific env vars) or use load_env() to build a dict for their own
Pydantic model.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field, PositiveInt

# Keys required by all services (used by load_env).
COMMON_ENV_KEYS = ("MQTT_BROKER", "MQTT_PORT", "MINABOX_DEVICE_ID", "LOG_LEVEL")


class EnvConfigBase(BaseModel):
    """Minimal env config shared across Minabox services.

    Use as base for service EnvConfig when you only need these four fields,
    or add fields in a subclass.
    """

    mqtt_broker: str = Field(min_length=1, description="MQTT broker hostname.")
    mqtt_port: PositiveInt = Field(description="MQTT broker port.")
    minabox_device_id: str = Field(min_length=1, description="Device ID for MQTT topics.")
    log_level: str = Field(
        description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )


def load_env(
    required_keys: tuple[str, ...] = COMMON_ENV_KEYS,
    optional_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load environment variables into a dict for use with Pydantic.

    Args:
        required_keys: Env var names that must be set (e.g. MQTT_BROKER).
        optional_defaults: Optional env vars with defaults, e.g. {"AUDIO_PORT": 8003}.

    Returns:
        Dict with keys in lowercase (MQTT_BROKER -> mqtt_broker) and values
        coerced (e.g. MQTT_PORT to int). Optional keys are included with
        their default if not set.

    Raises:
        ConfigError: If any required key is missing or invalid.
    """
    from ..exceptions import ConfigError

    optional_defaults = optional_defaults or {}
    out: dict[str, Any] = {}

    # Map common env names to model field names
    key_to_field = {
        "MQTT_BROKER": "mqtt_broker",
        "MQTT_PORT": "mqtt_port",
        "MINABOX_DEVICE_ID": "minabox_device_id",
        "LOG_LEVEL": "log_level",
    }

    for key in required_keys:
        if key not in os.environ:
            missing = [k for k in required_keys if k not in os.environ]
            raise ConfigError(
                f"Missing required environment variables: {', '.join(sorted(missing))}"
            )
        raw = os.environ[key]
        field = key_to_field.get(key, key.lower())
        if key == "MQTT_PORT":
            try:
                out[field] = int(raw)
            except ValueError as e:
                raise ConfigError(f"MQTT_PORT must be an integer, got '{raw}'") from e
        elif key == "LOG_LEVEL":
            out[field] = raw.upper()
        else:
            out[field] = raw

    for key, default in optional_defaults.items():
        field = key_to_field.get(key, key.lower())
        if field in out:
            continue
        raw = os.environ.get(key)
        if raw is None or raw == "":
            out[field] = default
        else:
            if key == "MQTT_PORT" or "PORT" in key.upper():
                try:
                    out[field] = int(raw)
                except ValueError:
                    out[field] = default
            else:
                out[field] = raw

    return out
