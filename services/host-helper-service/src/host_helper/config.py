"""Configuration for Host-Helper service."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ConfigError(Exception):
    """Raised when configuration cannot be loaded."""


def _get_required_env(key: str) -> str:
    val = os.environ.get(key)
    if not val or not str(val).strip():
        raise ConfigError(f"Missing or empty required environment variable: {key}")
    return str(val).strip()


def load_config() -> dict:
    """Load config from environment. Returns a simple dict."""
    log_level = _get_required_env("LOG_LEVEL").upper()
    api_key = _get_required_env("HOST_HELPER_API_KEY")
    port = int(os.environ.get("HOST_HELPER_PORT", "8000"))
    env_file_path = os.environ.get("ENV_FILE_PATH", "/workspace/.env")
    allowed_base = os.environ.get("ALLOWED_BASE_PATHS", "/media,/mnt,/home/pi")
    allowed_base_paths = [p.strip() for p in allowed_base.split(",") if p.strip()]
    host_proc = os.environ.get("HOST_PROC", "/host/proc")
    host_etc_hostname = os.environ.get("HOST_ETC_HOSTNAME", "/host/etc/hostname")
    host_root = os.environ.get("HOST_ROOT", "")
    host_ip = os.environ.get("HOST_IP", "").strip() or None

    return {
        "log_level": log_level,
        "api_key": api_key,
        "port": port,
        "env_file_path": Path(env_file_path),
        "allowed_base_paths": allowed_base_paths,
        "host_proc": host_proc,
        "host_etc_hostname": host_etc_hostname,
        "host_root": host_root,
        "host_ip": host_ip,
    }


def validate_path_under_allowed(path_str: str, allowed_base_paths: list[str]) -> Path:
    """Resolve path and ensure it is under one of the allowed base paths. Raises ValueError if not."""
    if not path_str or ".." in path_str:
        raise ValueError("Invalid path")
    p = Path(path_str).resolve()
    if not p.is_absolute():
        raise ValueError("Path must be absolute")
    for base in allowed_base_paths:
        base_resolved = Path(base).resolve()
        try:
            p.relative_to(base_resolved)
            return p
        except ValueError:
            continue
    raise ValueError("Path not under allowed base paths")
