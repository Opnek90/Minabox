"""State manager for display: caches audio status and sleep timer for rendering."""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class StateManager:
    """Caches audio status (from MQTT) and sleep timer (from backend poll) for display."""

    def __init__(self, device_id: str) -> None:
        self._device_id = device_id
        self._audio: dict[str, Any] = {
            "state": "stopped",
            "volume": 0,
            "muted": False,
            "multiple_output_devices": False,
            "bluetooth_sink_available": False,
        }
        self._sleep_timer: dict[str, Any] = {"active": False, "remaining_ms": None}
        self._session: dict[str, Any] = {"repeat_mode": "none", "shuffle": False}
        self._has_error: bool = False

    def update_audio(self, topic: str, payload: bytes) -> None:
        """Update cached audio state from MQTT audio/status. Clears error on new status."""
        if not topic.endswith("/audio/status"):
            return
        self._has_error = False
        try:
            data = json.loads(payload.decode("utf-8"))
            self._audio["state"] = data.get("state", "stopped")
            self._audio["volume"] = int(data.get("volume", 0))
            self._audio["muted"] = bool(data.get("muted", False))
            self._audio["multiple_output_devices"] = data.get("multiple_output_devices", False)
            self._audio["bluetooth_sink_available"] = data.get("bluetooth_sink_available", False)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            logger.warning("audio_status_parse_failed", error=str(exc))

    def set_error(self) -> None:
        """Set error state (called on audio/error or system/service-error)."""
        self._has_error = True

    def has_error(self) -> bool:
        """Return True if an error was reported (audio/error or system/service-error)."""
        return self._has_error

    def update_sleep_timer(self, active: bool, remaining_ms: int | None) -> None:
        """Update sleep timer state (from backend API poll)."""
        self._sleep_timer["active"] = active
        self._sleep_timer["remaining_ms"] = remaining_ms

    def get_audio(self) -> dict[str, Any]:
        """Return current audio state (state, volume, muted)."""
        return dict(self._audio)

    def get_sleep_timer(self) -> dict[str, Any]:
        """Return current sleep timer state (active, remaining_ms)."""
        return dict(self._sleep_timer)

    def update_session(self, repeat_mode: str, shuffle: bool) -> None:
        """Update session state (from backend API poll)."""
        self._session["repeat_mode"] = repeat_mode
        self._session["shuffle"] = shuffle

    def get_session(self) -> dict[str, Any]:
        """Return current session state (repeat_mode, shuffle)."""
        return dict(self._session)
