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
from fastapi import APIRouter, Depends, HTTPException
from shared_lib.version import get_version
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend_service.api.routes_host import _host_helper_api_key, _host_helper_url
from backend_service.api.websocket import ws_manager
from backend_service.config import get_config
from backend_service.core import container_registry
from backend_service.core import update_check as update_check_service
from backend_service.core.db_manager import get_db
from backend_service.core.mqtt_client import MQTTClient
from backend_service.models.schemas import HealthCheckResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

_start_time = time.time()
_mqtt_client: MQTTClient | None = None

# Welche Container es auf einer Box wirklich gibt, haengt an COMPOSE_PROFILES -
# deshalb wird die Liste zur Laufzeit bei Docker erfragt (container_registry).
# Dieser Katalog bleibt aus zwei Gruenden bestehen:
#   1. als Fallback, wenn der Docker-Socket nicht nutzbar ist,
#   2. als Anzeigereihenfolge - erst die Basis, dann die Hardware, zuletzt die
#      Dienste, die ein Nutzer selten anschaut.
# Ein Dienst, der hier fehlt, wird trotzdem angezeigt; er landet nur ans Ende.
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


async def _check_service_http(sid: str) -> dict | None:
    """Probe a service's /health endpoint.

    Returns the parsed body on success (so the caller also gets the version the
    service reports about itself), an empty dict when it answered but sent no
    usable JSON, and None when it did not answer at all. Only used on the
    fallback path - with Docker available the container health check already
    ran the very same request.
    """
    url = SERVICE_HEALTH_URLS.get(sid)
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
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


def _schema_state() -> dict:
    """Ergebnis der Schemapruefung aus dem Datenbank-Manager."""
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
        # Stand der Datenbank gegenueber dem, was dieser Code erwartet.
        "database": _schema_state(),
        "services": services,
    }


# Ein Dienstname muss ein Docker-Name sein koennen - alles andere kommt gar
# nicht erst bis zum Socket.
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
    # Nicht mehr gegen die feste Liste pruefen: welche Dienste es gibt,
    # entscheiden die Profile. Ein unbekannter Name ist "gibt es hier nicht"
    # (404), ein syntaktisch unmoeglicher ist ein Aufruffehler (400).
    if not _SERVICE_NAME_RE.match(service):
        raise HTTPException(status_code=400, detail="Invalid service")
    if await _container_for(service) is None and service not in SERVICE_IDS:
        raise HTTPException(status_code=404, detail="Unknown service")
    content = await _get_logs_via_host_helper(service, tail)
    if content is None:
        content = await _get_logs_via_docker(service, tail)
    if content is not None:
        return {"service": service, "lines": content, "tail": tail}
    data_path = os.environ.get("DATA_PATH", "/data")
    path = Path(data_path) / "logs" / f"{service}.log"
    if not path.exists():
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


@router.get("/update-check")
async def update_check(force: bool = False) -> dict:
    """Vergleicht die laufenden Versionen mit dem veroeffentlichten Stand.

    `force=true` umgeht den Zwischenspeicher - das ist der Knopf in der
    Oberflaeche; ohne den Parameter antwortet der zwischengespeicherte Stand.
    """
    entries = await container_registry.discover()
    if entries is None:
        raise HTTPException(
            status_code=503,
            detail="Ohne Docker-Zugriff sind die laufenden Versionen nicht bekannt.",
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
    # Eine Datenbank, die neuer ist als dieser Code, ist kein "gesund": die
    # Verbindung steht, aber die Daten liegen moeglicherweise woanders, als
    # diese Fassung sie sucht.
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
