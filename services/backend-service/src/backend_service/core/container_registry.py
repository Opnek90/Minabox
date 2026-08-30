"""Discovery of the running Minabox containers via the Docker socket.

Why the Docker socket and not MQTT or HTTP probes:

* It is the only source that covers *every* container uniformly. Mosquitto and
  the nginx-based WebUI speak no MQTT and expose no Minabox health schema, but
  Docker knows their state, their labels and their resource usage.
* It answers even when a service hangs. A container whose process stopped
  replying still has a status, a restart count and an exit code here.
* It reflects what is actually installed. Which containers exist depends on
  ``COMPOSE_PROFILES``; a box without the LED profile simply has no LED
  container, and asking Docker is the difference between "not installed" and
  "broken".

The socket is mounted read-only into the backend (``docker-compose.yml``) and
the container joins the host's ``docker`` group via ``DOCKER_GID``. When that
is missing, callers fall back to the static catalogue in ``routes_system``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Labels Compose writes on every container it creates.
PROJECT_LABEL = "com.docker.compose.project"
SERVICE_LABEL = "com.docker.compose.service"

# Careful: Compose stamps project and service into the *image* it builds, so
# every container started from a Minabox image inherits them - including a
# one-off `docker run` for debugging, which would then show up as a second
# "backend". These two labels are written only when Compose actually creates a
# container, so they are what separates a real service from a stray one.
CONTAINER_NUMBER_LABEL = "com.docker.compose.container-number"
ONEOFF_LABEL = "com.docker.compose.oneoff"

# OCI labels our Dockerfiles set from build args.
# eclipse-mosquitto ships them too, which is why the broker needs no special
# case to report a version.
VERSION_LABEL = "org.opencontainers.image.version"
REVISION_LABEL = "org.opencontainers.image.revision"
CREATED_LABEL = "org.opencontainers.image.created"

DEFAULT_PROJECT = "minabox"
NAME_PREFIX = "minabox-"

# A stats sample blocks for roughly a second (Docker needs two CPU readings to
# form a delta). With one worker per container the whole set costs about that
# same second instead of queueing behind the default executor, which on a Pi 4
# holds only eight threads.
_STATS_MAX_WORKERS = 16


_client_lock = threading.Lock()
_client: Any | None = None


def _docker_client() -> Any | None:
    """Docker SDK client, or None when the socket is not usable.

    Cached: this used to build a fresh client per call, and `collect_stats`
    calls it once per container. One /system/status request - which the WebUI
    polls - therefore opened a dozen connections to the socket and closed none
    of them. Guarded by a lock because the stats run in a thread pool.
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            import docker

            _client = docker.from_env()
        except Exception as e:  # ImportError, DockerException, PermissionError
            logger.debug("docker_client_unavailable", error=str(e))
            return None
    return _client


def _own_project(client: Any) -> str:
    """Compose project this backend belongs to.

    Read from our own container rather than configured: the hostname of a
    container is its id unless overridden, so we can look ourselves up and take
    the project label we were actually started with. Falls back to the
    environment and then to the default name.
    """
    try:
        own = client.containers.get(os.uname().nodename)
        project = (own.labels or {}).get(PROJECT_LABEL)
        if project:
            return str(project)
    except Exception as e:
        logger.debug("own_container_lookup_failed", error=str(e))
    return os.environ.get("COMPOSE_PROJECT_NAME") or DEFAULT_PROJECT


def _map_state(status: str, health: str | None) -> str:
    """Map Docker's container status to the three states the UI knows.

    ``starting`` counts as online on purpose: during the health check's start
    period the container is up and doing what it should, and showing it as
    offline would make every restart look like a fault.
    """
    if status == "running":
        if health == "unhealthy":
            return "error"
        return "online"
    if status in ("restarting", "dead"):
        return "error"
    if status == "exited":
        return "error"
    # created, paused, removing
    return "offline"


