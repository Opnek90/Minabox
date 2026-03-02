from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_sleep_timer_minutes() -> int:
    """Read sleep_timer_minutes from general_settings.json (default 30)."""
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            return max(1, int(data.get("sleep_timer_minutes", 30)))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return 30


def read_bedtime_fade_settings() -> tuple[bool, int, int, float]:
    """Read bedtime fade settings.

    Returns:
        (enabled, duration_min, interval_sec, step_pct)
    """
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            enabled = bool(data.get("bedtime_fade_enabled", False))
            duration = max(1, int(data.get("bedtime_fade_duration_minutes", 15)))
            interval = max(5, int(data.get("bedtime_fade_interval_seconds", 30)))
            step = max(
                0.5,
                min(50.0, float(data.get("bedtime_fade_step_percent", 2.0))),
            )
            return (enabled, duration, interval, step)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        pass
    return (False, 15, 30, 2.0)


__all__ = [
    "read_sleep_timer_minutes",
    "read_bedtime_fade_settings",
]

