"""The decision the connectivity watchdog makes on each tick.

The stakes: start the hotspot too eagerly and a perfectly online box starts
broadcasting an AP nobody asked for; start it too late (or never) and a user
whose router died is locked out of their box.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from host_helper import netwatch


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def ops(monkeypatch):
    """A stand-in for network_ops that records what the monitor asked it to do."""
    calls: list[str] = []
    state = {"probe": _probe("no_network")}

    def probe() -> dict:
        return state["probe"]

    def hotspot_up(ssid="Minabox-Setup", password=None) -> dict:
        calls.append("hotspot_up")
        state["probe"] = _probe("hotspot")
        return {"ssid": ssid, "password": "pw"}

    def hotspot_down() -> None:
        calls.append("hotspot_down")

    def known_client_profiles() -> list[str]:
        return state.get("profiles", [])

    def run_nmcli(args, timeout=30) -> SimpleNamespace:
        calls.append(f"nmcli:{' '.join(args)}")
        rc = state.get("nmcli_rc", 0)
        return SimpleNamespace(returncode=rc, stdout="", stderr="")

    def connectivity() -> str:
        return state.get("connectivity", "none")

    monkeypatch.setattr(netwatch.ops, "probe", probe)
    monkeypatch.setattr(netwatch.ops, "hotspot_up", hotspot_up)
    monkeypatch.setattr(netwatch.ops, "hotspot_down", hotspot_down)
    monkeypatch.setattr(netwatch.ops, "known_client_profiles", known_client_profiles)
    monkeypatch.setattr(netwatch.ops, "run_nmcli", run_nmcli)
    monkeypatch.setattr(netwatch.ops, "connectivity", connectivity)
    return SimpleNamespace(calls=calls, state=state)


def _probe(mode: str, **over) -> dict:
    base = {
        "mode": mode,
        "internet": mode == "online",
        "interface": None,
        "interface_type": None,
        "ipv4": None,
        "ssid": None,
        "hotspot": {"active": mode == "hotspot", "ssid": None, "password": None},
        "manage_url": None,
    }
    base.update(over)
    return base


def _monitor(clock) -> netwatch.NetworkMonitor:
    return netwatch.NetworkMonitor(enabled=True, clock=clock)


def test_hotspot_waits_out_the_grace_period(ops):
    clock = FakeClock()
    mon = _monitor(clock)

    mon.tick()
    assert "hotspot_up" not in ops.calls  # grace just started

    clock.advance(netwatch.GRACE_SECONDS - 1)
    mon.tick()
    assert "hotspot_up" not in ops.calls  # not yet

    clock.advance(2)
    mon.tick()
    assert "hotspot_up" in ops.calls


def test_a_plugged_in_cable_without_internet_never_triggers_the_hotspot(ops):
    clock = FakeClock()
    ops.state["probe"] = _probe(
        "no_network", interface="eth0", interface_type="ethernet"
    )
    mon = _monitor(clock)

    for _ in range(5):
        clock.advance(netwatch.GRACE_SECONDS)
        mon.tick()

    assert "hotspot_up" not in ops.calls


def test_an_online_box_is_left_alone(ops):
    clock = FakeClock()
    ops.state["probe"] = _probe("online", interface="wlan0", interface_type="wifi")
    mon = _monitor(clock)

    clock.advance(netwatch.GRACE_SECONDS * 3)
    mon.tick()

    assert ops.calls == []


def test_hotspot_is_dropped_once_connectivity_returns(ops):
    clock = FakeClock()
    mon = _monitor(clock)
    ops.state["probe"] = _probe("hotspot")

    # A tick while offline on the hotspot, then a cable appears. The hotspot
    # connection is still activated on wlan0, so the probe still says "hotspot"
    # - but now there is also a wired link with an address.
    mon.tick()
    clock.advance(netwatch.SWITCH_COOLDOWN + netwatch.RECOVERY_INTERVAL + 1)
    ops.state["probe"] = _probe(
        "hotspot", interface="eth0", interface_type="ethernet", ipv4="192.168.1.5"
    )
    mon.tick()

    assert "hotspot_down" in ops.calls


def test_recovery_reconnects_to_a_known_network_without_relaunching_the_hotspot(ops):
    clock = FakeClock()
    ops.state["probe"] = _probe("hotspot")
    ops.state["profiles"] = ["HomeNet"]
    ops.state["connectivity"] = "full"
    mon = _monitor(clock)

    mon.tick()  # on the hotspot, offline
    clock.advance(netwatch.RECOVERY_INTERVAL + netwatch.SWITCH_COOLDOWN + 1)
    mon.tick()

    assert "nmcli:con up HomeNet" in ops.calls
    # It got online, so the hotspot is not brought back up.
    assert ops.calls.count("hotspot_up") == 0


def test_disabled_monitor_still_reports_state_but_never_acts(monkeypatch, ops):
    clock = FakeClock()
    mon = netwatch.NetworkMonitor(enabled=False, clock=clock)

    clock.advance(netwatch.GRACE_SECONDS * 3)
    mon.tick()

    assert ops.calls == []
    assert mon.get_state()["mode"] == "no_network"
    assert mon.get_state()["fallback_enabled"] is False


def test_get_state_flags_a_stale_probe(ops):
    mon = _monitor(FakeClock())
    assert mon.get_state()["stale"] is True  # never ticked
    mon.tick()
    assert mon.get_state()["stale"] is False
