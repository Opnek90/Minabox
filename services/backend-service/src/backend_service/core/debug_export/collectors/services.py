"""Service-level collectors: health, container metadata, logs, network.

These reuse the paths that already exist - the Host-Helper endpoints for logs
and network, the Docker SDK the status page already talks to - instead of
opening new ones (docs/DebugExport.md 4.3).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from backend_service.core.debug_export import logfilter
from backend_service.core.debug_export.framework import (
    BLOCK_LOGS,
    BLOCK_NETWORK,
    BLOCK_SYSTEM,
    ExportContext,
    register,
)
from backend_service.core.debug_export.redaction import pseudonymize

logger = structlog.get_logger(__name__)

HEALTH_TIMEOUT = 3.0

# The service catalogue lives in routes_system, which imports the API package -
# importing it at module level would close a cycle back into this module via
# routes_debug. Every use below therefore imports it inside the function.


@register("services.health", BLOCK_SYSTEM, timeout=25.0)
async def collect_service_health(ctx: ExportContext) -> dict[str, Any]:
    """Reachability plus container metadata for every service."""
    from backend_service.api.routes_system import SERVICE_HEALTH_URLS, SERVICE_IDS

    async def probe(service_id: str) -> dict[str, Any]:
        url = SERVICE_HEALTH_URLS.get(service_id)
        entry: dict[str, Any] = {"service": service_id}
        if not url:
            entry["state"] = "not checked"
            return entry
        try:
            async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
                response = await client.get(url)
            entry["state"] = "online" if 200 <= response.status_code < 300 else "fehler"
            entry["http_status"] = response.status_code
            try:
                entry["health"] = response.json()
            except ValueError:
                entry["health"] = (response.text or "")[:500]
        except Exception as e:
            entry["state"] = "offline"
            entry["error"] = f"{type(e).__name__}: {e}"
        return entry

    probes = await asyncio.gather(*(probe(sid) for sid in SERVICE_IDS))
    containers = await asyncio.to_thread(_container_metadata)

    for entry in probes:
        meta = containers.get(entry["service"])
        if meta:
            entry["container"] = meta

    return {"services/health.json": {"services": probes}}


def _container_metadata() -> dict[str, dict[str, Any]]:
    """Restart counts and exit codes - a restart loop is visible here and nowhere else."""
    from backend_service.api.routes_system import CONTAINER_NAMES

    result: dict[str, dict[str, Any]] = {}
    try:
        import docker

        client = docker.from_env()
    except Exception as e:
        logger.debug("debug_export_docker_unavailable", error=str(e))
        return result

    for service_id, container_name in CONTAINER_NAMES.items():
        try:
            container = client.containers.get(container_name)
            attrs = container.attrs or {}
            state = attrs.get("State", {}) or {}
            config = attrs.get("Config", {}) or {}
            result[service_id] = {
                "name": container_name,
                "status": state.get("Status"),
                "started_at": state.get("StartedAt"),
                "finished_at": state.get("FinishedAt"),
                "exit_code": state.get("ExitCode"),
                "oom_killed": state.get("OOMKilled"),
                "restart_count": attrs.get("RestartCount"),
                "health": (state.get("Health") or {}).get("Status"),
                "image": config.get("Image"),
                "image_id": (attrs.get("Image") or "")[:19],
            }
        except Exception as e:
            result[service_id] = {
                "name": container_name,
                "error": f"{type(e).__name__}: {e}",
            }
    return result


@register("system.docker", BLOCK_SYSTEM, timeout=20.0)
def collect_docker(ctx: ExportContext) -> dict[str, Any]:
    """Docker version and disk usage - orphaned images fill a small SD card fast."""
    try:
        import docker

        client = docker.from_env()
        version = client.version() or {}
        data: dict[str, Any] = {
            "server_version": version.get("Version"),
            "api_version": version.get("ApiVersion"),
            "os": version.get("Os"),
            "arch": version.get("Arch"),
        }
        try:
            info = client.info() or {}
            data["storage_driver"] = info.get("Driver")
            data["containers_running"] = info.get("ContainersRunning")
            data["containers_stopped"] = info.get("ContainersStopped")
            data["images"] = info.get("Images")
            data["kernel_version"] = info.get("KernelVersion")
            data["memory_total_mb"] = round((info.get("MemTotal") or 0) / 1024**2)
        except Exception as e:
            data["info_error"] = f"{type(e).__name__}: {e}"
        try:
            usage = client.df() or {}
            data["disk_usage"] = {
                "images_bytes": sum(
                    i.get("Size", 0) for i in (usage.get("Images") or [])
                ),
                "containers": len(usage.get("Containers") or []),
                "volumes": len(usage.get("Volumes") or []),
            }
        except Exception as e:
            data["df_error"] = f"{type(e).__name__}: {e}"
        return {"system/docker.json": data}
    except Exception as e:
        return {"system/docker.json": {"error": f"{type(e).__name__}: {e}"}}


@register("logs.services", BLOCK_LOGS, timeout=60.0, bulky=True)
async def collect_service_logs(ctx: ExportContext) -> dict[str, Any]:
    """Container logs per service, via Host-Helper with a Docker SDK fallback."""
    from backend_service.api.routes_system import (
        SERVICE_IDS,
        _get_logs_via_docker,
        _get_logs_via_host_helper,
    )

    tail = ctx.options.log_tail
    files: dict[str, Any] = {}

    async def fetch(service_id: str) -> tuple[str, str | None]:
        content = await _get_logs_via_host_helper(service_id, tail)
        if content is None:
            content = await _get_logs_via_docker(service_id, tail)
        return service_id, content

    results = await asyncio.gather(*(fetch(sid) for sid in SERVICE_IDS))
    missing: list[str] = []
    for service_id, content in results:
        if content:
            files[f"services/{service_id}/logs.txt"] = logfilter.render_truncated_text(
                content, tail, source=f"container {service_id}"
            )
        else:
            missing.append(service_id)
    if missing:
        files["services/logs_missing.json"] = {
            "services": missing,
            "note": (
                "No logs could be fetched for these services. It may mean the "
                "container does not exist - which is a finding in itself."
            ),
        }
    return files


# Fetched wide, kept narrow: the difference is what the noise filter removes.
SYSLOG_FETCH_LINES = 20000
SYSLOG_KEEP_LINES = 800


@register("logs.syslog", BLOCK_LOGS, timeout=45.0, bulky=True)
async def collect_syslog(ctx: ExportContext) -> dict[str, Any]:
    """Kernel and docker unit logs from the host, plus an under-voltage scan.

    The kernel log is where the *history* of under-voltage events lives, which
    is what we give up by not talking to /dev/vcio.
    """
    from backend_service.api.routes_host import _host_helper_api_key, _request

    api_key = _host_helper_api_key()
    if not api_key:
        return {
            "logs/syslog_unavailable.json": {
                "reason": "Host-Helper not configured (HOST_HELPER_API_KEY missing)"
            }
        }

    files: dict[str, Any] = {}
    undervoltage_hits = 0
    for source in ("kernel", "docker"):
        try:
            # Ask for a wide window and do the trimming here: the noise has to
            # be dropped *before* the line budget applies, otherwise veth churn
            # eats the history (2026-08-18: 799 lines, all of it bridge chatter,
            # window starting two hours after the last boot).
            response = await _request(
                "GET",
                "/syslog",
                api_key,
                timeout=20.0,
                params={"n": SYSLOG_FETCH_LINES, "source": source},
            )
            if response.status_code != 200:
                files[f"logs/syslog-{source}.txt"] = (
                    f"(Host-Helper answered with HTTP {response.status_code})"
                )
                continue
            lines = [str(line) for line in ((response.json() or {}).get("lines") or [])]
            files[f"logs/syslog-{source}.txt"] = logfilter.render_filtered_log(
                lines, SYSLOG_KEEP_LINES, source=f"journalctl {source}"
            )
            if source == "kernel":
                # Counted on the unfiltered stream: these lines are kept by the
                # filter anyway, but the count must not depend on the budget.
                undervoltage_hits = sum(
                    1
                    for line in lines
                    if "under-voltage" in line.lower() or "throttl" in line.lower()
                )
        except Exception as e:
            files[f"logs/syslog-{source}.txt"] = (
                f"(not retrievable: {type(e).__name__}: {e})"
            )

    files["logs/kernel_findings.json"] = {
        "undervoltage_or_throttling_lines": undervoltage_hits,
        "note": (
            "Counts kernel-log lines reporting under-voltage or throttling. "
            "Replaces the history bits from vcgencmd."
        ),
    }
    return files


@register("logs.host_diagnostics", BLOCK_LOGS, timeout=30.0)
async def collect_host_diagnostics(ctx: ExportContext) -> dict[str, Any]:
    """Failed systemd units and high-priority journal entries.

    The single new Host-Helper route: GET /diagnostics/host, parameterless.
    """
    from backend_service.api.routes_host import _host_helper_api_key, _request

    api_key = _host_helper_api_key()
    if not api_key:
        return {}
    try:
        response = await _request("GET", "/diagnostics/host", api_key, timeout=20.0)
    except Exception as e:
        return {"system/systemd.json": {"error": f"{type(e).__name__}: {e}"}}
    if response.status_code == 404:
        return {
            "system/systemd.json": {
                "error": "Host-Helper does not know /diagnostics/host - older version?"
            }
        }
    if response.status_code != 200:
        return {"system/systemd.json": {"error": f"HTTP {response.status_code}"}}
    return {"system/systemd.json": response.json()}


@register("network.status", BLOCK_NETWORK, timeout=25.0)
async def collect_network(ctx: ExportContext) -> dict[str, Any]:
    """Network and host status. SSID and MAC are pseudonymised, never dropped."""
    from backend_service.api.routes_host import _host_helper_api_key, _request

    api_key = _host_helper_api_key()
    if not api_key:
        return {
            "system/network.json": {
                "reason": "Host-Helper not configured (HOST_HELPER_API_KEY missing)"
            }
        }

    files: dict[str, Any] = {}
    for path, target in (
        ("/system/network", "network"),
        ("/host-status", "host_status"),
    ):
        try:
            response = await _request("GET", path, api_key, timeout=15.0)
            payload = (
                response.json()
                if response.status_code == 200
                else {"error": f"HTTP {response.status_code}"}
            )
        except Exception as e:
            payload = {"error": f"{type(e).__name__}: {e}"}
        if isinstance(payload, dict):
            payload = _pseudonymize_network(payload, ctx.salt)
        files[f"system/{target}.json"] = payload

    try:
        response = await _request("GET", "/system/time-status", api_key, timeout=10.0)
        files["system/time_status.json"] = (
            response.json()
            if response.status_code == 200
            else {"error": f"HTTP {response.status_code}"}
        )
    except Exception as e:
        files["system/time_status.json"] = {"error": f"{type(e).__name__}: {e}"}

    return files


def _pseudonymize_network(payload: dict[str, Any], salt: str) -> dict[str, Any]:
    """Hash the identifying bits: the diagnosis needs "same network", not its name."""
    sensitive_keys = ("ssid", "mac", "hwaddr", "bssid", "hostname")
    result: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if isinstance(value, dict):
            result[key] = _pseudonymize_network(value, salt)
        elif isinstance(value, list):
            result[key] = [
                _pseudonymize_network(item, salt) if isinstance(item, dict) else item
                for item in value
            ]
        elif any(part in lowered for part in sensitive_keys) and isinstance(value, str):
            result[key] = pseudonymize(value, salt)
        else:
            result[key] = value
    return result
