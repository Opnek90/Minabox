"""Usage-limit helpers: daily listening cap and allowed-time windows.

RFID-specific behaviour settings (stop on remove, resume on rescan) have
been extracted to :mod:`backend_service.core.rfid_settings`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any


def read_allowed_usage_times() -> list[dict[str, Any]]:
    """Read allowed_usage_times from general_settings.json.

    Empty list = no restriction. When usage_times_enabled is False, returns [].
    """
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            if not bool(data.get("usage_times_enabled", False)):
                return []
            raw = data.get("allowed_usage_times")
            if isinstance(raw, list) and raw:
                return [
                    {
                        "weekday": int(x.get("weekday", 0)),
                        "start": str(x.get("start", "07:00")),
                        "end": str(x.get("end", "19:00")),
                    }
                    for x in raw
                    if isinstance(x, dict) and 0 <= x.get("weekday", 0) <= 6
                ]
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return []


def is_within_allowed_usage_time(now: datetime, slots: list[dict[str, Any]]) -> bool:
    """Return True if now falls within any allowed slot. Empty slots = always allowed."""
    if not slots:
        return True
    try:
        t = now.time()
        wd = now.weekday()  # 0=Monday, 6=Sunday
        for s in slots:
            if s.get("weekday") != wd:
                continue
            start_s = s.get("start", "07:00")
            end_s = s.get("end", "19:00")
            if len(start_s) >= 5 and len(end_s) >= 5:
                start_parts = start_s.split(":")
                end_parts = end_s.split(":")
                start_t = dt_time(int(start_parts[0], 10), int(start_parts[1], 10))
                end_t = dt_time(int(end_parts[0], 10), int(end_parts[1], 10))
                if start_t <= end_t:
                    if start_t <= t <= end_t:
                        return True
                else:
                    if t >= start_t or t <= end_t:
                        return True
    except (ValueError, IndexError, TypeError):
        pass
    return False


def read_daily_limit_settings() -> tuple[bool, int]:
    """Read daily_limit_enabled and daily_limit_minutes from general_settings.json."""
    data_path = os.environ.get("DATA_PATH", "/data")
    gs_path = Path(data_path) / "general_settings.json"
    try:
        if gs_path.exists():
            data = json.loads(gs_path.read_text(encoding="utf-8"))
            enabled = bool(data.get("daily_limit_enabled", False))
            minutes = max(1, min(1440, int(data.get("daily_limit_minutes", 120))))
            return (enabled, minutes)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        pass
    return (False, 120)


__all__ = [
    "read_allowed_usage_times",
    "is_within_allowed_usage_time",
    "read_daily_limit_settings",
]
