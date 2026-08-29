"""Parsing the real nmcli output that the network probe is built on.

Everything here is string handling: a misread of `nmcli` is what would make
the box put the wrong address on its display or start a hotspot when it is
perfectly online.
"""

from __future__ import annotations

from types import SimpleNamespace

from host_helper import network_ops


def _run(stdout: str, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def _router(monkeypatch, table: dict[tuple[str, ...], SimpleNamespace]) -> None:
    """Route run_nmcli calls to canned output, keyed by a prefix of the args."""

    def fake(args: list[str], timeout: int = 30) -> SimpleNamespace:
        for prefix, result in table.items():
            if tuple(args[: len(prefix)]) == prefix:
                return result
        return _run("", returncode=1)

    monkeypatch.setattr(network_ops, "run_nmcli", fake)


ONLINE_TABLE = {
    ("networking", "connectivity", "check"): _run("full\n"),
    ("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"): _run(
        "eth0:ethernet:connected:Wired connection 1\n"
        "wlan0:wifi:connected:HomeNet\n"
        "p2p-dev-wlan0:wifi-p2p:disconnected:\n"
    ),
    ("-t", "-f", "NAME,STATE", "con", "show", "--active"): _run(
        "Wired connection 1:activated\nHomeNet:activated\n"
    ),
    ("-t", "-f", "IP4.ADDRESS", "device", "show", "eth0"): _run(
        "IP4.ADDRESS[1]:192.168.1.42/24\n"
    ),
}


def test_a_wired_box_with_internet_is_online_and_shows_its_lan_address(monkeypatch):
    _router(monkeypatch, ONLINE_TABLE)
    state = network_ops.probe()
    assert state["mode"] == "online"
    assert state["internet"] is True
    assert state["interface"] == "eth0"
    assert state["interface_type"] == "ethernet"
    assert state["ipv4"] == "192.168.1.42"
    assert state["manage_url"] == "http://192.168.1.42"
    assert state["hotspot"]["active"] is False


def test_wifi_connected_without_internet_is_local_only(monkeypatch):
    table = dict(ONLINE_TABLE)
    table[("networking", "connectivity", "check")] = _run("limited\n")
    table[("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")] = _run(
        "wlan0:wifi:connected:HomeNet\n"
    )
    table[("-t", "-f", "IP4.ADDRESS", "device", "show", "wlan0")] = _run(
        "IP4.ADDRESS[1]:192.168.1.50/24\n"
    )
    table[("-t", "-f", "ACTIVE,SSID", "device", "wifi")] = _run(
        "yes:HomeNet\nno:Other\n"
    )
    _router(monkeypatch, table)
    state = network_ops.probe()
    assert state["mode"] == "local_only"
    assert state["internet"] is False
    assert state["ssid"] == "HomeNet"


def test_nothing_connected_is_no_network(monkeypatch):
    _router(
        monkeypatch,
        {
            ("networking", "connectivity", "check"): _run("none\n"),
            (
                "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status",
            ): _run("wlan0:wifi:disconnected:\neth0:ethernet:unavailable:\n"),
            ("-t", "-f", "NAME,STATE", "con", "show", "--active"): _run(""),
        },
    )
    state = network_ops.probe()
    assert state["mode"] == "no_network"
    assert state["interface"] is None
    assert state["manage_url"] is None


def test_hotspot_mode_reports_the_saved_password(monkeypatch):
    _router(
        monkeypatch,
        {
            ("networking", "connectivity", "check"): _run("none\n"),
            (
                "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status",
            ): _run("wlan0:wifi:connected:Minabox-Setup\n"),
            ("-t", "-f", "NAME,STATE", "con", "show", "--active"): _run(
                "Minabox-Setup:activated\n"
            ),
            (
                "-s", "-t", "-f", "802-11-wireless-security.psk",
                "con", "show", "Minabox-Setup",
            ): _run("802-11-wireless-security.psk:a1b2c3d4\n"),
        },
    )
    state = network_ops.probe()
    assert state["mode"] == "hotspot"
    assert state["hotspot"] == {
        "active": True,
        "ssid": "Minabox-Setup",
        "password": "a1b2c3d4",
    }
    assert state["manage_url"] == "http://10.42.0.1"


def test_a_connection_name_with_a_colon_does_not_shift_the_fields(monkeypatch):
    _router(
        monkeypatch,
        {
            ("networking", "connectivity", "check"): _run("full\n"),
            (
                "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status",
            ): _run("eth0:ethernet:connected:Home\\: guest\n"),
            ("-t", "-f", "IP4.ADDRESS", "device", "show", "eth0"): _run(
                "IP4.ADDRESS[1]:10.0.0.9/24\n"
            ),
        },
    )
    state = network_ops.probe()
    assert state["interface"] == "eth0"
    assert state["ipv4"] == "10.0.0.9"


def test_known_client_profiles_excludes_the_hotspot(monkeypatch):
    _router(
        monkeypatch,
        {
            ("-t", "-f", "NAME,TYPE", "connection", "show"): _run(
                "HomeNet:802-11-wireless\n"
                "Minabox-Setup:802-11-wireless\n"
                "Wired connection 1:802-3-ethernet\n"
            ),
        },
    )
    assert network_ops.known_client_profiles() == ["HomeNet"]
