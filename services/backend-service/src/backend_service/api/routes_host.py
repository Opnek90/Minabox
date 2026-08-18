"""REST API for Host-Helper proxy: audio path, move."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.models.database import TemperatureReading
from backend_service.core.temperature_logger import get_current_alert

logger = structlog.get_logger(__name__)
router = APIRouter()

HOST_HELPER_TIMEOUT = 10.0


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


@router.get("/host-status")
async def get_host_status() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"hostname": None, "ip": None, "uptime_seconds": None, "memory": None, "cpu": None, "disk": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/host-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_host_status_failed", error=str(e))
    return {"hostname": None, "ip": None, "uptime_seconds": None, "memory": None, "cpu": None, "disk": None, "temperature_celsius": None}


@router.get("/temperature-history")
async def get_temperature_history(
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> dict:
    """Return temperature readings for the last N hours (default 24)."""
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
    if alert is None:
        return {"alert": None}
    return {"alert": alert}


@router.get("/audio-path")
async def get_audio_path() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        config = get_config()
        return {"path": config.env.audio_storage_path}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/audio-path",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                data = r.json()
                saved = data.get("audio_files_path")
                if saved:
                    return {"path": saved}
        config = get_config()
        return {"path": config.env.audio_storage_path}
    except Exception as e:
        logger.debug("host_helper_get_audio_path_failed", error=str(e))
        config = get_config()
        return {"path": config.env.audio_storage_path}


@router.put("/audio-path")
async def put_audio_path(body: AudioPathBody) -> dict:
    path = body.path.strip()
    _validate_path(path)
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.post(
                f"{url}/apply-audio-path",
                json={"audio_files_path": path},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code == 400:
                raise HTTPException(status_code=400, detail=r.json().get("detail", "Invalid path"))
            if r.status_code != 200:
                raise HTTPException(status_code=503, detail="Host-Helper request failed")
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_apply_audio_path_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Host-Helper unreachable. Restart stack after adding host-helper.",
        ) from e


@router.post("/move-audio")
async def move_audio(body: MoveAudioBody):
    _validate_path(body.source)
    _validate_path(body.destination)
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.post(
                f"{url}/move",
                json={"source": body.source, "destination": body.destination},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code == 409:
                raise HTTPException(status_code=409, detail="Move already in progress")
            if r.status_code in (400, 404):
                detail = r.json().get("detail", "Move failed") if r.content else "Move failed"
                raise HTTPException(status_code=r.status_code, detail=detail)
            if r.status_code not in (200, 202):
                raise HTTPException(status_code=503, detail="Host-Helper request failed")
            return JSONResponse(content=r.json(), status_code=r.status_code)
    except httpx.RequestError as e:
        logger.warning("host_helper_move_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable.") from e


@router.get("/move-status")
async def get_move_status() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"status": "idle", "total": 0, "current": 0, "error": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/move-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_move_status_failed", error=str(e))
    return {"status": "idle", "total": 0, "current": 0, "error": None}


@router.post("/reboot")
async def reboot_host() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{url}/reboot",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                try:
                    detail = (r.json() or {}).get("detail", "Reboot failed") if r.content else "Reboot failed"
                except Exception:
                    detail = (r.text or "Reboot failed")[:500]
                raise HTTPException(status_code=min(r.status_code, 502), detail=detail)
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_reboot_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Host-Helper unreachable: {e!s}",
        ) from e


@router.post("/shutdown")
async def shutdown_host() -> dict:
    """Shutdown the host (Pi). Requires Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{url}/shutdown",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                try:
                    detail = (r.json() or {}).get("detail", "Shutdown failed") if r.content else "Shutdown failed"
                except Exception:
                    detail = (r.text or "Shutdown failed")[:500]
                raise HTTPException(status_code=min(r.status_code, 502), detail=detail)
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_shutdown_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Host-Helper unreachable: {e!s}",
        ) from e


