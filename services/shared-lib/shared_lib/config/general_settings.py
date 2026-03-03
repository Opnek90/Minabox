from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_general_settings(path: Path) -> dict[str, Any]:
    """Load general settings JSON from the given path.

    Returns an empty dict if the file does not exist, is invalid, or
    cannot be read. Callers are expected to apply their own defaults
    and fall back to environment variables as needed.
    """
    try:
        if not path.exists():
            return {}

        raw = path.read_text(encoding="utf-8")
        data: Any = json.loads(raw)
        if isinstance(data, dict):
            return data

        logger.warning("general_settings_not_dict", path=str(path))
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("general_settings_load_failed", path=str(path), error=str(exc))
        return {}

