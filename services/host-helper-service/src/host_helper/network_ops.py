"""Low-level network operations shared by the routes and the netwatch loop.

Everything here drives ``nmcli`` on the host through
``nsenter -t 1 -n -- chroot /host … nmcli``. The network namespace of PID 1 is
required, otherwise ``wlan0`` is simply not visible from inside the container.

The HTTP routes in ``api/routes/network.py`` are thin wrappers around these
functions; the background monitor in ``netwatch.py`` calls the same ones, so a
hotspot the user starts by hand and one the box brings up on its own go through
exactly the same path.
"""

from __future__ import annotations

import re
import secrets
import subprocess

import structlog
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

# The hotspot profile is always called this. Client profiles are
# ``Minabox-<sanitised SSID>``; the two namespaces do not collide.
HOTSPOT_CONN_ID = "Minabox-Setup"
# NetworkManager's ``ipv4.method shared`` hands the AP this address and runs a
# DHCP server behind it. Not configurable, so it can be shown on the display
# without asking.
HOTSPOT_GATEWAY = "10.42.0.1"

# ``-t`` mode escapes a literal colon inside a field as ``\:``. Split on a colon
# that is not preceded by a backslash so a connection name with a colon in it
# does not shift every field after it.
_TERSE_SPLIT = re.compile(r"(?<!\\):")


def _unescape(value: str) -> str:
    return value.replace("\\:", ":").replace("\\\\", "\\")


def run_nmcli(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run nmcli in the host network namespace so it sees wlan0. Needs pid=host."""
    # Imported here, not at module scope: the routes package pulls this module
    # in on startup, and importing deps from it at load time closes an import
    # cycle (routes -> network -> netwatch -> network_ops -> routes).
    from host_helper.api.routes.deps import _host_root, _host_tool, _nsenter_bin

    root_path = _host_root()
    if _host_tool("usr/bin/nmcli") is None:
        raise HTTPException(
            status_code=503, detail="nmcli not found on host (install NetworkManager)"
        )
    nsenter = _nsenter_bin()
    dbus_addr = "unix:path=/var/run/dbus/system_bus_socket"  # path inside chroot
    cmd = [
        str(nsenter),
        "-t",
        "1",
        "-n",
        "--",
        "chroot",
        str(root_path),
        "env",
        f"DBUS_SYSTEM_BUS_ADDRESS={dbus_addr}",
        "nmcli",
    ] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def wifi_connection_name(ssid: str) -> str:
    """A safe NetworkManager profile name for an SSID."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (ssid or ""))[:32]
    return f"Minabox-{safe}" if safe else "Minabox-WiFi"


# ── Hotspot ────────────────────────────────────────────────────────────────


def hotspot_up(ssid: str = HOTSPOT_CONN_ID, password: str | None = None) -> dict:
    """Bring the AP up. Reuses the existing profile when there is one.

    Reuse matters: the password is generated once and then shown on the
    display and in the WebUI. Recreating the profile on every call - which is
    what the old route did - would hand out a different password each time the
    box fell back to the hotspot.
    """
    existing_pw = _hotspot_saved_password()
    if existing_pw and not password:
        r = run_nmcli(["con", "up", HOTSPOT_CONN_ID], timeout=20)
        if r.returncode == 0:
            logger.info("hotspot_up_reused", ssid=ssid)
            return {"ssid": ssid, "password": existing_pw}
        # Fall through and rebuild it - the stored profile is unusable.
        logger.warning("hotspot_reuse_failed", detail=(r.stderr or r.stdout)[:200])

    password = (password or "").strip() or secrets.token_hex(4)
    try:
        run_nmcli(["con", "delete", HOTSPOT_CONN_ID], timeout=5)
    except Exception:  # noqa: BLE001 - a missing profile is the normal case
        pass
    run_nmcli(
        [
            "con", "add", "type", "wifi", "ifname", "wlan0",
            "autoconnect", "no", "con-name", HOTSPOT_CONN_ID, "ssid", ssid,
        ],
        timeout=10,
    )
    run_nmcli(
        [
            "con", "modify", HOTSPOT_CONN_ID,
            "802-11-wireless.mode", "ap", "ipv4.method", "shared",
        ],
        timeout=5,
    )
    run_nmcli(
        [
            "con", "modify", HOTSPOT_CONN_ID,
            "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
        ],
        timeout=5,
    )
    r = run_nmcli(["con", "up", HOTSPOT_CONN_ID], timeout=20)
    if r.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=(r.stderr or r.stdout or "Hotspot start failed")[:500],
        )
    logger.info("hotspot_up", ssid=ssid)
    return {"ssid": ssid, "password": password}


def hotspot_down() -> None:
    """Stop the hotspot and bring wlan0 back to client mode."""
    run_nmcli(["con", "down", HOTSPOT_CONN_ID], timeout=10)
    logger.info("hotspot_down")


def hotspot_status() -> dict:
    """Whether the hotspot connection is currently activated."""
    try:
        r = run_nmcli(
            ["-t", "-f", "NAME,STATE", "con", "show", "--active"], timeout=5
        )
    except HTTPException:
        return {"active": False, "ssid": None}
    out = (r.stdout or "").strip()
    active = HOTSPOT_CONN_ID in out and "activated" in out.lower()
    return {"active": active, "ssid": HOTSPOT_CONN_ID if active else None}


