"""REST API endpoints for system status and health."""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, Depends
from shared_lib.version import get_version
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend_service.api.routes_host import _host_helper_api_key, _host_helper_url
from backend_service.api.websocket import ws_manager
from backend_service.config import get_config
from backend_service.core import capabilities as capabilities_service
from backend_service.core import container_registry
from backend_service.core import update_check as update_check_service
from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import HealthCheckResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

_start_time = time.time()
_mqtt_client: MQTTClient | None = None

# Which containers a box really has depends on COMPOSE_PROFILES, so the list is
# asked of Docker at runtime (container_registry). This catalogue stays for two
# reasons:
#   1. as a fallback when the Docker socket is unusable,
#   2. as the display order - the basics first, then the hardware, and last the
#      services a user rarely looks at.
# A service missing from here is still shown; it just ends up at the bottom.
SERVICE_IDS = (
    "backend",
    "mqtt",
    "webui",
    "audio",
    "rfid",
    "button",
    "led",
    "display",
    "media-downloader",
    "host-helper",
)
SERVICE_HEALTH_URLS = {
    "audio":            "http://audio:8003/health",
    "rfid":             "http://rfid:8000/health",
    "button":           "http://button:8000/health",
    "led":              "http://led:8000/health",
    "display":          "http://display:8000/health",
    "webui":            "http://webui:80/",
    "media-downloader": "http://media-downloader:8007/health",
    "host-helper":      "http://host-helper:8000/health",
}
CONTAINER_NAMES = {
    "audio":            "minabox-audio",
    "rfid":             "minabox-rfid",
    "button":           "minabox-button",
    "led":              "minabox-led",
    "display":          "minabox-display",
    "webui":            "minabox-webui",
    "backend":          "minabox-backend",
    "mqtt":             "minabox-mqtt",
    "media-downloader": "minabox-media-downloader",
    "host-helper":      "minabox-host-helper",
}
HEALTH_TIMEOUT = 2.0


def set_mqtt_client(mqtt_client: MQTTClient) -> None:
    global _mqtt_client
    _mqtt_client = mqtt_client


async def _check_service_http(
    sid: str, client: httpx.AsyncClient | None = None
) -> dict | None:
    """Probe a service's /health endpoint.

    Returns the parsed body on success (so the caller also gets the version and
    the status the service reports about itself), an empty dict when it
    answered but sent no usable JSON, and None when it did not answer at all.

    *client* lets a caller reuse one connection pool across a whole round of
    probes instead of setting up eight.
    """
    url = SERVICE_HEALTH_URLS.get(sid)
    if not url:
        return None
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as own:
                r = await own.get(url)
        else:
            r = await client.get(url)
        if not 200 <= r.status_code < 300:
            return None
        try:
            body = r.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}
    except Exception as e:
        logger.debug("service_health_check_failed", service=sid, error=str(e))
        return None


# What a service is allowed to call itself in its own /health body. Anything
# else is ignored rather than passed through, so a typo in one service cannot
# invent a state the UI has no rendering for.
_REPORTED_HEALTH_STATES = ("healthy", "degraded")


async def _apply_reported_health(entries: list[dict]) -> None:
    """Fold each service's self-reported /health status into its entry.

    Five services (audio, rfid, button, display, led) answer /health with a
    "status" of their own, and until this ran nothing looked at it. The
    container health check only asks whether the endpoint answers with 2xx -
    and a degraded service answers 2xx on purpose, so that a lost broker does
    not make Docker restart something that is otherwise fine. The result was a
    service that reported itself as broken and was shown green: the LED service
    with not a single usable GPIO pin, or any service whose MQTT connection had
    gone while the container kept running.

    Only entries that are online are probed. A container that is already known
    to be down has nothing to add and would only spend HEALTH_TIMEOUT saying
    so. The probes run together, so the whole round costs one timeout, not one
    per service.
    """
    probeable = [
        e for e in entries
        if e.get("state") == "online" and e.get("service") in SERVICE_HEALTH_URLS
    ]
    if not probeable:
        return

    async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
        bodies = await asyncio.gather(
            *(_check_service_http(e["service"], client) for e in probeable)
        )

    for entry, body in zip(probeable, bodies, strict=True):
        if not body:
            continue
        reported = body.get("status")
        if reported not in _REPORTED_HEALTH_STATES:
            continue
        entry["service_status"] = reported
        if reported == "degraded":
            # Deliberately below "error": an unhealthy container is the worse
            # news, and a service that still answers is not to overwrite it.
            entry["state"] = "degraded"