@router.post("/restart")
async def restart_services() -> dict:
    """Restart Minabox containers. Proxied to Host-Helper (runs on host)."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=125.0) as client:
            r = await client.post(
                f"{url}/restart",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                try:
                    detail = (r.json() or {}).get("detail", "Restart failed") if r.content else "Restart failed"
                except Exception:
                    detail = (r.text or "Restart failed")[:500]
                raise HTTPException(status_code=min(r.status_code, 502), detail=detail)
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_restart_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Host-Helper unreachable: {e!s}",
        ) from e


@router.get("/syslog")
async def get_syslog(n: int = 200, source: str = "kernel") -> dict:
    """Return host kernel or docker unit logs. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"lines": [], "source": source}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{url}/syslog",
                params={"n": n, "source": source},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_syslog_failed", error=str(e))
    return {"lines": [], "source": source}


@router.put("/timezone")
async def put_timezone(body: TimezoneBody) -> dict:
    """Set host timezone (e.g. Europe/Berlin). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.put(
                f"{url}/system/timezone",
                json={"timezone": body.timezone},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed to set timezone") if r.content else "Failed to set timezone"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_timezone_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/hostname")
async def get_hostname() -> dict:
    """Return current host hostname. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"hostname": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/system/hostname",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_hostname_failed", error=str(e))
    return {"hostname": None}


@router.put("/hostname")
async def put_hostname(body: HostnameBody) -> dict:
    """Set host hostname. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.put(
                f"{url}/system/hostname",
                json={"hostname": body.hostname},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed to set hostname") if r.content else "Failed to set hostname"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_hostname_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/board-leds")
async def get_board_leds() -> dict:
    """Return board LED state (stealth). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"stealth": False, "power_led": "on", "activity_led": "on"}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/system/board-leds",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_board_leds_failed", error=str(e))
    return {"stealth": False, "power_led": "on", "activity_led": "on"}


@router.put("/board-leds")
async def put_board_leds(body: BoardLedsBody) -> dict:
    """Set board LEDs (stealth on/off). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.put(
                f"{url}/system/board-leds",
                json={"stealth": body.stealth},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed to set board LEDs") if r.content else "Failed to set board LEDs"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_board_leds_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/network")
async def get_network() -> dict:
    """Return current IP config (DHCP/manual). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"method": "dhcp", "address": None, "netmask": None, "gateway": None, "dns": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/system/network",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_network_failed", error=str(e))
    return {"method": "dhcp", "address": None, "netmask": None, "gateway": None, "dns": None}


@router.put("/network")
async def put_network(body: NetworkBody) -> dict:
    """Set IP config (DHCP or manual). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.put(
                f"{url}/system/network",
                json={
                    "method": body.method,
                    "address": body.address,
                    "netmask": body.netmask,
                    "gateway": body.gateway,
                    "dns": body.dns,
                },
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed to set network") if r.content else "Failed to set network"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_network_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/password")
async def set_password(body: PasswordBody) -> dict:
    """Change system user password. Proxied to Host-Helper. Password is never logged."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{url}/system/password",
                json={"username": body.username, "new_password": body.new_password},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed to set password") if r.content else "Failed to set password"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_password_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/docker-prune")
async def docker_prune() -> dict:
    """Run docker system prune. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=310.0) as client:
            r = await client.post(
                f"{url}/system/docker-prune",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Docker prune failed") if r.content else "Docker prune failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_docker_prune_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/ssh-status")
async def get_ssh_status() -> dict:
    """Return SSH enabled/active on host. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"enabled": False, "active": False}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/system/ssh-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_ssh_status_failed", error=str(e))
    return {"enabled": False, "active": False}


