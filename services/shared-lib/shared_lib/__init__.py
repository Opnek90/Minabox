"""Shared utilities for Minabox services (config, logging, MQTT base, schemas)."""

from __future__ import annotations

from . import config
from . import mqtt
from .logging import setup_structlog
from .exceptions import ConfigError, ConfigLoadError, MinaboxError
from .schemas import BaseHealthResponse, build_health_body

__all__ = [
    "BaseHealthResponse",
    "ConfigError",
    "ConfigLoadError",
    "MinaboxError",
    "build_health_body",
    "config",
    "mqtt",
    "setup_structlog",
]
