"""REST API endpoints for system status and health."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import HealthCheckResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

# Service start time
_start_time = time.time()

# MQTT client will be injected at startup
_mqtt_client: MQTTClient | None = None

# Known Minabox services for status panel; URLs for HTTP health check (from backend container on minabox-network)
SERVICE_IDS = ("backend", "mqtt", "audio", "rfid", "button", "led", "webui")
SERVICE_HEALTH_URLS = {
    "audio": "http://audio:8003/health",
    "rfid": "http://rfid:8000/health",
    "button": "http://button:8000/health",
    "led": "http://led:8000/health",
    "webui": "http://webui:80/",
}
HEALTH_TIMEOUT = 2.0

# Container names for docker logs (when running with docker compose)
CONTAINER_NAMES = {
    "audio": "minabox-audio",
    "rfid": "minabox-rfid",
    "button": "minabox-button",
    "led": "minabox-led",
    "webui": "minabox-webui",
}


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    """Set MQTT client for system routes."""
    global _mqtt_client
    _mqtt_client = mqtt_client


async def _check_service_http(sid: str) -> bool:
    """Return True if service responds with 2xx."""
    url = SERVICE_HEALTH_URLS.get(sid)
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            r = await client.get(url)
            return 200 <= r.status_code < 300
    except Exception as e:
        logger.debug("service_health_check_failed", service=sid, error=str(e))
        return False


@router.get("/status")
async def system_status() -> dict:
    """Return system status for Admin UI (device_id, uptime, service list)."""
    config = get_config()
    uptime_seconds = int(time.time() - _start_time)
    mqtt_ok = _mqtt_client.is_connected if _mqtt_client else False
    now = datetime.now(UTC).isoformat()
    services = []

    for sid in SERVICE_IDS:
        if sid == "backend":
            state = "online"
        elif sid == "mqtt":
            state = "online" if mqtt_ok else "offline"
        else:
            state = "online" if await _check_service_http(sid) else "offline"
        services.append({
            "service": sid,
            "state": state,
            "timestamp": now,
        })

    return {
        "device_id": config.device_id,
        "uptime_seconds": uptime_seconds,
        "services": services,
    }


def _sync_docker_logs(container_name: str, tail: int) -> str | None:
    """Get container logs via Docker API (blocking). Returns None if Docker unavailable."""
    try:
        import docker
        client = docker.from_env()
        container = client.containers.get(container_name)
        out = container.logs(tail=min(tail, 500), stdout=True, stderr=True)
        return out.decode("utf-8", errors="replace").strip()
    except Exception as e:
        logger.debug("docker_logs_failed", service=container_name, error=str(e))
        return None


async def _get_logs_via_docker(service: str, tail: int) -> str | None:
    """Try to get logs via Docker API. Returns content or None if unavailable."""
    container = CONTAINER_NAMES.get(service)
    if not container:
        return None
    try:
        return await asyncio.to_thread(_sync_docker_logs, container, tail)
    except Exception as e:
        logger.debug("docker_logs_async_failed", service=service, error=str(e))
        return None


@router.get("/logs")
async def get_service_logs(service: str, tail: int = 200) -> dict:
    """Return recent logs for a service. Uses docker logs if available, else /data/logs/<service>.log."""
    if service not in SERVICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid service")
    # Prefer docker logs when socket is available (e.g. backend started with docker)
    content = await _get_logs_via_docker(service, tail)
    if content is not None:
        return {"service": service, "lines": content, "tail": tail}
    # Fallback: read from file
    data_path = os.environ.get("DATA_PATH", "/data")
    path = Path(data_path) / "logs" / f"{service}.log"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Logs not available. Mount Docker socket into backend (e.g. /var/run/docker.sock) to view container logs.",
        )
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        content = "\n".join(lines[-tail:]) if len(lines) > tail else "\n".join(lines)
        return {"service": service, "lines": content, "tail": tail}
    except Exception as e:
        logger.warning("logs_read_failed", service=service, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read logs") from e


def _restart_containers_sync() -> None:
    """Restart all Minabox containers via Docker API (blocking)."""
    try:
        import docker
        client = docker.from_env()
        for name in CONTAINER_NAMES.values():
            try:
                container = client.containers.get(name)
                container.restart()
            except Exception as e:
                logger.warning("restart_container_failed", container=name, error=str(e))
        # Also restart host-helper if present
        try:
            client.containers.get("minabox-host-helper").restart()
        except Exception:
            pass
    except Exception as e:
        logger.warning("restart_containers_failed", error=str(e))
        raise


@router.post("/restart")
async def restart_services() -> dict:
    """Restart all Minabox services (containers). Requires Docker socket mounted."""
    try:
        await asyncio.to_thread(_restart_containers_sync)
        return {"ok": True}
    except Exception as e:
        logger.error("restart_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Restart failed. Ensure Docker socket is mounted.",
        ) from e


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse:
    """Health check endpoint.

    Returns:
        Health status
    """
    uptime_seconds = int(time.time() - _start_time)

    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        database_connected = False

    # Check MQTT connection
    mqtt_connected = _mqtt_client.is_connected if _mqtt_client else False

    status = "healthy" if (database_connected and mqtt_connected) else "unhealthy"

    return HealthCheckResponse(
        status=status,
        service="backend",
        version="0.1.0",
        uptime_seconds=uptime_seconds,
        mqtt_connected=mqtt_connected,
        database_connected=database_connected,
    )
