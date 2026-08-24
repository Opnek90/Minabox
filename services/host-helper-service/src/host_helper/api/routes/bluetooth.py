"""Scanning, pairing and connecting Bluetooth devices."""

from __future__ import annotations

import asyncio
import subprocess
import threading

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from host_helper.api.routes.deps import (
    _check_api_key,
    _nsenter_bin,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Bluetooth ─────────────────────────────────────────────────────────────


def _run_bluetoothctl_on_host(
    args: list[str], timeout: int = 15
) -> subprocess.CompletedProcess:
    """Run bluetoothctl on the host, where the Bluetooth management socket is."""
    nsenter_bin = _nsenter_bin()
    # /usr/bin/bluetoothctl is resolved in the host's mount namespace after nsenter
    cmd = [
        str(nsenter_bin),
        "-t",
        "1",
        "-m",
        "-n",
        "--",
        "/usr/bin/bluetoothctl",
    ] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class BluetoothPairBody(BaseModel):
    address: str


@router.get("/bluetooth/scan")
async def bluetooth_scan(_: None = Depends(_check_api_key)) -> dict:
    """Scan for Bluetooth devices and return their address and name.

    One bluetoothctl process is kept alive for the whole 12 seconds. On most
    setups discovery stops the moment the client disconnects, so running
    "scan on" with a timeout would end the scan before anything is listed.
    """
    # Power the adapter on first: a box driven only from the WebUI has never
    # had bluetoothctl run on it, and BlueZ answers NotReady.
    try:
        _run_bluetoothctl_on_host(["power", "on"], timeout=5)
    except Exception:
        pass
    # Keep one client alive so discovery stays active for the full window.
    nsenter_bin = _nsenter_bin()
    cmd_bt = [str(nsenter_bin), "-t", "1", "-m", "-n", "--", "/usr/bin/bluetoothctl"]
    proc = None
    devices: list[dict] = []
    stdout_lines: list[str] = []

    def read_stdout() -> None:
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            stdout_lines.append(line.rstrip("\n\r"))

    try:
        proc = subprocess.Popen(
            cmd_bt,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        proc.stdin.write("power on\n")
        proc.stdin.write("scan on\n")
        proc.stdin.flush()
        await asyncio.sleep(12)
        proc.stdin.write("devices\n")
        proc.stdin.write("scan off\n")
        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.stdin.close()
        try:
            await asyncio.to_thread(proc.wait, 5)
        except subprocess.TimeoutExpired:
            proc.kill()
        await asyncio.to_thread(reader.join, 2)
        for line in stdout_lines:
            if line.startswith("Device "):
                parts = line[7:].strip().split(" ", 1)
                addr = parts[0] if parts else ""
                name = parts[1].strip() if len(parts) > 1 else ""
                if addr:
                    devices.append({"address": addr, "name": name or None})
    except FileNotFoundError:
        return {"devices": []}
    except Exception:
        return {"devices": []}
    return {"devices": devices}


@router.post("/bluetooth/pair")
def bluetooth_pair(
    body: BluetoothPairBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Pair with a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_pair_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["pair", addr], timeout=30)
    except HTTPException:
        raise
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_pair_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth pairing unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Pairing failed").strip()
        logger.warning(
            "bluetooth_pair_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    # Trust so the device can connect automatically when in range
    try:
        _run_bluetoothctl_on_host(["trust", addr], timeout=10)
    except Exception:
        pass
    logger.info("bluetooth_pair_ok", address=addr)
    return {"ok": True, "message": "Paired", "address": addr}


def _parse_bluetooth_devices(output: str) -> dict[str, str | None]:
    """Turn `bluetoothctl devices` output into {address: name}."""
    devices: dict[str, str | None] = {}
    for line in (output or "").strip().splitlines():
        if not line.startswith("Device "):
            continue
        address, _, name = line[len("Device ") :].strip().partition(" ")
        if address:
            devices[address] = name.strip() or None
    return devices


@router.get("/bluetooth/paired")
def bluetooth_paired(_: None = Depends(_check_api_key)) -> dict:
    """Return the paired devices (address, name, connected). No scan.

    Two fixed calls, not one per device. Asking `bluetoothctl info <addr>` for
    every entry used to cost up to five seconds each, so a box with a handful
    of remembered headphones answered slower than the WebUI was willing to
    wait. BlueZ filters the list itself.
    """
    try:
        paired = _run_bluetoothctl_on_host(["devices", "Paired"], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"devices": []}
    if paired.returncode != 0:
        return {"devices": []}

    connected_addresses: set[str] = set()
    try:
        connected = _run_bluetoothctl_on_host(["devices", "Connected"], timeout=10)
        if connected.returncode == 0:
            connected_addresses = set(_parse_bluetooth_devices(connected.stdout))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Knowing the pairs matters more than knowing which one is live.
        pass

    return {
        "devices": [
            {
                "address": address,
                "name": name,
                "connected": address in connected_addresses,
            }
            for address, name in _parse_bluetooth_devices(paired.stdout).items()
        ]
    }


class BluetoothAddressBody(BaseModel):
    address: str


@router.post("/bluetooth/connect")
def bluetooth_connect(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Connect to a paired Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_connect_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["connect", addr], timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_connect_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth connect unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Connect failed").strip()
        logger.warning(
            "bluetooth_connect_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_connect_ok", address=addr)
    return {"ok": True, "message": "Connected", "address": addr}


@router.post("/bluetooth/disconnect")
def bluetooth_disconnect(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Disconnect a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_disconnect_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["disconnect", addr], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_disconnect_error",
            address=addr,
            error=type(e).__name__,
            msg=str(e),
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth disconnect unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Disconnect failed").strip()
        logger.warning(
            "bluetooth_disconnect_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_disconnect_ok", address=addr)
    return {"ok": True, "message": "Disconnected", "address": addr}


@router.post("/bluetooth/remove")
def bluetooth_remove(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Remove (unpair) a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_remove_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["remove", addr], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_remove_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth remove unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Remove failed").strip()
        logger.warning(
            "bluetooth_remove_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_remove_ok", address=addr)
    return {"ok": True, "message": "Removed", "address": addr}
