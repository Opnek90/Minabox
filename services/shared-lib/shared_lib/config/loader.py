"""Load JSON config files and validate with Pydantic schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel

from ..exceptions import ConfigError

T = TypeVar("T", bound=BaseModel)


def load_json_config(
    path: Path,
    schema_class: type[T],
    *,
    create_if_missing: bool = False,
    default_factory: Callable[[], T] | None = None,
) -> T:
    """Load and validate JSON config from a file.

    Args:
        path: Path to the JSON config file.
        schema_class: Pydantic model class to validate and parse into.
        create_if_missing: If True and file does not exist, use default_factory
            when provided; otherwise raise ConfigError.
        default_factory: Callable that returns a default instance when file
            is missing and create_if_missing is True.

    Returns:
        Validated config instance.

    Raises:
        ConfigError: If file is missing (and not create_if_missing with factory),
            read fails, JSON is invalid, or validation fails.
    """
    if not path.exists():
        if create_if_missing and default_factory is not None:
            return default_factory()
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read configuration file: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in configuration file: {path}") from exc

    return schema_class.model_validate(data)
