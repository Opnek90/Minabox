"""State manager for display: caches audio status and sleep timer for rendering."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from ..render.volume import VolumeView

logger = structlog.get_logger(__name__)

# How long the error indicator stays up after the last error event.
#
# The flag used to be cleared by exactly one thing: an incoming audio/status.
# But the audio service only publishes that when the status actually changed,
# so an error on an otherwise idle box - the backend's temperature warning is
# the reachable case - left the icon on the panel until somebody pressed play.
#
# A corner of a 128x64 panel can honestly express "something went wrong
# recently"; it cannot express "and it is still wrong", because nothing tells
# us that. So the indicator expires on its own.
ERROR_STATE_TIMEOUT = 300.0


class StateManager:
    """Caches audio status (MQTT) and sleep timer (backend poll) for display."""

    def __init__(
        self,
        device_id: str,
        *,
        error_timeout: float = ERROR_STATE_TIMEOUT,
    ) -> None:
        self._device_id = device_id
        self._error_timeout = error_timeout
        self._audio: dict[str, Any] = {
            "state": "stopped",
            "volume": 0,
            # The bounds and the step arrive with audio/status. The defaults
            # here are the widest possible range, so a service that starts
            # before the first status shows a plausible bar rather than a wrong
            # one - see render/volume.py for why the raw volume is not enough.
            "min_volume": 0,
            "max_volume": 100,
            "volume_step": 0,
            "muted": False,
            "multiple_output_devices": False,
            "bluetooth_sink_available": False,
        }
        self._sleep_timer: dict[str, Any] = {"active": False, "remaining_ms": None}
        self._session: dict[str, Any] = {"repeat_mode": "none", "shuffle": False}
        self._error_since: float | None = None

    def update_audio(self, topic: str, payload: bytes) -> None:
        """Update cached audio state from audio/status. Clears error on new status."""
        if not topic.endswith("/audio/status"):
            return
        self._error_since = None
        try:
            data = json.loads(payload.decode("utf-8"))
            self._audio["state"] = data.get("state", "stopped")
            self._audio["volume"] = int(data.get("volume", 0))
            self._audio["min_volume"] = int(data.get("min_volume", 0))
            self._audio["max_volume"] = int(data.get("max_volume", 100))
            # 0 means "unknown", which the renderer reads as "draw a bar, not
            # blocks". An older audio service simply does not send it.
            self._audio["volume_step"] = int(data.get("volume_step", 0))
            self._audio["muted"] = bool(data.get("muted", False))
            self._audio["multiple_output_devices"] = data.get(
                "multiple_output_devices", False
            )
            self._audio["bluetooth_sink_available"] = data.get(
                "bluetooth_sink_available", False
            )
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            logger.warning("audio_status_parse_failed", error=str(exc))

    def set_error(self) -> None:
        """Set error state (called on audio/error or system/service-error)."""
        self._error_since = time.monotonic()

    def has_error(self) -> bool:
        """True while an error was reported recently enough to still show it."""
        if self._error_since is None:
            return False
        if time.monotonic() - self._error_since >= self._error_timeout:
            self._error_since = None
            logger.debug("error_state_expired", after_seconds=self._error_timeout)
            return False
        return True

    def update_sleep_timer(self, active: bool, remaining_ms: int | None) -> None:
        """Update sleep timer state (from backend API poll)."""
        self._sleep_timer["active"] = active
        self._sleep_timer["remaining_ms"] = remaining_ms

    def get_audio(self) -> dict[str, Any]:
        """Return current audio state (state, volume, bounds, muted)."""
        return dict(self._audio)

    def get_volume_view(self) -> VolumeView:
        """Return what the volume HUD needs, resolved from the cached status."""
        audio = self._audio
        return VolumeView(
            volume=audio["volume"],
            min_volume=audio["min_volume"],
            max_volume=audio["max_volume"],
            step=audio["volume_step"],
            muted=bool(audio["muted"]),
        )

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
