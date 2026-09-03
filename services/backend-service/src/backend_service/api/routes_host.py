"""REST API for Host-Helper proxy: audio path, move, system and hardware control.

Almost every route here is a thin proxy in front of the Host-Helper. The
request/response handling is identical for all of them, so it lives in
_proxy() (strict: propagate failures) and _proxy_optional() (soft: fall back to
a neutral payload when the Host-Helper is absent or unhappy).

All calls share one pooled httpx.AsyncClient - creating a client per request
meant a fresh TCP handshake for every button press in the WebUI.
"""

from __future__ import annotations

import copy
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from backend_service.config import get_config
from backend_service.core import capabilities, component_catalog, update_check
from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import SCHEMA_VERSION, get_db
from backend_service.core.system_alerts import get_all_alerts
from backend_service.models.database import TemperatureReading

logger = structlog.get_logger(__name__)
router = APIRouter()

HOST_HELPER_TIMEOUT = 10.0
#: Backups are large and live on an SD card, so they get their own budget.
BACKUP_TIMEOUT = 60.0

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
        raise ApiError(status_code=400, code="path_required", detail="path required")
    if ".." in path:
        raise ApiError(status_code=400, code="path_invalid", detail="Invalid path")
    p = Path(path).resolve()
    if not p.is_absolute():
        raise ApiError(status_code=400, code="path_not_absolute", detail="Path must be absolute")
    allowed = _allowed_audio_paths()
    for base in allowed:
        try:
            p.relative_to(Path(base).resolve())
            return
        except ValueError:
            continue
    raise ApiError(status_code=400, code="path_not_allowed", detail="Path not under allowed base paths")


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
    error_code: str,
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
        raise ApiError(status_code=503, code="host_helper_not_configured", detail=not_configured_detail)
    try:
        r = await _request(
            method, path, api_key, timeout=timeout, json=json, params=params, files=files
        )
    except httpx.RequestError as e:
        logger.warning(log_event, error=str(e))
        raise ApiError(status_code=503, code="host_helper_unreachable", detail=unreachable_detail) from e

    if r.status_code == 401:
        raise ApiError(status_code=503, code="host_helper_auth_failed", detail="Host-Helper authentication failed")
    if r.status_code not in ok_statuses and r.status_code >= 400:
        raise ApiError(
            status_code=min(r.status_code, 502),
            code=error_code,
            detail=_extract_detail(r, error_message),
        )
    if r.status_code not in ok_statuses:
        raise ApiError(status_code=503, code="host_helper_request_failed", detail="Host-Helper request failed")
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

    The fallback is deep-copied: callers get an object they may keep or mutate
    without affecting the next request. A shallow copy would share nested lists
    such as {"devices": []}.
    """
    api_key = _host_helper_api_key()
    if not api_key:
        return copy.deepcopy(fallback)
    try:
        r = await _request(method, path, api_key, timeout=timeout, params=params)
        if r.status_code == 200:
            payload = r.json()
            if payload is not None:
                return payload
    except Exception as e:
        logger.debug(log_event, error=str(e))
    return copy.deepcopy(fallback)


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


@router.get("/alerts")
async def get_system_alerts() -> dict:
    """All active system alerts, most severe first.

    The header picks the update hint out of this and shows it as an icon,
    while the notice bar renders everything else - overheating, say - as a full
    row. Both can be active at once.
    """
    return {"alerts": get_all_alerts()}


# ── Audio path & move ────────────────────────────────────────────────────────


@router.get("/audio-path")
async def get_audio_path() -> dict:
    """Return the configured media path, falling back to the running config.

    get_config() is evaluated lazily on purpose: when the Host-Helper knows the
    saved path, this endpoint must not depend on the service config being
    loadable at all.
    """
    data = await _proxy_optional(
        "/audio-path",
        fallback={},
        log_event="host_helper_get_audio_path_failed",
    )
    saved = data.get("audio_files_path")
    if saved:
        return {"path": saved}
    return {"path": get_config().env.audio_storage_path}


@router.put("/audio-path")
async def put_audio_path(body: AudioPathBody) -> dict:
    path = body.path.strip()
    _validate_path(path)
    return await _proxy(
        "POST",
        "/apply-audio-path",
        json={"audio_files_path": path},
        error_message="Invalid path",
        error_code="audio_path_invalid",
        log_event="host_helper_apply_audio_path_failed",
        unreachable_detail="Host-Helper unreachable. Restart stack after adding host-helper.",
    )


@router.post("/move-audio")
async def move_audio(body: MoveAudioBody) -> JSONResponse:
    _validate_path(body.source)
    _validate_path(body.destination)
    api_key = _host_helper_api_key()
    if not api_key:
        raise ApiError(status_code=503, code="host_helper_not_configured", detail=_NOT_CONFIGURED)
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
        raise ApiError(status_code=503, code="host_helper_unreachable", detail="Host-Helper unreachable.") from e

    if r.status_code == 401:
        raise ApiError(status_code=503, code="host_helper_auth_failed", detail="Host-Helper authentication failed")
    if r.status_code == 409:
        raise ApiError(status_code=409, code="move_in_progress", detail="Move already in progress")
    if r.status_code in (400, 404):
        raise ApiError(
            status_code=r.status_code, code="move_failed", detail=_extract_detail(r, "Move failed")
        )
    if r.status_code not in (200, 202):
        raise ApiError(status_code=503, code="host_helper_request_failed", detail="Host-Helper request failed")
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
        error_code="host_reboot_failed",
        log_event="host_helper_reboot_failed",
    )


async def host_restart_audio_service() -> dict:
    """Restart only the audio container - the escalation the UI offers next.

    Not the whole stack: that takes the WebUI down with it, and the person
    waiting for an answer is looking at exactly that page.
    """
    return await _proxy(
        "POST",
        "/audio/restart",
        timeout=95.0,
        error_message="Restarting the audio service failed",
        error_code="audio_service_restart_failed",
        log_event="host_helper_audio_restart_failed",
    )


async def host_audio_repair() -> dict | None:
    """Steps 1 and 7 of the sound-repair chain, run on the host.

    Not a route: the button lives under /audio/troubleshoot, which stitches
    this half together with the audio service's. Returns None when the
    host-helper is missing or does not answer - a box without it still gets
    steps 2 to 6, which is most of the value.
    """
    result = await _proxy_optional(
        "/audio/repair",
        method="POST",
        # amixer is asked once per control per card, each through nsenter.
        timeout=30.0,
        fallback={},
        log_event="host_helper_audio_repair_failed",
    )
    return result or None


@router.post("/shutdown")
async def shutdown_host() -> dict:
    """Shutdown the host (Pi). Requires Host-Helper."""
    return await _proxy(
        "POST",
        "/shutdown",
        error_message="Shutdown failed",
        error_code="host_shutdown_failed",
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
        error_code="services_restart_failed",
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
        error_code="timezone_set_failed",
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
        error_code="hostname_set_failed",
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
        error_code="board_leds_set_failed",
        log_event="host_helper_board_leds_failed",
    )


@router.get("/network-status")
async def get_network_status() -> dict:
    """Where the box stands on the network right now. Proxied to Host-Helper.

    Public (see middleware/auth.py): the display service polls this without a
    session, and the hotspot password it can carry is only present while the
    fallback hotspot is the box's only network anyway.
    """
    return await _proxy_optional(
        "/network/status",
        fallback={
            "mode": "unknown",
            "internet": False,
            "interface": None,
            "interface_type": None,
            "ipv4": None,
            "ssid": None,
            "hotspot": {"active": False, "ssid": None, "password": None},
            "manage_url": None,
            "fallback_enabled": True,
            "stale": True,
        },
        log_event="host_helper_network_status_failed",
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
        error_code="network_set_failed",
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
        error_code="host_password_set_failed",
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
        error_code="docker_prune_failed",
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
        error_code="ssh_toggle_failed",
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
        error_code="factory_reset_failed",
        log_event="host_helper_factory_reset_failed",
    )


class UpdateTargetsBody(BaseModel):
    """Target version per service. Empty means: everything to the latest."""

    targets: dict[str, str] | None = None
    backup: bool = True


class RollbackBody(BaseModel):
    """The services to step back, by name. Empty is rejected, never read as "all"."""

    services: list[str] = []


@router.post("/update-minabox")
async def update_minabox(body: UpdateTargetsBody | None = None) -> dict:
    """Start the update in the background. Proxied to the Host-Helper.

    Returns immediately; progress comes from /update-minabox/status. The
    update runs as its own unit on the host, so it survives the host-helper
    being recreated underneath it.

    With `targets`, exactly the named services go to exactly the named
    versions - plus whatever those versions need from the other services
    (#194). A release may say it needs a newer backend; taking that backend
    along is the difference between a targeted update and a box left on a
    combination nobody built. Without `targets` everything moves anyway and
    there is nothing to add.
    """
    payload = body.model_dump() if body else {"targets": None, "backup": True}
    targets = payload.get("targets")
    if targets:
        extra = update_check.companions(targets)
        if extra:
            logger.info("update_pulls_along", targets=targets, companions=extra)
            payload["targets"] = {**targets, **extra}
    # The schema version travels with every run and is filed in the history.
    # It is the only thing that later says whether the way back crosses a
    # migration - see /update-history.
    payload["schema_version"] = SCHEMA_VERSION
    payload["kind"] = "update"
    return await _proxy(
        "POST",
        "/system/update-minabox",
        timeout=60.0,
        json=payload,
        error_message="Update failed",
        error_code="update_failed",
        log_event="host_helper_update_minabox_failed",
    )


def _left_behind(
    service: str,
    target: str,
    running: dict[str, str],
    requirements: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """The running service that this step back would drop below its minimum.

    The mirror image of the hold-back in the update check (#194): there a
    candidate waits because the box is too old for it, here a step back is
    refused because it would make the box too old for something that is
    already running. The first one found is named - one reason is enough to
    say why the button does nothing, and a list of them would only be longer.
    """
    for other, wanted in sorted(requirements.items()):
        if other == service or other not in running:
            continue
        minimum = wanted.get(service)
        if minimum and update_check.is_newer(minimum, target):
            return {"service": other, "minimum": minimum}
    return None


def _rollback_candidates(
    entries: list[dict],
    running: dict[str, str],
    requirements: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    """Per service the version it ran before the most recent change of it.

    Walks the history from newest to oldest and stops at the first entry that
    names a *different* version than the one running now. Anything older is
    not "the way back" but a second step, and offering it as one would be a
    promise about data that was written since.

    A step back over a schema change is refused here, not attempted. Once the
    database has been migrated, the older code looks for its data where the
    newer version no longer puts it - and reports it as gone. That is not a
    failure the box could recover from on its own, so it never starts.

    The second refusal is the version dependency read backwards (#194): a step
    back that would drop this service below what another *running* service
    asks of it. Each service is judged on its own, against what runs today -
    so stepping two services back together, where the one asking would be
    stepping back out of its own requirement, is refused as well. The button
    steps back one service at a time, and the careful answer is the right one
    for the case where it does not.
    """
    candidates: list[dict] = []
    for service, current in sorted(running.items()):
        for entry in entries:
            previous = (entry.get("previous") or {}).get(service)
            if not previous or previous == current:
                continue
            recorded = entry.get("schema_version")
            # Only the backend reads the database; the other services are free
            # to move on their own, which is the whole point of a version per
            # service.
            blocked = (
                service == "backend"
                and isinstance(recorded, int)
                and recorded != SCHEMA_VERSION
            )
            # Asked second, and only when the first answer was yes: the
            # database is the harder wall of the two, and naming it is the
            # more useful sentence.
            left_behind = (
                None
                if blocked
                else _left_behind(service, previous, running, requirements or {})
            )
            candidate = {
                "service": service,
                "installed": current,
                "target": previous,
                "recorded_at": entry.get("started_at"),
                "allowed": not blocked and left_behind is None,
                "reason": (
                    "schema_changed"
                    if blocked
                    else "requires_unmet"
                    if left_behind
                    else None
                ),
            }
            if left_behind:
                candidate["required_by"] = left_behind
            candidates.append(candidate)
            break
    return candidates


@router.get("/update-history")
async def update_history() -> dict:
    """What ran before, and what may be gone back to.

    Soft-fails like the other status reads: without the Host-Helper there is
    simply nothing to offer, and the maintenance page should still open.
    """
    payload = await _proxy_optional(
        "/system/update-history",
        fallback={"entries": [], "running": {}},
        log_event="host_helper_update_history_failed",
    )
    entries = [e for e in (payload.get("entries") or []) if isinstance(e, dict)]
    running = {
        k: v for k, v in (payload.get("running") or {}).items() if isinstance(v, str)
    }
    return {
        "entries": entries,
        "schema_version": SCHEMA_VERSION,
        "candidates": _rollback_candidates(
            entries, running, update_check.declared_requirements()
        ),
    }


@router.post("/rollback")
async def rollback(body: RollbackBody) -> dict:
    """Put the named services back on the version they ran before.

    Runs through the same path as an update - backup, pin, pull, restart,
    verify - only with older tags. The check against the history happens here
    and not in the Host-Helper: whether a step back is safe is a question
    about the database schema, and this is the service that knows it.
    """
    wanted = [name for name in dict.fromkeys(body.services) if name]
    if not wanted:
        raise ApiError(
            status_code=400, code="rollback_no_services", detail="No service named"
        )

    history = await update_history()
    by_service = {c["service"]: c for c in history["candidates"]}

    targets: dict[str, str] = {}
    for name in wanted:
        candidate = by_service.get(name)
        if candidate is None:
            raise ApiError(
                status_code=409,
                code="rollback_unavailable",
                detail=f"No earlier version recorded for {name}",
            )
        if candidate["reason"] == "requires_unmet":
            other = candidate.get("required_by") or {}
            raise ApiError(
                status_code=409,
                code="rollback_requires_unmet",
                detail=(
                    f"{name} cannot be stepped back: "
                    f"{other.get('service')} needs at least "
                    f"{name} {other.get('minimum')}."
                ),
            )
        if not candidate["allowed"]:
            raise ApiError(
                status_code=409,
                code="rollback_schema_changed",
                detail=(
                    f"{name} cannot be stepped back: the database was migrated "
                    "in between, and the older version cannot read it."
                ),
            )
        targets[name] = candidate["target"]

    logger.info("rollback_started", targets=targets)
    return await _proxy(
        "POST",
        "/system/update-minabox",
        timeout=60.0,
        json={
            "targets": targets,
            "backup": True,
            "schema_version": SCHEMA_VERSION,
            "kind": "rollback",
        },
        error_message="Rollback failed",
        error_code="rollback_failed",
        log_event="host_helper_rollback_failed",
    )


@router.get("/update-minabox/status")
async def update_minabox_status() -> dict:
    """Progress and output of the running or last update.

    Soft-fails on purpose: during the restart the host-helper is briefly
    unreachable, and the WebUI should be allowed to keep asking rather than
    show an error.
    """
    return await _proxy_optional(
        "/system/update-minabox/status",
        fallback={
            "running": True,
            "step": None,
            "step_count": None,
            "step_key": None,
            "exit_code": None,
            "steps": [],
            "log": "",
            "targets": {},
            "unreachable": True,
        },
        log_event="host_helper_update_minabox_status_failed",
    )


# ── Optional components ──────────────────────────────────────────────────────
#
# Which components a box has is COMPOSE_PROFILES in .env. The Host-Helper is
# the only service that may write it and the only one that can drive compose,
# so all three routes are plain proxies. What the WebUI shows *per* component -
# installed, running, healthy - keeps coming from /system/capabilities.


class ComponentsBody(BaseModel):
    """The components this box should have, as compose profiles."""

    profiles: list[str]


@router.get("/components")
async def get_components() -> dict:
    """The catalogue: every optional component, with or without this box having it.

    The Host-Helper answers which profiles are written in .env; the catalogue
    adds what each component is for, what it needs and which version it is at
    (component_catalog.py) - so a component can be found and added without
    reading the documentation first (#181).

    Soft-fails like the other status reads: without the Host-Helper the
    maintenance page should still open. The list then comes from the
    catalogue instead, and only *changing* it is out of reach - which
    `unreachable` says.
    """
    payload = await _proxy_optional(
        "/system/components",
        fallback={"components": [], "profiles": [], "busy": False, "unreachable": True},
        log_event="host_helper_components_failed",
    )
    return await component_catalog.enrich(
        payload, channel=update_check.read_update_channel()
    )


@router.put("/components")
async def put_components(body: ComponentsBody) -> dict:
    """Set the components of this box. Returns as soon as the run has started.

    Nothing is deleted: a component that is switched off loses its container,
    not its data. Progress comes from /components/status.
    """
    # Only profiles this image's compose file actually has. The catalogue also
    # lists addons that are installed by writing a setting - those have no
    # profile at all - and a caller that sent one of their ids anyway would
    # have COMPOSE_PROFILES written with a profile that starts nothing.
    profiles = [p for p in body.profiles if p in capabilities.PROFILE_TO_FEATURE]
    return await _proxy(
        "PUT",
        "/system/components",
        timeout=60.0,
        json={"profiles": profiles},
        error_message="Changing the components failed",
        error_code="components_failed",
        log_event="host_helper_put_components_failed",
    )


@router.get("/components/status")
async def get_components_status() -> dict:
    """Progress and output of the running or last component change.

    Soft-fails on purpose: the run recreates the backend, so this very service
    is briefly gone. The WebUI should keep asking rather than show an error.
    """
    return await _proxy_optional(
        "/system/components/status",
        fallback={
            "running": True,
            "step": None,
            "step_count": None,
            "step_key": None,
            "exit_code": None,
            "steps": [],
            "log": "",
            "profiles": [],
            "reboot_required": False,
            "blocked": [],
            "unreachable": True,
        },
        log_event="host_helper_components_status_failed",
    )


@router.post("/update-os")
async def update_os() -> dict:
    """Run OS update (apt upgrade) on host. Proxied to Host-Helper. Blocks until done."""
    return await _proxy(
        "POST",
        "/system/update-os",
        timeout=1900.0,
        error_message="OS update failed",
        error_code="os_update_failed",
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
        error_code="wifi_connect_failed",
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
        error_code="hotspot_start_failed",
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
        error_code="hotspot_stop_failed",
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
        error_code="usb_files_failed",
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
        error_code="usb_import_failed",
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
        error_code="usb_eject_failed",
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
        error_code="bluetooth_pair_failed",
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
        error_code="bluetooth_connect_failed",
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
        error_code="bluetooth_disconnect_failed",
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
        error_code="bluetooth_remove_failed",
        log_event="host_helper_bluetooth_remove_failed",
        not_configured_detail=_NOT_CONFIGURED_SHORT,
    )


# ── Backup ───────────────────────────────────────────────────────────────────


@router.get("/backup/download")
async def backup_download() -> Response:
    """Download backup ZIP (DB, configs, state). Proxied to Host-Helper.

    Streamed rather than buffered. Reading `r.content` held the whole archive in
    memory - and then again in the outgoing body - which a backup including
    audio can easily exceed on a Pi. The response is closed by the background
    task once the last chunk has left.
    """
    api_key = _host_helper_api_key()
    if not api_key:
        raise ApiError(status_code=503, code="host_helper_not_configured", detail=_NOT_CONFIGURED)

    client = _get_client()
    request = client.build_request(
        "GET",
        f"{_host_helper_url()}/backup/download",
        headers={"X-Api-Key": api_key},
        timeout=BACKUP_TIMEOUT,
    )
    try:
        upstream = await client.send(request, stream=True)
    except httpx.RequestError as e:
        logger.warning("host_helper_backup_download_failed", error=str(e))
        raise ApiError(status_code=503, code="host_helper_unreachable", detail=_UNREACHABLE) from e

    if upstream.status_code != 200:
        # The body is still unread at this point; read it so _extract_detail has
        # something to work with, then release the connection.
        await upstream.aread()
        await upstream.aclose()
        if upstream.status_code == 401:
            raise ApiError(status_code=503, code="host_helper_auth_failed", detail="Host-Helper authentication failed")
        raise ApiError(
            status_code=min(upstream.status_code, 502),
            code="backup_download_failed",
            detail=_extract_detail(upstream, "Backup download failed"),
        )

    disposition = upstream.headers.get(
        "content-disposition", "attachment; filename=minabox-backup.zip"
    )
    return StreamingResponse(
        upstream.aiter_bytes(),
        media_type=upstream.headers.get("content-type", "application/zip"),
        headers={"Content-Disposition": disposition},
        background=BackgroundTask(upstream.aclose),
    )


@router.post("/backup/restore")
async def backup_restore(file: UploadFile = File(...)) -> dict:
    """Upload a backup ZIP and start the restore. Proxied to Host-Helper.

    Answers as soon as the Host-Helper has accepted the archive (202). It
    cannot wait for the outcome: the restore stops this very service, so the
    reply would never reach the WebUI. Progress comes from /backup/restore-status.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise ApiError(status_code=400, code="upload_must_be_zip", detail="Upload must be a .zip file")
    # Hand the spooled upload straight to httpx instead of reading it into a
    # bytes object first. Starlette has already put anything sizeable on disk,
    # so this keeps a large backup out of the RAM entirely.
    try:
        await file.seek(0)
    except (OSError, ValueError) as e:
        raise ApiError(status_code=400, code="upload_read_failed", detail="Failed to read upload") from e
    return await _proxy(
        "POST",
        "/backup/restore",
        timeout=300.0,
        files={"file": (file.filename or "backup.zip", file.file, "application/zip")},
        error_message="Restore failed",
        error_code="backup_restore_failed",
        log_event="host_helper_backup_restore_failed",
        ok_statuses=(200, 202),
    )


@router.get("/backup/restore-status")
async def backup_restore_status() -> dict:
    """State of the running or last restore. Proxied to Host-Helper."""
    return await _proxy_optional(
        "/backup/restore-status",
        fallback={"status": "idle", "error": None, "finished_at": None},
        log_event="host_helper_backup_restore_status_failed",
    )
