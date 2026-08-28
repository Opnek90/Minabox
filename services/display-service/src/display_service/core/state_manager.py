"""State manager for display: caches audio status and sleep timer for rendering."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import structlog

from ..render.playing import PlayingView
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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """*clock* is injectable so tests can move time without freezing it.

        Patching ``time.monotonic`` itself is not an option: asyncio reads its
        event loop clock from there, so a frozen one stops every await in the
        process, not just this class.
        """
        self._device_id = device_id
        self._error_timeout = error_timeout
        self._clock = clock
        self._audio: dict[str, Any] = {
            "state": "stopped",
            # Kept so a track change can be recognised: the title lives in the
            # backend's session response, not in the status, and the poll for
            # it has to be pulled forward when the track moves on.
            "track_id": None,
            "volume": 0,
            # The bounds and the step arrive with audio/status. The defaults
            # here are the widest possible range, so a service that starts
            # before the first status shows a plausible bar rather than a wrong
            # one - see render/volume.py for why the raw volume is not enough.
            "min_volume": 0,
            "max_volume": 100,
            "volume_step": 0,
            # position_ms is a snapshot, not a live value: the audio service
            # deliberately keeps it out of its status fingerprint so a playing
            # track does not publish every two seconds. _position_anchor is the
            # local clock reading when it arrived, which is what lets the
            # remaining time be counted here instead of asked for.
            "position_ms": 0,
            "duration_ms": None,
            "muted": False,
            "multiple_output_devices": False,
            "bluetooth_sink_available": False,
        }
        self._sleep_timer: dict[str, Any] = {"active": False, "remaining_ms": None}
        # Where the box stands on the network, from the backend poll. "unknown"
        # until the first answer - which is also what it falls back to when the
        # poll fails, so a stale hotspot screen does not outlive the hotspot.
        self._network: dict[str, Any] = {
            "mode": "unknown",
            "ssid": None,
            "manage_url": None,
            "hotspot": {"active": False, "ssid": None, "password": None},
        }
        self._session: dict[str, Any] = {
            "repeat_mode": "none",
            "shuffle": False,
            "current_title": "",
        }
        self._error_since: float | None = None
        self._position_anchor: float = clock()

    def update_audio(self, topic: str, payload: bytes) -> None:
        """Update cached audio state from audio/status. Clears error on new status."""
        if not topic.endswith("/audio/status"):
            return
        self._error_since = None
        try:
            data = json.loads(payload.decode("utf-8"))
            self._audio["state"] = data.get("state", "stopped")
            self._audio["track_id"] = data.get("track_id")
            self._audio["volume"] = int(data.get("volume", 0))
            self._audio["min_volume"] = int(data.get("min_volume", 0))
            self._audio["max_volume"] = int(data.get("max_volume", 100))
            # 0 means "unknown", which the renderer reads as "draw a bar, not
            # blocks". An older audio service simply does not send it.
            self._audio["volume_step"] = int(data.get("volume_step", 0))
            self._audio["muted"] = bool(data.get("muted", False))
            # A stopped player reports -1, which is not a position.
            position = int(data.get("position_ms") or 0)
            self._audio["position_ms"] = max(0, position)
            duration = data.get("duration_ms")
            self._audio["duration_ms"] = int(duration) if duration else None
            self._position_anchor = self._clock()
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
        self._error_since = self._clock()

    def has_error(self) -> bool:
        """True while an error was reported recently enough to still show it."""
        if self._error_since is None:
            return False
        if self._clock() - self._error_since >= self._error_timeout:
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

    def update_network(self, data: dict[str, Any]) -> None:
        """Update cached network state (from the backend /network-status poll)."""
        hotspot = data.get("hotspot") or {}
        self._network = {
            "mode": data.get("mode", "unknown"),
            "ssid": data.get("ssid"),
            "manage_url": data.get("manage_url"),
            "hotspot": {
                "active": bool(hotspot.get("active")),
                "ssid": hotspot.get("ssid"),
                "password": hotspot.get("password"),
            },
        }

    def get_network(self) -> dict[str, Any]:
        """Return cached network state (mode, ssid, manage_url, hotspot)."""
        return dict(self._network)

    def wants_network_screen(self) -> bool:
        """True while the box cannot be reached the usual way and should say so.

        Only the two states a person can act on: the fallback hotspot is up
        (here are the credentials), or there is no network at all. "Local
        network only" is a mark on the idle screen, not a screen.
        """
        return self._network.get("mode") in ("hotspot", "no_network")

    def update_session(
        self, repeat_mode: str, shuffle: bool, current_title: str = ""
    ) -> None:
        """Update session state (from backend API poll)."""
        self._session["repeat_mode"] = repeat_mode
        self._session["shuffle"] = shuffle
        self._session["current_title"] = current_title

    def is_playing(self) -> bool:
        """True while a track is playing or paused - not stopped."""
        return self._audio["state"] in ("playing", "paused")

    def get_playing_view(self) -> PlayingView:
        """Return what the playing screen needs, with the remainder counted on.

        The count runs from the position in the last status message. Every
        event that moves the position out of band - a seek, a resume, the next
        track - reaches us through the audio service's play command, which
        publishes unconditionally and re-anchors it.
        """
        audio = self._audio
        duration = audio["duration_ms"]
        remaining = None
        if duration:
            elapsed_ms = 0.0
            if audio["state"] == "playing":
                elapsed_ms = max(0.0, self._clock() - self._position_anchor) * 1000
            remaining = int(duration - audio["position_ms"] - elapsed_ms)
        return PlayingView(
            title=self._session["current_title"],
            remaining_ms=remaining,
            duration_ms=duration,
            paused=audio["state"] == "paused",
            muted=bool(audio["muted"]),
        )

    def get_session(self) -> dict[str, Any]:
        """Return current session state (repeat_mode, shuffle)."""
        return dict(self._session)
