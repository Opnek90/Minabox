"""REST API for Host-Helper proxy: audio path, move, system and hardware control.

Almost every route here is a thin proxy in front of the Host-Helper. The
request/response handling is identical for all of them, so it lives in
_proxy() (strict: propagate failures) and _proxy_optional() (soft: fall back to
a neutral payload when the Host-Helper is absent or unhappy).

All calls share one pooled httpx.AsyncClient - creating a client per request
meant a fresh TCP handshake for every button press in the WebUI.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.core.temperature_logger import get_current_alert
from backend_service.models.database import TemperatureReading

logger = structlog.get_logger(__name__)
router = APIRouter()

HOST_HELPER_TIMEOUT = 10.0

_NOT_CONFIGURED = "Host-Helper not configured (HOST_HELPER_API_KEY missing)"
_NOT_CONFIGURED_SHORT = "Host-Helper not configured"
_UNREACHABLE = "Host-Helper unreachable"


def _host_helper_url() -> str:
    return os.environ.get("HOST_HELPER_URL", "http://host-helper:8000").rstrip("/")


def _host_helper_api_key() -> str | None:
    return os.environ.get("HOST_HELPER_API_KEY", "").strip() or None


def _allowed_audio_paths() -> list[str]:
    raw = os.environ.get("ALLOWED_AUDIO_PATHS", "/media,/mnt,/home/pi")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _validate_path(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="path required")
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    p = Path(path).resolve()
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    allowed = _allowed_audio_paths()
    for base in allowed:
        try:
            p.relative_to(Path(base).resolve())
            return
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Path not under allowed base paths")


# ── Shared HTTP client ───────────────────────────────────────────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return the pooled client, creating it on first use.

    Timeouts are always passed per request, because the endpoints range from a
    10s status poll to a 30 minute OS update.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT)
    return _client


async def close_host_helper_client() -> None:
    """Close the pooled client. Called from the service shutdown path."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


# ── Proxy helpers ────────────────────────────────────────────────────────────


def _extract_detail(response: httpx.Response, fallback: str) -> str:
    """Pull `detail` out of a Host-Helper error body, tolerating junk."""
    if not response.content:
        return fallback
    try:
        payload = response.json() or {}
    except Exception:
        return (response.text or fallback)[:500]
    detail = payload.get("detail", fallback) if isinstance(payload, dict) else fallback
    if isinstance(detail, list):
        detail = detail[0] if detail else fallback
    return str(detail)


async def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    timeout: float,
    json: dict | None = None,
    params: dict | None = None,
    files: Any = None,
) -> httpx.Response:
    return await _get_client().request(
        method,
        f"{_host_helper_url()}{path}",
        json=json,
        params=params,
        files=files,
        headers={"X-Api-Key": api_key},
        timeout=timeout,
    )


async def _proxy(
    method: str,
    path: str,
    *,
    error_message: str,
    log_event: str,
    timeout: float = HOST_HELPER_TIMEOUT,
    json: dict | None = None,
    params: dict | None = None,
    files: Any = None,
    not_configured_detail: str = _NOT_CONFIGURED,
    unreachable_detail: str = _UNREACHABLE,
    ok_statuses: tuple[int, ...] = (200,),
) -> Any:
    """Proxy a call to the Host-Helper and propagate failures to the caller.

    A 401 from the Host-Helper is deliberately reported as 503, not 401: the
    WebUI treats 401 as "your session expired" and would log the user out over
    what is really a server-side misconfiguration.
    """
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail=not_configured_detail)
    try:
        r = await _request(
            method, path, api_key, timeout=timeout, json=json, params=params, files=files
        )
    except httpx.RequestError as e:
        logger.warning(log_event, error=str(e))
        raise HTTPException(status_code=503, detail=unreachable_detail) from e

    if r.status_code == 401:
        raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
    if r.status_code not in ok_statuses and r.status_code >= 400:
        raise HTTPException(
            status_code=min(r.status_code, 502),
            detail=_extract_detail(r, error_message),
        )
    if r.status_code not in ok_statuses:
        raise HTTPException(status_code=503, detail="Host-Helper request failed")
    return r.json()