@router.post("/ssh-toggle")
async def ssh_toggle(body: SshToggleBody) -> dict:
    """Enable or disable SSH on host. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{url}/system/ssh-toggle",
                json={"enable": body.enable},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "SSH toggle failed") if r.content else "SSH toggle failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_ssh_toggle_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/factory-reset")
async def factory_reset(body: FactoryResetBody | None = None) -> dict:
    """Factory reset: clear DB/config, optional audio, start hotspot, restart. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    payload = {"delete_audio": getattr(body, "delete_audio", False) if body else False}
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{url}/system/factory-reset",
                json=payload,
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Factory reset failed") if r.content else "Factory reset failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_factory_reset_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/update-minabox")
async def update_minabox() -> dict:
    """Pull images and restart containers. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=620.0) as client:
            r = await client.post(
                f"{url}/system/update-minabox",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Update failed") if r.content else "Update failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_update_minabox_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/wifi/scan")
async def wifi_scan() -> dict:
    """List available WiFi networks. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"networks": []}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{url}/wifi/scan", headers={"X-Api-Key": api_key})
            payload = r.json() if r.status_code == 200 else None
            if r.status_code == 200 and payload is not None:
                return payload
    except Exception as e:
        logger.debug("host_helper_wifi_scan_failed", error=str(e))
    return {"networks": []}


class WifiConnectBody(BaseModel):
    ssid: str
    password: str = ""


@router.post("/wifi/connect")
async def wifi_connect(body: WifiConnectBody) -> dict:
    """Connect to WiFi. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=50.0) as client:
            r = await client.post(
                f"{url}/wifi/connect",
                json={"ssid": body.ssid, "password": body.password},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Connect failed") if r.content else "Connect failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_wifi_connect_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


class HotspotStartBody(BaseModel):
    ssid: str = "Minabox-Setup"
    password: str = ""


@router.post("/wifi/hotspot/start")
async def wifi_hotspot_start(body: HotspotStartBody | None = Body(None)) -> dict:
    """Start WiFi hotspot. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                f"{url}/wifi/hotspot/start",
                json=(body.model_dump() if body else {}),
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Hotspot start failed") if r.content else "Hotspot start failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_wifi_hotspot_start_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/wifi/hotspot/stop")
async def wifi_hotspot_stop() -> dict:
    """Stop WiFi hotspot. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{url}/wifi/hotspot/stop", headers={"X-Api-Key": api_key})
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Hotspot stop failed") if r.content else "Hotspot stop failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_wifi_hotspot_stop_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/usb/devices")
async def usb_devices() -> dict:
    """List USB block devices. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"devices": []}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{url}/usb/devices", headers={"X-Api-Key": api_key})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_usb_devices_failed", error=str(e))
    return {"devices": []}


@router.get("/usb/{device_id}/files")
async def usb_files(device_id: str) -> dict:
    """List files on USB device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(
                f"{url}/usb/{device_id}/files",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Failed") if r.content else "Failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_usb_files_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


class UsbImportBody(BaseModel):
    device_id: str
    source_paths: list[str]


class UsbEjectBody(BaseModel):
    device_id: str


@router.post("/usb/import")
async def usb_import(body: UsbImportBody) -> dict:
    """Import from USB to audio storage. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{url}/usb/import",
                json={"device_id": body.device_id, "source_paths": body.source_paths},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Import failed") if r.content else "Import failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_usb_import_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/usb/eject")
async def usb_eject(body: UsbEjectBody) -> dict:
    """Eject USB device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{url}/usb/eject",
                json={"device_id": body.device_id},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Eject failed") if r.content else "Eject failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_usb_eject_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/bluetooth/scan")
async def bluetooth_scan() -> dict:
    """Scan for Bluetooth devices. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"devices": []}
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(f"{url}/bluetooth/scan", headers={"X-Api-Key": api_key})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_bluetooth_scan_failed", error=str(e))
    return {"devices": []}


class BluetoothPairBody(BaseModel):
    address: str


