"""Shared utilities for Minabox services (config, logging, MQTT base, schemas)."""

from __future__ import annotations

from . import config
from . import mqtt
from .logging import setup_structlog
from .exceptions import ConfigError, ConfigLoadError, MinaboxError
from .schemas import BaseHealthResponse, build_health_body
from .version import get_git_sha, get_version, version_info

__all__ = [
    "BaseHealthResponse",
    "ConfigError",
    "ConfigLoadError",
    "MinaboxError",
    "build_health_body",
    "config",
    "get_git_sha",
    "get_version",
    "mqtt",
    "setup_structlog",
    "version_info",
]