async def _proxy_optional(
    path: str,
    *,
    fallback: dict,
    log_event: str,
    method: str = "GET",
    timeout: float = HOST_HELPER_TIMEOUT,
    params: dict | None = None,
) -> dict:
    """Proxy a read-only call, returning `fallback` whenever anything goes wrong.

    Used for status widgets that must not break the settings page just because
    the Host-Helper is missing or restarting.
    """
    api_key = _host_helper_api_key()
    if not api_key:
        return dict(fallback)
    try:
        r = await _request(method, path, api_key, timeout=timeout, params=params)
        if r.status_code == 200:
            payload = r.json()
            if payload is not None:
                return payload
    except Exception as e:
        logger.debug(log_event, error=str(e))
    return dict(fallback)


# ── Request bodies ───────────────────────────────────────────────────────────


class AudioPathBody(BaseModel):
    path: str


class MoveAudioBody(BaseModel):
    source: str
    destination: str


class TimezoneBody(BaseModel):
    timezone: str


class HostnameBody(BaseModel):
    hostname: str


class BoardLedsBody(BaseModel):
    stealth: bool


class NetworkBody(BaseModel):
    method: str
    address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    dns: str | None = None


class PasswordBody(BaseModel):
    username: str
    new_password: str


class SshToggleBody(BaseModel):
    enable: bool


class FactoryResetBody(BaseModel):
    delete_audio: bool = False


class WifiConnectBody(BaseModel):
    ssid: str
    password: str = ""


class HotspotStartBody(BaseModel):
    ssid: str = "Minabox-Setup"
    password: str = ""


class UsbImportBody(BaseModel):
    device_id: str
    source_paths: list[str]


class UsbEjectBody(BaseModel):
    device_id: str


class BluetoothPairBody(BaseModel):
    address: str


# ── Status & local data ──────────────────────────────────────────────────────


@router.get("/host-status")
async def get_host_status() -> dict:
    return await _proxy_optional(
        "/host-status",
        fallback={
            "hostname": None,
            "ip": None,
            "uptime_seconds": None,
            "memory": None,
            "cpu": None,
            "disk": None,
            "temperature_celsius": None,
        },
        log_event="host_helper_host_status_failed",
    )


@router.get("/temperature-history")
def get_temperature_history(
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> dict:
    """Return temperature readings for the last N hours (default 24).

    Sync on purpose: the query is blocking SQLAlchemy, so FastAPI runs it in
    the threadpool instead of on the event loop.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        db.query(TemperatureReading)
        .filter(TemperatureReading.recorded_at >= since)
        .order_by(TemperatureReading.recorded_at)
        .all()
    )
    readings = [
        {"t": r.recorded_at.isoformat(), "celsius": round(r.temperature_celsius, 1)}
        for r in rows
    ]
    return {"readings": readings}


@router.get("/current-alert")
async def get_current_system_alert() -> dict:
    """Return the currently active system alert (e.g. overheating) for the WebUI bar."""
    alert = get_current_alert()
    return {"alert": alert}


# ── Audio path & move ────────────────────────────────────────────────────────


@router.get("/audio-path")
async def get_audio_path() -> dict:
    """Return the configured media path, falling back to the running config."""
    fallback = {"path": get_config().env.audio_storage_path}
    data = await _proxy_optional(
        "/audio-path",
        fallback={},
        log_event="host_helper_get_audio_path_failed",
    )
    saved = data.get("audio_files_path")
    return {"path": saved} if saved else fallback


@router.put("/audio-path")
async def put_audio_path(body: AudioPathBody) -> dict:
    path = body.path.strip()
    _validate_path(path)
    return await _proxy(
        "POST",
        "/apply-audio-path",
        json={"audio_files_path": path},
        error_message="Invalid path",
        log_event="host_helper_apply_audio_path_failed",
        unreachable_detail="Host-Helper unreachable. Restart stack after adding host-helper.",
    )


@router.post("/move-audio")
async def move_audio(body: MoveAudioBody):
    _validate_path(body.source)
    _validate_path(body.destination)
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    try:
        r = await _request(
            "POST",
            "/move",
            api_key,
            timeout=HOST_HELPER_TIMEOUT,
            json={"source": body.source, "destination": body.destination},
        )
    except httpx.RequestError as e:
        logger.warning("host_helper_move_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable.") from e

    if r.status_code == 401:
        raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
    if r.status_code == 409:
        raise HTTPException(status_code=409, detail="Move already in progress")
    if r.status_code in (400, 404):
        raise HTTPException(
            status_code=r.status_code, detail=_extract_detail(r, "Move failed")
        )
    if r.status_code not in (200, 202):
        raise HTTPException(status_code=503, detail="Host-Helper request failed")
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.get("/move-status")
async def get_move_status() -> dict:
    return await _proxy_optional(
        "/move-status",
        fallback={"status": "idle", "total": 0, "current": 0, "error": None},
        log_event="host_helper_move_status_failed",
    )


# ── Power & lifecycle ────────────────────────────────────────────────────────


@router.post("/reboot")
async def reboot_host() -> dict:
    return await _proxy(
        "POST",
        "/reboot",
        error_message="Reboot failed",
        log_event="host_helper_reboot_failed",
    )


@router.post("/shutdown")
async def shutdown_host() -> dict:
    """Shutdown the host (Pi). Requires Host-Helper."""
    return await _proxy(
        "POST",
        "/shutdown",
        error_message="Shutdown failed",
        log_event="host_helper_shutdown_failed",
    )


@router.post("/restart")
async def restart_services() -> dict:
    """Restart Minabox containers. Proxied to Host-Helper (runs on host)."""
    return await _proxy(
        "POST",
        "/restart",
        timeout=125.0,
        error_message="Restart failed",
        log_event="host_helper_restart_failed",
    )


@router.get("/syslog")
async def get_syslog(n: int = 200, source: str = "kernel") -> dict:
    """Return host kernel or docker unit logs. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/syslog",
        params={"n": n, "source": source},
        timeout=20.0,
        fallback={"lines": [], "source": source},
        log_event="host_helper_syslog_failed",
    )