@router.post("/bluetooth/pair")
async def bluetooth_pair(body: BluetoothPairBody) -> dict:
    """Pair with Bluetooth device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            r = await client.post(
                f"{url}/bluetooth/pair",
                json={"address": body.address},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Pairing failed") if r.content else "Pairing failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_bluetooth_pair_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/bluetooth/paired")
async def bluetooth_paired() -> dict:
    """Return paired Bluetooth devices. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"devices": []}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{url}/bluetooth/paired", headers={"X-Api-Key": api_key})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_bluetooth_paired_failed", error=str(e))
    return {"devices": []}


@router.post("/bluetooth/connect")
async def bluetooth_connect(body: BluetoothPairBody) -> dict:
    """Connect to paired Bluetooth device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{url}/bluetooth/connect",
                json={"address": body.address},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Connect failed") if r.content else "Connect failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_bluetooth_connect_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/bluetooth/disconnect")
async def bluetooth_disconnect(body: BluetoothPairBody) -> dict:
    """Disconnect Bluetooth device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{url}/bluetooth/disconnect",
                json={"address": body.address},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Disconnect failed") if r.content else "Disconnect failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_bluetooth_disconnect_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/bluetooth/remove")
async def bluetooth_remove(body: BluetoothPairBody) -> dict:
    """Remove (unpair) Bluetooth device. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{url}/bluetooth/remove",
                json={"address": body.address},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Remove failed") if r.content else "Remove failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_bluetooth_remove_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/wifi/hotspot/status")
async def wifi_hotspot_status() -> dict:
    """Hotspot active? Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"active": False, "ssid": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{url}/wifi/hotspot/status", headers={"X-Api-Key": api_key})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_wifi_hotspot_status_failed", error=str(e))
    return {"active": False, "ssid": None}


@router.post("/update-os")
async def update_os() -> dict:
    """Run OS update (apt upgrade) on host. Proxied to Host-Helper. Blocks until done."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Host-Helper not configured")
    try:
        async with httpx.AsyncClient(timeout=1900.0) as client:
            r = await client.post(
                f"{url}/system/update-os",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "OS update failed") if r.content else "OS update failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_update_os_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.get("/update-os/log")
async def update_os_log() -> dict:
    """OS update log and running status. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"running": False, "log": ""}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{url}/system/update-os/log",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {"running": False, "log": ""}


@router.get("/version")
async def get_version() -> dict:
    """Current version and update availability. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"current_version": "unknown", "current_commit": None, "update_available": False}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{url}/system/version",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_version_failed", error=str(e))
    return {"current_version": "unknown", "current_commit": None, "update_available": False}


@router.get("/time-status")
async def get_time_status() -> dict:
    """Return host timezone, NTP sync, local time. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"timezone": None, "ntp_sync": False, "local_time": None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{url}/system/time-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_time_status_failed", error=str(e))
    return {"timezone": None, "ntp_sync": False, "local_time": None}


@router.get("/backup/download")
async def backup_download() -> Response:
    """Download backup ZIP (DB, configs, state). Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{url}/backup/download",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code != 200:
                raise HTTPException(status_code=min(r.status_code, 502), detail="Backup download failed")
            disposition = r.headers.get("content-disposition", "attachment; filename=minabox-backup.zip")
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "application/zip"),
                headers={"Content-Disposition": disposition},
            )
    except httpx.RequestError as e:
        logger.warning("host_helper_backup_download_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e


@router.post("/backup/restore")
async def backup_restore(file: UploadFile = File(...)) -> dict:
    """Upload backup ZIP and restore. Proxied to Host-Helper."""
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip file")
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to read upload") from e
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{url}/backup/restore",
                files={"file": (file.filename or "backup.zip", content, "application/zip")},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                detail = (r.json() or {}).get("detail", "Restore failed") if r.content else "Restore failed"
                if isinstance(detail, list):
                    detail = detail[0] if detail else "Restore failed"
                raise HTTPException(status_code=min(r.status_code, 502), detail=str(detail))
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_backup_restore_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable") from e