def _schema_state() -> dict:
    """The schema check result from the database manager."""
    try:
        from backend_service.core import db_manager

        manager = db_manager.db_manager
        return dict(manager.schema_state) if manager else {}
    except Exception as e:
        logger.debug("schema_state_unavailable", error=str(e))
        return {}


def _order_key(entry: dict) -> tuple[int, str]:
    """Sort key: catalogue order first, unknown services alphabetically last."""
    sid = entry.get("service", "")
    try:
        return (SERVICE_IDS.index(sid), "")
    except ValueError:
        return (len(SERVICE_IDS), sid)


async def _status_from_docker(mqtt_ok: bool, now: str) -> list[dict] | None:
    """Service list built from the containers that actually exist.

    This is the normal path. It covers every container of the Compose project -
    including mqtt and webui, which have no Minabox health endpoint - and it
    leaves out what a profile never started, so a box without the LED profile
    shows no LED entry instead of a permanent "offline".
    """
    entries = await container_registry.discover()
    if entries is None:
        return None

    stats = await container_registry.collect_stats(
        [e["container"] for e in entries if e.get("container")]
    )

    for entry in entries:
        entry["timestamp"] = now
        entry.update(stats.get(entry.get("container", ""), {}))
        if entry.get("service") == "mqtt":
            # Extra fact, not a verdict: the container healthcheck already says
            # whether the broker answers. This says whether *we* are attached
            # to it, which differs during a reconnect and is worth seeing.
            entry["mqtt_connected"] = mqtt_ok

    # The container health check only proves the endpoint answers. What the
    # service says about itself in the body is a separate question, and it is
    # the one that catches a running container that cannot do its job.
    await _apply_reported_health(entries)

    entries.sort(key=_order_key)
    return entries


async def _status_from_probes(mqtt_ok: bool, now: str) -> list[dict]:
    """Fallback for a backend without a usable Docker socket.

    Without Docker there is no way to know which containers exist, so this
    walks the static catalogue and asks each service directly. No CPU or RAM
    here - those come from Docker and from nowhere else.
    """
    probed = [sid for sid in SERVICE_IDS if sid not in ("backend", "mqtt")]
    results = dict(
        zip(
            probed,
            await asyncio.gather(*(_check_service_http(sid) for sid in probed)),
            strict=True,
        )
    )

    services = []
    for sid in SERVICE_IDS:
        entry: dict = {
            "service": sid,
            "container": CONTAINER_NAMES.get(sid),
            "timestamp": now,
        }
        if sid == "backend":
            entry["state"] = "online"
            entry["version"] = get_version()
        elif sid == "mqtt":
            entry["state"] = "online" if mqtt_ok else "offline"
            entry["mqtt_connected"] = mqtt_ok
        else:
            health = results.get(sid)
            entry["state"] = "online" if health is not None else "offline"
            if health and isinstance(health.get("version"), str):
                entry["version"] = health["version"]
            if health and health.get("status") in _REPORTED_HEALTH_STATES:
                entry["service_status"] = health["status"]
                if health["status"] == "degraded":
                    entry["state"] = "degraded"
        services.append(entry)
    return services


@router.get("/status")
async def system_status() -> dict:
    """System status for the admin UI: device id, uptime, and one entry per
    container with state, version and resource usage."""
    config = get_config()
    uptime_seconds = int(time.time() - _start_time)
    mqtt_ok = _mqtt_client.is_connected if _mqtt_client else False
    now = datetime.now(UTC).isoformat()

    services = await _status_from_docker(mqtt_ok, now)
    docker_available = services is not None
    if services is None:
        services = await _status_from_probes(mqtt_ok, now)

    return {
        "device_id": config.device_id,
        "uptime_seconds": uptime_seconds,
        # Tells the UI why CPU/RAM are missing: not "zero load" but "not
        # measurable here".
        "docker_available": docker_available,
        # Raspberry Pi OS ships with the memory cgroup controller disabled, and
        # then no per-container RAM figure exists at all - not for us and not
        # for `docker stats`. The flag lets the UI say that instead of drawing
        # ten bars at zero.
        "memory_stats_available": any(
            s.get("memory_mb") is not None for s in services
        ),
        # Where the database stands against what this code expects.
        "database": _schema_state(),
        "services": services,
    }