# ── System settings ──────────────────────────────────────────────────────────


@router.put("/timezone")
async def put_timezone(body: TimezoneBody) -> dict:
    """Set host timezone (e.g. Europe/Berlin). Proxied to Host-Helper."""
    return await _proxy(
        "PUT",
        "/system/timezone",
        timeout=15.0,
        json={"timezone": body.timezone},
        error_message="Failed to set timezone",
        log_event="host_helper_timezone_failed",
    )


@router.get("/hostname")
async def get_hostname() -> dict:
    """Return current host hostname. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/hostname",
        fallback={"hostname": None},
        log_event="host_helper_hostname_failed",
    )


@router.put("/hostname")
async def put_hostname(body: HostnameBody) -> dict:
    """Set host hostname. Proxied to Host-Helper."""
    return await _proxy(
        "PUT",
        "/system/hostname",
        timeout=15.0,
        json={"hostname": body.hostname},
        error_message="Failed to set hostname",
        log_event="host_helper_hostname_failed",
    )


@router.get("/board-leds")
async def get_board_leds() -> dict:
    """Return board LED state (stealth). Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/board-leds",
        fallback={"stealth": False, "power_led": "on", "activity_led": "on"},
        log_event="host_helper_board_leds_failed",
    )


@router.put("/board-leds")
async def put_board_leds(body: BoardLedsBody) -> dict:
    """Set board LEDs (stealth on/off). Proxied to Host-Helper."""
    return await _proxy(
        "PUT",
        "/system/board-leds",
        json={"stealth": body.stealth},
        error_message="Failed to set board LEDs",
        log_event="host_helper_board_leds_failed",
    )


@router.get("/network")
async def get_network() -> dict:
    """Return current IP config (DHCP/manual). Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/network",
        fallback={
            "method": "dhcp",
            "address": None,
            "netmask": None,
            "gateway": None,
            "dns": None,
        },
        log_event="host_helper_network_failed",
    )


@router.put("/network")
async def put_network(body: NetworkBody) -> dict:
    """Set IP config (DHCP or manual). Proxied to Host-Helper."""
    return await _proxy(
        "PUT",
        "/system/network",
        timeout=15.0,
        json={
            "method": body.method,
            "address": body.address,
            "netmask": body.netmask,
            "gateway": body.gateway,
            "dns": body.dns,
        },
        error_message="Failed to set network",
        log_event="host_helper_network_failed",
    )


@router.post("/password")
async def set_password(body: PasswordBody) -> dict:
    """Change system user password. Proxied to Host-Helper. Password is never logged."""
    return await _proxy(
        "POST",
        "/system/password",
        timeout=15.0,
        json={"username": body.username, "new_password": body.new_password},
        error_message="Failed to set password",
        log_event="host_helper_password_failed",
    )


@router.post("/docker-prune")
async def docker_prune() -> dict:
    """Run docker system prune. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/system/docker-prune",
        timeout=310.0,
        error_message="Docker prune failed",
        log_event="host_helper_docker_prune_failed",
    )


