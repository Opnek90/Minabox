"""Watches connectivity and brings up the setup hotspot when the box is stranded.

The problem this solves is a chicken-and-egg one. Every other way of starting
the hotspot - the WebUI switch, the factory reset - assumes you can already
reach the box. When the configured Wi-Fi is gone (router off, password
changed, box carried to a friend's house) a non-technical user has no way in
at all.

So this loop runs on the host-helper, which is where the ``nmcli`` plumbing
already lives. Every ``CHECK_INTERVAL`` seconds it asks NetworkManager where
things stand:

* connectivity is back (or a cable got plugged in) -> make sure the hotspot is
  down, reset the timer;
* no connectivity, hotspot not up, and it has been that way past
  ``GRACE_SECONDS`` -> bring the hotspot up so the box is reachable as
  ``Minabox-Setup`` / http://10.42.0.1;
* no connectivity but the hotspot is already up -> every ``RECOVERY_INTERVAL``
  try the saved client profiles again; if one gets online, the hotspot stays
  down.

Anti-flap: after any switch between AP and client mode nothing else happens
for ``SWITCH_COOLDOWN`` seconds. The recovery attempt costs one short AP
outage every few minutes while the box is genuinely offline - the alternative
is staying on the hotspot forever after the home Wi-Fi comes back.

There is no on/off switch yet; that is a later step. For now the only thing
that suppresses the hotspot is a working connection or a plugged-in cable.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable

import structlog

from host_helper import network_ops as ops

logger = structlog.get_logger(__name__)

CHECK_INTERVAL = 20.0
GRACE_SECONDS = 90.0
RECOVERY_INTERVAL = 180.0
SWITCH_COOLDOWN = 60.0

_monitor: NetworkMonitor | None = None


def get_monitor() -> NetworkMonitor | None:
    """The process-wide monitor, or None before the loop has been started."""
    return _monitor


def set_monitor(monitor: NetworkMonitor | None) -> None:
    global _monitor
    _monitor = monitor

_CONNECTED_MODES = ("online", "local_only")


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "").strip() or default)
    except (TypeError, ValueError):
        return default


class NetworkMonitor:
    """Holds the last probe and decides whether the hotspot should be running."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._enabled = (
            enabled
            if enabled is not None
            else os.environ.get("NETWATCH_ENABLED", "true").lower()
            not in ("false", "0", "no")
        )
        self._clock = clock
        self._grace = _env_float("NETWATCH_GRACE_SECONDS", GRACE_SECONDS)
        self._interval = _env_float("NETWATCH_CHECK_INTERVAL", CHECK_INTERVAL)
        self._recovery_interval = _env_float(
            "NETWATCH_RECOVERY_INTERVAL", RECOVERY_INTERVAL
        )
        self._hotspot_ssid = (
            os.environ.get("NETWATCH_HOTSPOT_SSID", "").strip() or ops.HOTSPOT_CONN_ID
        )

        self._offline_since: float | None = None
        self._last_switch: float = 0.0
        self._last_recovery: float = 0.0
        self._state: dict = {
            "mode": "unknown",
            "internet": False,
            "interface": None,
            "interface_type": None,
            "ipv4": None,
            "ssid": None,
            "hotspot": {"active": False, "ssid": None, "password": None},
            "manage_url": None,
            "fallback_enabled": self._enabled,
            "updated_at": None,
        }

    # -- public -----------------------------------------------------------

    def get_state(self) -> dict:
        """The last probe, plus how fresh it is. Safe to call from a request."""
        state = dict(self._state)
        updated = state.get("updated_at")
        state["stale"] = updated is None or (time.time() - updated) > 120
        return state

    async def run_forever(self) -> None:
        # A first pass right away so /network/status is not "unknown" for the
        # first 20 seconds after every restart.
        while True:
            try:
                self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the loop must not die
                logger.warning("netwatch_tick_failed", error=str(exc))
            await asyncio.sleep(self._interval)

    # -- one iteration --------------------------------------------------

    def tick(self) -> None:
        probe = ops.probe()
        now = self._clock()
        if self._enabled:
            self._decide(probe, now)
            # The decision can change the picture (hotspot just came up); the
            # cheapest honest thing is to re-probe rather than guess.
            probe = ops.probe()
        self._state = {
            **probe,
            "fallback_enabled": self._enabled,
            "updated_at": time.time(),
        }

    def _decide(self, probe: dict, now: float) -> None:
        in_cooldown = (now - self._last_switch) < SWITCH_COOLDOWN
        hotspot_active = bool(probe.get("hotspot", {}).get("active"))
        # A non-hotspot connection that actually has an address. The probe
        # reports this even while the hotspot is also up (NetworkManager keeps
        # the AP on wlan0 while a cable carries eth0), which is exactly the
        # case where the hotspot has become redundant.
        has_client_link = bool(probe.get("interface") and probe.get("ipv4"))
        connected = (
            probe.get("internet")
            or has_client_link
            or probe.get("mode") in _CONNECTED_MODES
        )

        if connected:
            self._offline_since = None
            if hotspot_active and not in_cooldown:
                # Connectivity returned by some other route - a cable, most
                # likely. The hotspot has done its job.
                logger.info("netwatch_hotspot_no_longer_needed")
                self._safe(ops.hotspot_down)
                self._last_switch = now
            return

        if hotspot_active:
            if in_cooldown or (now - self._last_recovery) < self._recovery_interval:
                return
            self._last_recovery = now
            self._attempt_reconnect(probe, now)
            return

        # Offline, and not on the hotspot.
        if self._has_ethernet_link(probe):
            # A cable is in but not routing. That is a LAN/DHCP problem, not a
            # reason to start broadcasting an AP nobody asked for.
            self._offline_since = None
            return
        if self._offline_since is None:
            self._offline_since = now
            logger.info("netwatch_offline_grace_started", grace_s=self._grace)
            return
        if (now - self._offline_since) >= self._grace and not in_cooldown:
            logger.info("netwatch_starting_fallback_hotspot", ssid=self._hotspot_ssid)
            if self._safe(lambda: ops.hotspot_up(self._hotspot_ssid)):
                self._last_switch = now
                self._offline_since = None

    def _attempt_reconnect(self, probe: dict, now: float) -> None:
        """Try each saved client profile; fall back to the hotspot if none work."""
        profiles = self._safe(ops.known_client_profiles) or []
        for name in profiles:
            logger.info("netwatch_reconnect_try", profile=name)
            r = self._safe(lambda n=name: ops.run_nmcli(["con", "up", n], timeout=30))
            if r is None or r.returncode != 0:
                continue
            if ops.connectivity() in ("full", "limited", "portal"):
                logger.info("netwatch_reconnect_ok", profile=name)
                self._last_switch = now
                return
        # Nothing worked - "con up" above may have torn the AP down, so make
        # sure it is back.
        logger.info("netwatch_reconnect_failed_keeping_hotspot")
        if self._safe(lambda: ops.hotspot_up(self._hotspot_ssid)):
            self._last_switch = now

    @staticmethod
    def _has_ethernet_link(probe: dict) -> bool:
        return probe.get("interface_type") == "ethernet"

    @staticmethod
    def _safe(fn: Callable):  # type: ignore[type-arg]
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - one bad nmcli call is not fatal
            logger.warning("netwatch_op_failed", error=str(exc))
            return None