def _describe(container: Any) -> dict[str, Any]:
    """Turn one Docker container into the entry the status API returns."""
    attrs = container.attrs or {}
    state = attrs.get("State") or {}
    config = attrs.get("Config") or {}
    labels: dict[str, str] = config.get("Labels") or {}

    status = str(state.get("Status") or "unknown")
    health = (state.get("Health") or {}).get("Status")
    exit_code = state.get("ExitCode")

    service = labels.get(SERVICE_LABEL) or container.name.removeprefix(NAME_PREFIX)

    entry: dict[str, Any] = {
        "service": service,
        "container": container.name,
        "state": _map_state(status, health),
        "docker_status": status,
        "health": health,
        "version": labels.get(VERSION_LABEL),
        "git_sha": labels.get(REVISION_LABEL),
        "build_date": labels.get(CREATED_LABEL),
        "image": config.get("Image"),
        "restart_count": attrs.get("RestartCount"),
        "started_at": state.get("StartedAt"),
    }
    # Only interesting when something went wrong - a zero here on a running
    # container is noise.
    if status != "running" and exit_code is not None:
        entry["exit_code"] = exit_code
    if state.get("OOMKilled"):
        entry["oom_killed"] = True
    return entry


def _is_compose_service(container: Any) -> bool:
    """True for a container Compose created as a service of the project."""
    labels = container.labels or {}
    if CONTAINER_NUMBER_LABEL not in labels:
        # Only the image labels are present - something started this by hand.
        return False
    # `docker compose run` containers are throwaway, not part of the stack.
    return str(labels.get(ONEOFF_LABEL, "False")).lower() != "true"


def _pick(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Choose between two containers claiming the same service id.

    Prefers the one named the way docker-compose.yml names it, then a running
    one over a stopped one. Only reached when something unusual is going on -
    a leftover container, a manual start - and then showing the real service is
    more useful than showing whichever Docker listed first.
    """
    for entry in (current, candidate):
        if entry.get("container") == f"{NAME_PREFIX}{entry.get('service')}":
            return entry
    if current.get("docker_status") == "running":
        return current
    if candidate.get("docker_status") == "running":
        return candidate
    return current


def _discover_sync() -> list[dict[str, Any]] | None:
    """Blocking discovery. Returns None when Docker is unreachable."""
    client = _docker_client()
    if client is None:
        return None
    project = _own_project(client)
    try:
        containers = [
            c
            for c in client.containers.list(
                all=True, filters={"label": f"{PROJECT_LABEL}={project}"}
            )
            if _is_compose_service(c)
        ]
    except Exception as e:
        logger.debug("docker_container_list_failed", error=str(e))
        return None

    if not containers:
        # A stack started without Compose has no usable container labels, but it
        # still follows the naming convention.
        try:
            containers = [
                c
                for c in client.containers.list(all=True)
                if c.name.startswith(NAME_PREFIX)
            ]
        except Exception as e:
            logger.debug("docker_container_list_failed", error=str(e))
            return None

    by_service: dict[str, dict[str, Any]] = {}
    for container in containers:
        try:
            entry = _describe(container)
        except Exception as e:
            logger.debug(
                "container_describe_failed", container=container.name, error=str(e)
            )
            continue
        service = entry["service"]
        existing = by_service.get(service)
        by_service[service] = _pick(existing, entry) if existing else entry
    return list(by_service.values())


async def discover() -> list[dict[str, Any]] | None:
    """Every container of this Compose project, or None without Docker."""
    try:
        return await asyncio.to_thread(_discover_sync)
    except Exception as e:
        logger.debug("container_discovery_failed", error=str(e))
        return None


def parse_stats(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn one raw Docker stats sample into CPU and RAM figures.

    Kept separate from the socket call so the arithmetic - especially the
    "memory is not measurable here" case - stays testable without Docker.
    """
    cpu_stats = raw.get("cpu_stats") or {}
    precpu_stats = raw.get("precpu_stats") or {}
    cpu_delta = (cpu_stats.get("cpu_usage") or {}).get("total_usage", 0) - (
        precpu_stats.get("cpu_usage") or {}
    ).get("total_usage", 0)
    system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
        "system_cpu_usage", 0
    )
    num_cpus = cpu_stats.get("online_cpus") or len(
        (cpu_stats.get("cpu_usage") or {}).get("percpu_usage", [1])
    )
    cpu_percent = (
        round((cpu_delta / system_delta) * num_cpus * 100.0, 1)
        if system_delta > 0
        else 0.0
    )

    memory_stats = raw.get("memory_stats") or {}
    mem_usage = memory_stats.get("usage")
    if mem_usage is None:
        # A missing "usage" key means the kernel's memory cgroup controller is
        # off - the default on Raspberry Pi OS until cgroup_memory=1 lands in
        # cmdline.txt. `docker stats` reports 0B/0B on such a host too. None
        # keeps "not measurable" apart from "uses no memory", so the UI can
        # omit the bar instead of drawing an empty one that looks like a
        # reading.
        return {"cpu_percent": cpu_percent, "memory_mb": None, "memory_percent": None}

    # Subtract page cache so the number matches what `docker stats` prints.
    stats_detail = memory_stats.get("stats") or {}
    mem_cache = stats_detail.get("cache", 0) or stats_detail.get("inactive_file", 0)
    mem_rss = max(mem_usage - mem_cache, 0)
    mem_limit = memory_stats.get("limit", 0)

    return {
        "cpu_percent": cpu_percent,
        "memory_mb": round(mem_rss / 1024 / 1024, 1),
        # What the percentage refers to depends on the setup: Docker reports the
        # container's memory limit, and where none is set - the default here,
        # see the note on resource limits in docker-compose.yml - that is the
        # host's total RAM. So today this reads as "share of system memory";
        # once limits are configured it becomes "share of this container's
        # budget". Zero only occurs when Docker reports no limit at all.
        "memory_percent": (
            round((mem_rss / mem_limit) * 100.0, 1) if mem_limit > 0 else None
        ),
    }