def _hotspot_saved_password() -> str | None:
    """The PSK stored in the hotspot profile, or None if there is no profile."""
    try:
        r = run_nmcli(
            [
                "-s", "-t", "-f", "802-11-wireless-security.psk",
                "con", "show", HOTSPOT_CONN_ID,
            ],
            timeout=5,
        )
    except HTTPException:
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("802-11-wireless-security.psk:"):
            return line.split(":", 1)[1].strip() or None
    return None


# ── State probe ────────────────────────────────────────────────────────────

_CONNECTED_STATES = ("connected", "connecting")


def _device_status() -> list[dict]:
    r = run_nmcli(
        ["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout=10
    )
    if r.returncode != 0:
        return []
    rows: list[dict] = []
    for line in (r.stdout or "").strip().splitlines():
        parts = _TERSE_SPLIT.split(line)
        if len(parts) < 3:
            continue
        rows.append(
            {
                "device": _unescape(parts[0]),
                "type": parts[1],
                "state": parts[2],
                "connection": _unescape(":".join(parts[3:])) if len(parts) > 3 else "",
            }
        )
    return rows


def connectivity() -> str:
    """NetworkManager's own verdict: none | portal | limited | full | unknown."""
    try:
        r = run_nmcli(["networking", "connectivity", "check"], timeout=10)
    except HTTPException:
        return "unknown"
    value = (r.stdout or "").strip().lower()
    return value if value in ("none", "portal", "limited", "full") else "unknown"


def _device_ipv4(device: str) -> str | None:
    r = run_nmcli(["-t", "-f", "IP4.ADDRESS", "device", "show", device], timeout=10)
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        # IP4.ADDRESS[1]:192.168.1.42/24
        if line.startswith("IP4.ADDRESS"):
            _, _, value = line.partition(":")
            addr = value.strip().split("/", 1)[0].strip()
            if addr:
                return addr
    return None


def _active_wifi_ssid() -> str | None:
    r = run_nmcli(["-t", "-f", "ACTIVE,SSID", "device", "wifi"], timeout=10)
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        parts = _TERSE_SPLIT.split(line, maxsplit=1)
        if len(parts) == 2 and parts[0] == "yes":
            return _unescape(parts[1]) or None
    return None


def known_client_profiles() -> list[str]:
    """Saved Wi-Fi client profiles the box could try to reconnect with."""
    r = run_nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=10)
    if r.returncode != 0:
        return []
    names: list[str] = []
    for line in (r.stdout or "").splitlines():
        parts = _TERSE_SPLIT.split(line)
        if len(parts) < 2:
            continue
        name = _unescape(parts[0])
        if parts[-1].endswith("wireless") and name != HOTSPOT_CONN_ID:
            names.append(name)
    return names


def _classify(hotspot_active: bool, conn: str, has_ipv4: bool) -> str:
    if hotspot_active:
        return "hotspot"
    if conn == "full":
        return "online"
    if conn in ("limited", "portal") or has_ipv4:
        return "local_only"
    return "no_network"


def probe() -> dict:
    """A full snapshot of where the box stands on the network right now.

    Shape is stable so the WebUI and the display can rely on it:

        mode            online | local_only | hotspot | no_network | unknown
        internet        bool - NetworkManager reached the wider internet
        interface       the device carrying the primary connection, or None
        interface_type  "ethernet" | "wifi" | None
        ipv4            dotted address on that interface, or None
        ssid            connected client SSID, or None
        hotspot         {active, ssid, password} - password only while active
        manage_url      the address to reach the WebUI on right now
    """
    try:
        rows = _device_status()
    except HTTPException:
        return {
            "mode": "unknown", "internet": False, "interface": None,
            "interface_type": None, "ipv4": None, "ssid": None,
            "hotspot": {"active": False, "ssid": None, "password": None},
            "manage_url": None,
        }

    hs = hotspot_status()
    hotspot_active = bool(hs.get("active"))
    conn = connectivity()

    primary = None
    for row in rows:
        if row["state"] not in _CONNECTED_STATES:
            continue
        if row["connection"] == HOTSPOT_CONN_ID:
            continue
        if row["type"] == "ethernet":
            primary = row
            break  # a cable wins over Wi-Fi
        if row["type"] == "wifi" and primary is None:
            primary = row

    ipv4 = _device_ipv4(primary["device"]) if primary else None
    interface = primary["device"] if primary else None
    interface_type = (
        "ethernet"
        if primary and primary["type"] == "ethernet"
        else "wifi"
        if primary and primary["type"] == "wifi"
        else None
    )
    ssid = _active_wifi_ssid() if interface_type == "wifi" else None

    mode = _classify(hotspot_active, conn, bool(ipv4))

    if hotspot_active:
        manage_url: str | None = f"http://{HOTSPOT_GATEWAY}"
    elif ipv4:
        manage_url = f"http://{ipv4}"
    else:
        manage_url = None

    return {
        "mode": mode,
        "internet": conn == "full",
        "interface": interface,
        "interface_type": interface_type,
        "ipv4": ipv4,
        "ssid": ssid,
        "hotspot": {
            "active": hotspot_active,
            "ssid": HOTSPOT_CONN_ID if hotspot_active else None,
            "password": _hotspot_saved_password() if hotspot_active else None,
        },
        "manage_url": manage_url,
    }