@router.get("/ssh-status")
async def get_ssh_status() -> dict:
    """Return SSH enabled/active on host. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/ssh-status",
        fallback={"enabled": False, "active": False},
        log_event="host_helper_ssh_status_failed",
    )


@router.post("/ssh-toggle")
async def ssh_toggle(body: SshToggleBody) -> dict:
    """Enable or disable SSH on host. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/system/ssh-toggle",
        timeout=20.0,
        json={"enable": body.enable},
        error_message="SSH toggle failed",
        log_event="host_helper_ssh_toggle_failed",
    )


@router.post("/factory-reset")
async def factory_reset(body: FactoryResetBody | None = None) -> dict:
    """Factory reset: clear DB/config, optional audio, start hotspot, restart."""
    return await _proxy(
        "POST",
        "/system/factory-reset",
        timeout=180.0,
        json={"delete_audio": body.delete_audio if body else False},
        error_message="Factory reset failed",
        log_event="host_helper_factory_reset_failed",
    )


@router.post("/update-minabox")
async def update_minabox() -> dict:
    """Pull images and restart containers. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/system/update-minabox",
        timeout=620.0,
        error_message="Update failed",
        log_event="host_helper_update_minabox_failed",
    )


@router.post("/update-os")
async def update_os() -> dict:
    """Run OS update (apt upgrade) on host. Proxied to Host-Helper. Blocks until done."""
    return await _proxy(
        "POST",
        "/system/update-os",
        timeout=1900.0,
        error_message="OS update failed",
        log_event="host_helper_update_os_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.get("/update-os/log")
async def update_os_log() -> dict:
    """OS update log and running status. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/update-os/log",
        fallback={"running": False, "log": ""},
        log_event="host_helper_update_os_log_failed",
    )


@router.get("/version")
async def get_version() -> dict:
    """Current version and update availability. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/version",
        timeout=15.0,
        fallback={
            "current_version": "unknown",
            "current_commit": None,
            "update_available": False,
        },
        log_event="host_helper_version_failed",
    )


@router.get("/time-status")
async def get_time_status() -> dict:
    """Return host timezone, NTP sync, local time. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/system/time-status",
        fallback={"timezone": None, "ntp_sync": False, "local_time": None},
        log_event="host_helper_time_status_failed",
    )


# ── WiFi & hotspot ───────────────────────────────────────────────────────────


@router.get("/wifi/scan")
async def wifi_scan() -> dict:
    """List available WiFi networks. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/wifi/scan",
        timeout=30.0,
        fallback={"networks": []},
        log_event="host_helper_wifi_scan_failed",
    )


@router.post("/wifi/connect")
async def wifi_connect(body: WifiConnectBody) -> dict:
    """Connect to WiFi. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/wifi/connect",
        timeout=50.0,
        json={"ssid": body.ssid, "password": body.password},
        error_message="Connect failed",
        log_event="host_helper_wifi_connect_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/wifi/hotspot/start")
async def wifi_hotspot_start(body: HotspotStartBody | None = Body(None)) -> dict:
    """Start WiFi hotspot. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/wifi/hotspot/start",
        timeout=25.0,
        json=(body.model_dump() if body else {}),
        error_message="Hotspot start failed",
        log_event="host_helper_wifi_hotspot_start_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/wifi/hotspot/stop")
async def wifi_hotspot_stop() -> dict:
    """Stop WiFi hotspot. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/wifi/hotspot/stop",
        timeout=15.0,
        error_message="Hotspot stop failed",
        log_event="host_helper_wifi_hotspot_stop_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.get("/wifi/hotspot/status")
async def wifi_hotspot_status() -> dict:
    """Hotspot active? Proxied to Host-Helper."""
    return await _proxy_optional(
        "/wifi/hotspot/status",
        fallback={"active": False, "ssid": None},
        log_event="host_helper_wifi_hotspot_status_failed",
    )


# ── USB ──────────────────────────────────────────────────────────────────────