def _stats_sync(container_name: str) -> dict[str, Any] | None:
    """CPU and RAM for one container (blocking, ~1s)."""
    client = _docker_client()
    if client is None:
        return None
    try:
        container = client.containers.get(container_name)
        return parse_stats(container.stats(stream=False))
    except Exception as e:
        logger.debug("container_stats_failed", container=container_name, error=str(e))
        return None


async def collect_stats(container_names: list[str]) -> dict[str, dict[str, Any]]:
    """CPU and RAM for the given containers, gathered in parallel."""
    if not container_names:
        return {}
    loop = asyncio.get_running_loop()
    workers = min(len(container_names), _STATS_MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="stats") as pool:
        results = await asyncio.gather(
            *(
                loop.run_in_executor(pool, _stats_sync, name)
                for name in container_names
            ),
            return_exceptions=True,
        )
    return {
        name: result
        for name, result in zip(container_names, results, strict=True)
        if isinstance(result, dict)
    }


# The service -> container mapping is asked for once per log request and once
# per service in the debug export. Container names change only when Compose
# recreates something, so a short cache saves a pile of socket round trips
# without ever being meaningfully stale.
_NAME_CACHE_TTL = 30.0
_name_cache: tuple[float, dict[str, str]] | None = None


async def service_container_names() -> dict[str, str] | None:
    """Map service id to container name, or None when Docker is unavailable."""
    global _name_cache

    now = asyncio.get_running_loop().time()
    if _name_cache is not None and now - _name_cache[0] < _NAME_CACHE_TTL:
        return _name_cache[1]

    entries = await discover()
    if entries is None:
        return None
    mapping = {
        e["service"]: e["container"]
        for e in entries
        if e.get("service") and e.get("container")
    }
    _name_cache = (now, mapping)
    return mapping