@router.get("/capabilities")
async def system_capabilities() -> dict:
    """Per optional component: installed (from COMPOSE_PROFILES) plus the live
    running/healthy state. The WebUI renders navigation, settings and feature
    actions only for what is installed here."""
    return await capabilities_service.feature_states()


# A service name has to be a possible Docker name - anything else never even
# reaches the socket.
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


async def _container_for(service: str) -> str | None:
    """Container name for a service id.

    Prefers what Docker reports, so a container the profiles never started is
    correctly reported as unknown instead of producing a confusing "not found"
    from deeper down. Falls back to the static catalogue when Docker is not
    reachable at all.
    """
    if not _SERVICE_NAME_RE.match(service):
        return None
    names = await container_registry.service_container_names()
    if names is not None:
        return names.get(service)
    return CONTAINER_NAMES.get(service)


async def _get_logs_via_host_helper(service: str, tail: int) -> str | None:
    """Fetch container logs via Host-Helper (has Docker socket). Returns None if not configured or failed."""
    api_key = _host_helper_api_key()
    container = await _container_for(service)
    if not api_key:
        return None
    if not container:
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
                return data.get("lines") or ""
    except Exception as e:
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
    container = await _container_for(service)
    if not container:
        return None
    try:
        return await asyncio.to_thread(_sync_docker_logs, container, tail)
    except Exception as e:
        logger.debug("docker_logs_async_failed", service=service, error=str(e))
        return None


@router.get("/logs")
async def get_service_logs(service: str, tail: int = 200) -> dict:
    # No longer checked against the fixed list: the profiles decide which
    # services exist. An unknown name means "not on this box" (404); one that
    # cannot be a name at all is a caller error (400).
    if not _SERVICE_NAME_RE.match(service):
        raise ApiError(status_code=400, code="service_invalid", detail="Invalid service")
    if await _container_for(service) is None and service not in SERVICE_IDS:
        raise ApiError(status_code=404, code="service_unknown", detail="Unknown service")
    content = await _get_logs_via_host_helper(service, tail)
    if content is None:
        content = await _get_logs_via_docker(service, tail)
    if content is not None:
        return {"service": service, "lines": content, "tail": tail}
    data_path = os.environ.get("DATA_PATH", "/data")
    path = Path(data_path) / "logs" / f"{service}.log"
    if not path.exists():
        raise ApiError(
            status_code=404,
            code="logs_unavailable",
            detail="Logs not available. Configure Host-Helper (HOST_HELPER_API_KEY) or mount Docker socket into backend.",
        )
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        content = "\n".join(lines[-tail:]) if len(lines) > tail else "\n".join(lines)
        return {"service": service, "lines": content, "tail": tail}
    except Exception as e:
        logger.warning("logs_read_failed", service=service, error=str(e))
        raise ApiError(status_code=500, code="logs_read_failed", detail="Failed to read logs") from e


@router.get("/update-check")
async def update_check(force: bool = False) -> dict:
    """Compare the running versions against the published ones.

    `force=true` bypasses the cache - that is the button in the WebUI; without
    the parameter the cached state answers.
    """
    entries = await container_registry.discover()
    if entries is None:
        raise ApiError(
            status_code=503,
            code="versions_unknown_no_docker",
            detail="Running versions are unknown without Docker access.",
        )
    installed = {
        e["service"]: e["version"]
        for e in entries
        if e.get("service") and e.get("version")
    }
    result = await update_check_service.check(installed, force=force)
    await update_check_service.apply_alert(result, ws_manager.broadcast)
    return result


@router.get("/health", response_model=HealthCheckResponse)
def health_check(db: Session = Depends(get_db)) -> HealthCheckResponse:
    uptime_seconds = int(time.time() - _start_time)
    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        database_connected = False
    mqtt_connected = _mqtt_client.is_connected if _mqtt_client else False
    # A database newer than this code is not "healthy": the connection is
    # fine, but the data may not be where this version looks for it.
    schema_ok = _schema_state().get("status") != "too_new"
    status = (
        "healthy" if (database_connected and mqtt_connected and schema_ok) else "unhealthy"
    )
    return HealthCheckResponse(
        status=status,
        service="backend",
        version=get_version(),
        uptime_seconds=uptime_seconds,
        mqtt_connected=mqtt_connected,
        database_connected=database_connected,
    )