@router.get("/usb/devices")
async def usb_devices() -> dict:
    """List USB block devices. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/usb/devices",
        timeout=20.0,
        fallback={"devices": []},
        log_event="host_helper_usb_devices_failed",
    )


@router.get("/usb/{device_id}/files")
async def usb_files(device_id: str) -> dict:
    """List files on USB device. Proxied to Host-Helper."""
    return await _proxy(
        "GET",
        f"/usb/{device_id}/files",
        timeout=25.0,
        error_message="Failed",
        log_event="host_helper_usb_files_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/usb/import")
async def usb_import(body: UsbImportBody) -> dict:
    """Import from USB to audio storage. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/usb/import",
        timeout=300.0,
        json={"device_id": body.device_id, "source_paths": body.source_paths},
        error_message="Import failed",
        log_event="host_helper_usb_import_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/usb/eject")
async def usb_eject(body: UsbEjectBody) -> dict:
    """Eject USB device. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/usb/eject",
        timeout=20.0,
        json={"device_id": body.device_id},
        error_message="Eject failed",
        log_event="host_helper_usb_eject_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


# ── Bluetooth ────────────────────────────────────────────────────────────────


@router.get("/bluetooth/scan")
async def bluetooth_scan() -> dict:
    """Scan for Bluetooth devices. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/bluetooth/scan",
        timeout=25.0,
        fallback={"devices": []},
        log_event="host_helper_bluetooth_scan_failed",
    )


@router.get("/bluetooth/paired")
async def bluetooth_paired() -> dict:
    """Return paired Bluetooth devices. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/bluetooth/paired",
        timeout=15.0,
        fallback={"devices": []},
        log_event="host_helper_bluetooth_paired_failed",
    )


@router.post("/bluetooth/pair")
async def bluetooth_pair(body: BluetoothPairBody) -> dict:
    """Pair with Bluetooth device. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/bluetooth/pair",
        timeout=35.0,
        json={"address": body.address},
        error_message="Pairing failed",
        log_event="host_helper_bluetooth_pair_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/bluetooth/connect")
async def bluetooth_connect(body: BluetoothPairBody) -> dict:
    """Connect to paired Bluetooth device. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/bluetooth/connect",
        timeout=20.0,
        json={"address": body.address},
        error_message="Connect failed",
        log_event="host_helper_bluetooth_connect_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/bluetooth/disconnect")
async def bluetooth_disconnect(body: BluetoothPairBody) -> dict:
    """Disconnect Bluetooth device. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/bluetooth/disconnect",
        timeout=15.0,
        json={"address": body.address},
        error_message="Disconnect failed",
        log_event="host_helper_bluetooth_disconnect_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


@router.post("/bluetooth/remove")
async def bluetooth_remove(body: BluetoothPairBody) -> dict:
    """Remove (unpair) Bluetooth device. Proxied to Host-Helper."""
    return await _proxy(
        "POST",
        "/bluetooth/remove",
        timeout=15.0,
        json={"address": body.address},
        error_message="Remove failed",
        log_event="host_helper_bluetooth_remove_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


# ── Backup ───────────────────────────────────────────────────────────────────


@router.get("/backup/download")
async def backup_download() -> Response:
    """Download backup ZIP (DB, configs, state). Proxied to Host-Helper."""
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    try:
        r = await _request("GET", "/backup/download", api_key, timeout=60.0)
    except httpx.RequestError as e:
        logger.warning("host_helper_backup_download_failed", error=str(e))
        raise HTTPException(status_code=503, detail=_UNREACHABLE) from e

    if r.status_code == 401:
        raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
    if r.status_code != 200:
        raise HTTPException(
            status_code=min(r.status_code, 502), detail="Backup download failed"
        )
    disposition = r.headers.get(
        "content-disposition", "attachment; filename=minabox-backup.zip"
    )
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "application/zip"),
        headers={"Content-Disposition": disposition},
    )


@router.post("/backup/restore")
async def backup_restore(file: UploadFile = File(...)) -> dict:
    """Upload backup ZIP and restore. Proxied to Host-Helper."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip file")
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to read upload") from e
    return await _proxy(
        "POST",
        "/backup/restore",
        timeout=300.0,
        files={"file": (file.filename or "backup.zip", content, "application/zip")},
        error_message="Restore failed",
        log_event="host_helper_backup_restore_failed",
    )
