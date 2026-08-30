"""WiFi, the setup hotspot, and the IPv4 configuration."""

from __future__ import annotations

import subprocess

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from host_helper import network_ops
from host_helper.api.routes.deps import _check_api_key

logger = structlog.get_logger(__name__)

router = APIRouter()

# Re-exported for maintenance.py, which drives the same hotspot profile during a
# factory reset. The nmcli runner and the hotspot id live in network_ops now so
# the background monitor can share them.
HOTSPOT_CONN_ID = network_ops.HOTSPOT_CONN_ID


def _run_nmcli_host_network(
    args: list[str], timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run nmcli in the host network namespace so it sees wlan0. Needs pid=host."""
    return network_ops.run_nmcli(args, timeout=timeout)


# ── WLAN & Hotspot ─────────────────────────────────────────────────────────


class WifiConnectBody(BaseModel):
    ssid: str
    password: str = ""


class HotspotStartBody(BaseModel):
    ssid: str = "Minabox-Setup"
    password: str = ""


@router.get("/wifi/scan")
def wifi_scan(_: None = Depends(_check_api_key)) -> dict:
    """List the available WiFi networks with their signal strength."""
    try:
        _run_nmcli_host_network(["dev", "wifi", "rescan"], timeout=15)
    except (subprocess.TimeoutExpired, HTTPException, OSError):
        pass
    try:
        r = _run_nmcli_host_network(
            ["-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list"], timeout=25
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="WiFi scan timed out") from e
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(status_code=503, detail=f"WiFi scan failed: {e}") from e
    if r.returncode != 0:
        raise HTTPException(
            status_code=502, detail=(r.stderr or r.stdout or "Scan failed")[:500]
        )
    networks: list[dict] = []
    for line in (r.stdout or "").strip().splitlines():
        parts = line.split(":", 1)
        if len(parts) >= 2:
            networks.append(
                {
                    "ssid": parts[0].strip() or None,
                    "signal": int(parts[1]) if parts[1].strip().isdigit() else 0,
                }
            )
    # Dedupe by SSID, keep max signal
    by_ssid: dict[str, int] = {}
    for n in networks:
        sid = n.get("ssid") or ""
        if sid and (sid not in by_ssid or (n.get("signal") or 0) > by_ssid[sid]):
            by_ssid[sid] = n.get("signal") or 0
    return {
        "networks": [
            {"ssid": s, "signal": by_ssid[s]}
            for s in sorted(by_ssid.keys(), key=lambda x: -by_ssid[x])
        ]
    }


def _wifi_connection_name(ssid: str) -> str:
    """A safe NetworkManager profile name for an SSID."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (ssid or ""))[:32]
    return f"Minabox-{safe}" if safe else "Minabox-WiFi"


@router.post("/wifi/connect")
def wifi_connect(
    body: WifiConnectBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Connect to a WiFi network by SSID and password.

    key-mgmt is set explicitly; without it NetworkManager refuses the profile
    with "property is missing".
    """
    ssid = (body.ssid or "").strip()
    if not ssid:
        raise HTTPException(status_code=400, detail="SSID required")
    password = (body.password or "").strip()
    con_name = _wifi_connection_name(ssid)
    try:
        try:
            _run_nmcli_host_network(["con", "delete", con_name], timeout=5)
        except Exception:
            pass
        _run_nmcli_host_network(
            [
                "con",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "autoconnect",
                "yes",
                "con-name",
                con_name,
                "ssid",
                ssid,
            ],
            timeout=10,
        )
        if password:
            _run_nmcli_host_network(
                [
                    "con",
                    "modify",
                    con_name,
                    "wifi-sec.key-mgmt",
                    "wpa-psk",
                    "wifi-sec.psk",
                    password,
                ],
                timeout=5,
            )
        else:
            _run_nmcli_host_network(
                ["con", "modify", con_name, "wifi-sec.key-mgmt", "none"],
                timeout=5,
            )
        r = _run_nmcli_host_network(["con", "up", con_name], timeout=45)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Connect timed out") from e
    except HTTPException:
        raise
    if r.returncode != 0:
        raise HTTPException(
            status_code=400, detail=(r.stderr or r.stdout or "Connect failed")[:500]
        )
    return {"ok": True, "message": "Connected", "ssid": ssid}


@router.post("/wifi/hotspot/start")
def wifi_hotspot_start(
    body: HotspotStartBody | None = None,
    _: None = Depends(_check_api_key),
) -> dict:
    """Start AP (hotspot). Default SSID Minabox-Setup, optional password.

    An existing profile is reused, so the password the user was shown a moment
    ago still works; only an explicit password in the body forces a rebuild.
    """
    ssid = (body.ssid if body else HOTSPOT_CONN_ID).strip() or HOTSPOT_CONN_ID
    password = (body.password if body else "").strip()
    try:
        result = network_ops.hotspot_up(ssid, password or None)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Hotspot start timed out") from e
    logger.info("wifi_hotspot_started", ssid=result["ssid"])
    return {"ok": True, "message": "Hotspot started", **result}


@router.post("/wifi/hotspot/stop")
def wifi_hotspot_stop(_: None = Depends(_check_api_key)) -> dict:
    """Stop the hotspot and bring wlan0 back to client mode."""
    network_ops.hotspot_down()
    logger.info("wifi_hotspot_stopped")
    return {"ok": True, "message": "Hotspot stopped"}


@router.get("/wifi/hotspot/status")
def wifi_hotspot_status(_: None = Depends(_check_api_key)) -> dict:
    """Return whether the hotspot is currently active."""
    return network_ops.hotspot_status()


@router.get("/network/status")
def network_status(_: None = Depends(_check_api_key)) -> dict:
    """Where the box stands on the network: mode, address, hotspot, manage URL.

    Served from the background monitor's last probe when it is running (no
    extra nmcli calls on a polled endpoint); falls back to a fresh probe
    otherwise, e.g. in tests or right after startup.
    """
    from host_helper.netwatch import get_monitor

    monitor = get_monitor()
    if monitor is not None:
        return monitor.get_state()
    state = network_ops.probe()
    state["fallback_enabled"] = True
    state["stale"] = False
    return state


# ── Network (IP config: DHCP / static) ────────────────────────────────────


def _get_active_connection_name() -> str | None:
    """The first active connection that is not the hotspot."""
    try:
        r = _run_nmcli_host_network(
            ["-t", "-f", "NAME", "con", "show", "--active"], timeout=10
        )
        if r.returncode != 0:
            return None
        for line in (r.stdout or "").strip().splitlines():
            name = line.strip()
            if name and name != HOTSPOT_CONN_ID:
                return name
    except (HTTPException, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _parse_ipv4_address(addr: str) -> tuple[str | None, str | None]:
    """Parse '192.168.1.10/24' -> (address, netmask as prefix or dotted)."""
    if not addr or not addr.strip():
        return (None, None)
    addr = addr.strip().split(",")[0].strip()
    if "/" in addr:
        a, prefix = addr.split("/", 1)
        a = a.strip()
        try:
            p = int(prefix.strip())
            if 0 <= p <= 32:
                return (a if a else None, str(p))
        except ValueError:
            pass
        return (a if a else None, None)
    return (addr, None)


@router.get("/system/network")
def get_network(_: None = Depends(_check_api_key)) -> dict:
    """The IPv4 configuration of the active connection."""
    out = {
        "method": "dhcp",
        "address": None,
        "netmask": None,
        "gateway": None,
        "dns": None,
    }
    con_name = _get_active_connection_name()
    if not con_name:
        return out
    try:
        r = _run_nmcli_host_network(
            [
                "-t",
                "-f",
                "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns",
                "con",
                "show",
                con_name,
            ],
            timeout=10,
        )
        if r.returncode != 0:
            return out
        fields = {}
        for line in (r.stdout or "").strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        method = (fields.get("ipv4.method") or "auto").lower()
        out["method"] = "dhcp" if method == "auto" else "manual"
        addr_str = fields.get("ipv4.addresses") or fields.get("IP4.ADDRESS") or ""
        if addr_str:
            a, nm = _parse_ipv4_address(addr_str)
            out["address"] = a
            out["netmask"] = nm
        out["gateway"] = (
            fields.get("ipv4.gateway") or fields.get("IP4.GATEWAY") or ""
        ).strip() or None
        dns = (fields.get("ipv4.dns") or fields.get("IP4.DNS") or "").strip()
        out["dns"] = dns.split(",")[0].strip() if dns else None
    except (HTTPException, subprocess.TimeoutExpired, OSError):
        pass
    return out


class NetworkBody(BaseModel):
    method: str  # "dhcp" | "manual"
    address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    dns: str | None = None


@router.put("/system/network")
def set_network(
    body: NetworkBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set IPv4 config: DHCP or manual (address, netmask, gateway, dns)."""
    con_name = _get_active_connection_name()
    if not con_name:
        raise HTTPException(
            status_code=503,
            detail="No active connection (use WLAN or connect Ethernet)",
        )
    method = (body.method or "dhcp").strip().lower()
    if method not in ("dhcp", "manual"):
        raise HTTPException(status_code=400, detail="method must be 'dhcp' or 'manual'")
    try:
        # Bring connection down first so the old address/DHCP lease is released;
        # otherwise the interface keeps two addresses, the static and the old
        # DHCP one.
        _run_nmcli_host_network(["con", "down", con_name], timeout=10)
        if method == "dhcp":
            # Clearing the three manual fields is not tidiness, it is the
            # point. NetworkManager in method=auto *adds* whatever sits in
            # ipv4.addresses on top of the DHCP lease, so a profile that once
            # had a static address keeps carrying it: the interface ends up
            # with two addresses, and IP4.ADDRESS[1] - the stale static one -
            # is what /network/status reports as "reachable at". The box then
            # names an address the user does not use.
            r = _run_nmcli_host_network(
                [
                    "con", "modify", con_name,
                    "ipv4.method", "auto",
                    "ipv4.addresses", "",
                    "ipv4.gateway", "",
                    "ipv4.dns", "",
                ],
                timeout=10,
            )
            if r.returncode != 0:
                raise HTTPException(
                    status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
                )
        else:
            address = (body.address or "").strip()
            if not address:
                raise HTTPException(
                    status_code=400, detail="address required for manual config"
                )
            prefix = (body.netmask or "24").strip()
            if prefix.isdigit():
                addr_spec = f"{address}/{prefix}"
            else:
                addr_spec = address
            args = [
                "con",
                "modify",
                con_name,
                "ipv4.method",
                "manual",
                "ipv4.addresses",
                addr_spec,
            ]
            if (body.gateway or "").strip():
                args += ["ipv4.gateway", body.gateway.strip()]
            if (body.dns or "").strip():
                args += ["ipv4.dns", body.dns.strip()]
            r = _run_nmcli_host_network(args, timeout=10)
            if r.returncode != 0:
                raise HTTPException(
                    status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
                )
        r = _run_nmcli_host_network(["con", "up", con_name], timeout=15)
        if r.returncode != 0:
            raise HTTPException(
                status_code=502, detail=(r.stderr or r.stdout or "Apply failed")[:500]
            )
    except HTTPException:
        raise
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("set_network_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set network") from e
    logger.info("network_set", method=method, connection=con_name)
    return {"ok": True, "method": "dhcp" if method == "dhcp" else "manual"}
