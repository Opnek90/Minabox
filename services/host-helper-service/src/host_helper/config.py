"""Configuration for the host-helper service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import structlog
from shared_lib.exceptions import ConfigError

logger = structlog.get_logger(__name__)


def _get_required_env(key: str) -> str:
    val = os.environ.get(key)
    if not val or not str(val).strip():
        raise ConfigError(f"Missing or empty required environment variable: {key}")
    return str(val).strip()


def _optional_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip() or default


@dataclass(frozen=True, slots=True)
class Config:
    """Everything the service reads from the environment, resolved once.

    Frozen and fully populated on purpose. The previous shape was a plain dict,
    which meant every call site repeated the default a second time
    (`cfg.get("workspace_path", "/workspace")`) for a key that load_config()
    always sets. Two places to change one default is one too many, and a typo
    in a key silently produced the fallback instead of failing.
    """

    log_level: str
    api_key: str
    port: int
    env_file_path: Path
    allowed_base_paths: tuple[str, ...]
    host_proc: Path
    host_etc_hostname: Path
    host_root: str
    host_ip: str | None
    workspace_path: Path
    data_path: Path
    audio_storage_path: Path
    default_user: str


def load_config() -> Config:
    """Read the configuration from the environment.

    Raises ConfigError for anything required and missing, so the process exits
    instead of starting half-configured.
    """
    workspace_path = _optional_env("WORKSPACE_PATH", "/workspace")
    return Config(
        log_level=_get_required_env("LOG_LEVEL").upper(),
        api_key=_get_required_env("HOST_HELPER_API_KEY"),
        port=int(_optional_env("HOST_HELPER_PORT", "8000")),
        env_file_path=Path(_optional_env("ENV_FILE_PATH", "/workspace/.env")),
        allowed_base_paths=tuple(
            p.strip()
            for p in _optional_env("ALLOWED_BASE_PATHS", "/media,/mnt,/home/pi").split(
                ","
            )
            if p.strip()
        ),
        host_proc=Path(_optional_env("HOST_PROC", "/host/proc")),
        host_etc_hostname=Path(
            _optional_env("HOST_ETC_HOSTNAME", "/host/etc/hostname")
        ),
        # Deliberately a plain string and allowed to be empty: an empty value
        # means "no host mount", which the path translation treats differently
        # from "/". _host_root() in the routes turns it into a usable Path.
        host_root=os.environ.get("HOST_ROOT", "").strip(),
        host_ip=os.environ.get("HOST_IP", "").strip() or None,
        workspace_path=Path(workspace_path),
        data_path=Path(_optional_env("DATA_PATH", str(Path(workspace_path) / "data"))),
        audio_storage_path=Path(
            _optional_env("AUDIO_STORAGE_PATH", str(Path(workspace_path) / "audio"))
        ),
        default_user=_optional_env("DEFAULT_USER", "pi"),
    )


def validate_path_under_allowed(
    path_str: str, allowed_base_paths: tuple[str, ...] | list[str]
) -> Path:
    """Resolve a path and require it under an allowed base. Raises ValueError."""
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
