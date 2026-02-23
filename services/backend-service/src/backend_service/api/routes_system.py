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
from backend_service.api.routes_host import _host_helper_api_key, _host_helper_url

logger = structlog.get_logger(__name__)
router = APIRouter()

_start_time = time.time()
_mqtt_client: MQTTClient | None = None

SERVICE_IDS = ("backend", "mqtt", "audio", "rfid", "button", "led", "display", "webui")
SERVICE_HEALTH_URLS = {
    "audio":   "http://audio:8003/health",
    "rfid":    "http://rfid:8000/health",
    "button":  "http://button:8000/health",
    "led":     "http://led:8000/health",
    "display": "http://display:8000/health",
    "webui":   "http://webui:80/",
}
CONTAINER_NAMES = {
    "audio":   "minabox-audio",
    "rfid":    "minabox-rfid",
    "button":  "minabox-button",
    "led":     "minabox-led",
    "display": "minabox-display",
    "webui":   "minabox-webui",
    "backend": "minabox-backend",
    "mqtt":    "minabox-mqtt",
}
HEALTH_TIMEOUT = 2.0


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    global _mqtt_client
    _mqtt_client = mqtt_client


async def _check_service_http(sid: str) -> bool:
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


def _get_container_stats_sync(container_name: str) -> dict | None:
    """
    Fetch CPU + RAM stats for a container via Docker API (blocking).
    Returns dict with cpu_percent, memory_mb, memory_percent or None if unavailable.
    """
    try:
        import docker
        client = docker.from_env()
        container = client.containers.get(container_name)
        raw = container.stats(stream=False)

        # ── CPU % ──────────────────────────────────────────────────────────
        cpu_delta = (
            raw["cpu_stats"]["cpu_usage"]["total_usage"]
            - raw["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            raw["cpu_stats"].get("system_cpu_usage", 0)
            - raw["precpu_stats"].get("system_cpu_usage", 0)
        )
        num_cpus = raw["cpu_stats"].get("online_cpus") or len(
            raw["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
        )
        cpu_percent = (
            round((cpu_delta / system_delta) * num_cpus * 100.0, 1)
            if system_delta > 0
            else 0.0
        )

        # ── RAM ────────────────────────────────────────────────────────────
        mem_usage = raw["memory_stats"].get("usage", 0)
        # Subtract cache so we get RSS-like value (same as `docker stats`)
        mem_cache = (
            raw["memory_stats"].get("stats", {}).get("cache", 0)
            or raw["memory_stats"].get("stats", {}).get("inactive_file", 0)
        )
        mem_rss = max(mem_usage - mem_cache, 0)
        mem_limit = raw["memory_stats"].get("limit", 0)
        memory_mb = round(mem_rss / 1024 / 1024, 1)
        memory_percent = (
            round((mem_rss / mem_limit) * 100.0, 1) if mem_limit > 0 else 0.0
        )

        return {
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "memory_percent": memory_percent,
        }
    except Exception as e:
        logger.debug("container_stats_failed", container=container_name, error=str(e))
        return None


async def _get_container_stats(sid: str) -> dict | None:
    container = CONTAINER_NAMES.get(sid)
    if not container:
        return None
    try:
        return await asyncio.to_thread(_get_container_stats_sync, container)
    except Exception:
        return None


@router.get("/status")
async def system_status() -> dict:
    """Return system status for Admin UI (device_id, uptime, service list with metrics)."""
    config = get_config()
    uptime_seconds = int(time.time() - _start_time)
    mqtt_ok = _mqtt_client.is_connected if _mqtt_client else False
    now = datetime.now(UTC).isoformat()

    # Run health checks + stats concurrently
    health_checks = {
        sid: _check_service_http(sid)
        for sid in SERVICE_IDS
        if sid not in ("backend", "mqtt")
    }
    stats_checks = {
        sid: _get_container_stats(sid)
        for sid in SERVICE_IDS
        if sid not in ("mqtt",)
    }

    health_results = dict(
        zip(health_checks.keys(), await asyncio.gather(*health_checks.values()))
    )
    stats_results = dict(
        zip(stats_checks.keys(), await asyncio.gather(*stats_checks.values()))
    )

    services = []
    for sid in SERVICE_IDS:
        if sid == "backend":
            state = "online"
        elif sid == "mqtt":
            state = "online" if mqtt_ok else "offline"
        else:
            state = "online" if health_results.get(sid) else "offline"

        entry: dict = {
            "service": sid,
            "state": state,
            "timestamp": now,
        }

        stats = stats_results.get(sid)
        if stats:
            entry["cpu_percent"] = stats["cpu_percent"]
            entry["memory_mb"] = stats["memory_mb"]
            entry["memory_percent"] = stats["memory_percent"]

        services.append(entry)

    return {
        "device_id": config.device_id,
        "uptime_seconds": uptime_seconds,
        "services": services,
    }


def _debug_log(msg: str, data: dict) -> None:
    # #region agent log
    try:
        import json
        path = "/cursor-debug/debug-771350.log"
        with open(path, "a") as f:
            f.write(json.dumps({"sessionId": "771350", "location": "routes_system.py", "message": msg, "data": data, "timestamp": __import__("time").time() * 1000}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


async def _get_logs_via_host_helper(service: str, tail: int) -> str | None:
    """Fetch container logs via Host-Helper (has Docker socket). Returns None if not configured or failed."""
    api_key = _host_helper_api_key()
    container = CONTAINER_NAMES.get(service)
    if not api_key:
        _debug_log("host_helper_logs_skip", {"reason": "no_api_key", "service": service, "hypothesisId": "H1,H3"})
        return None
    if not container:
        _debug_log("host_helper_logs_skip", {"reason": "no_container", "service": service, "hypothesisId": "H1"})
        return None
    url_base = _host_helper_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{url_base}/container-logs",
                params={"container_name": container, "tail": min(tail, 500)},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                data = r.json()
                out = data.get("lines") or ""
                _debug_log("host_helper_logs_ok", {"service": service, "status_code": 200, "hypothesisId": "H1,H3"})
                return out
            _debug_log("host_helper_logs_fail", {"service": service, "status_code": r.status_code, "url_base": url_base, "hypothesisId": "H1,H3"})
    except Exception as e:
        _debug_log("host_helper_logs_exception", {"service": service, "error": str(e), "url_base": url_base, "hypothesisId": "H1,H3"})
        logger.debug("host_helper_logs_failed", service=service, error=str(e))
    return None


def _sync_docker_logs(container_name: str, tail: int) -> str | None:
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
    if service not in SERVICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid service")
    _debug_log("get_service_logs_start", {"service": service, "tail": tail, "hypothesisId": "H1,H2"})
    content = await _get_logs_via_host_helper(service, tail)
    if content is None:
        content = await _get_logs_via_docker(service, tail)
        _debug_log("get_service_logs_docker_fallback", {"service": service, "got_content": content is not None, "hypothesisId": "H1,H2"})
    if content is not None:
        _debug_log("get_service_logs_ok", {"service": service, "source": "host_helper_or_docker", "hypothesisId": "H1,H2"})
        return {"service": service, "lines": content, "tail": tail}
    data_path = os.environ.get("DATA_PATH", "/data")
    path = Path(data_path) / "logs" / f"{service}.log"
    path_exists = path.exists()
    _debug_log("get_service_logs_file_fallback", {"service": service, "path": str(path), "path_exists": path_exists, "hypothesisId": "H1,H2"})
    if not path_exists:
        _debug_log("get_service_logs_404", {"service": service, "hypothesisId": "H2"})
        raise HTTPException(
            status_code=404,
            detail="Logs not available. Configure Host-Helper (HOST_HELPER_API_KEY) or mount Docker socket into backend.",
        )
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        content = "\n".join(lines[-tail:]) if len(lines) > tail else "\n".join(lines)
        return {"service": service, "lines": content, "tail": tail}
    except Exception as e:
        logger.warning("logs_read_failed", service=service, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read logs") from e


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse:
    uptime_seconds = int(time.time() - _start_time)
    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        database_connected = False
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
