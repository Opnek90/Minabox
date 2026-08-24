"""Container logs and the read-only host diagnostics."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import UTC, datetime

import structlog
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound
from fastapi import APIRouter, Depends, HTTPException

from host_helper.api.routes.deps import (
    _check_api_key,
    _docker,
    _drop_docker_client,
    _run_on_host_via_nsenter,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _is_allowed_container_name(name: str) -> bool:
    """Allow only Minabox container names (e.g. minabox-backend, minabox-audio)."""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    return name.startswith("minabox-") and all(c.isalnum() or c == "-" for c in name)


def _read_container_logs(container_name: str, tail: int) -> dict:
    """Blocking Docker SDK call - run via asyncio.to_thread."""
    container = _docker().containers.get(container_name)
    out = container.logs(tail=tail, stdout=True, stderr=True)
    return {"lines": out.decode("utf-8", errors="replace").strip(), "tail": tail}


@router.get("/container-logs")
async def container_logs(
    container_name: str,
    tail: int = 200,
    _: None = Depends(_check_api_key),
) -> dict:
    """Return last N lines of a container's logs via Docker CLI. Requires API key."""
    if not _is_allowed_container_name(container_name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    tail = max(1, min(int(tail), 500))
    try:
        return await asyncio.to_thread(_read_container_logs, container_name, tail)
    except DockerNotFound:
        raise HTTPException(status_code=404, detail="Container not found") from None
    except DockerAPIError as e:
        # The daemon answered, so the client is fine - only the request failed.
        raise HTTPException(
            status_code=502, detail=str(e.explanation or str(e))[:500]
        ) from e
    except Exception as e:
        # Anything else is a transport problem; the cached client may be the
        # stale half of it, so drop it and let the next call rebuild.
        _drop_docker_client()
        logger.exception("container_logs_failed")
        raise HTTPException(status_code=503, detail="Docker not available") from e


# ── Diagnostics (read-only, for the debug export) ────────────────────

# Fixed command list. This is the single route the debug export adds to a
# service that runs as root with the host mounted, so it takes no parameters at
# all: nothing from the caller can influence what runs here.
# See docs/DebugExport.md section 4.3.
_DIAGNOSTIC_COMMANDS: tuple[tuple[str, list[str], int], ...] = (
    ("failed_units", ["systemctl", "--failed", "--no-legend"], 15),
    (
        "journal_errors",
        ["journalctl", "-p", "3", "-n", "200", "--no-pager", "-o", "short-iso"],
        20,
    ),
    ("timedatectl", ["timedatectl", "show"], 10),
)


_DIAGNOSTIC_OUTPUT_LIMIT = 64 * 1024


def _run_diagnostic(args: list[str], timeout: int) -> dict:
    """Run one fixed command on the host. Never raises - failures are data."""
    try:
        result = _run_on_host_via_nsenter(args, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "output": ""}
    output = ((result.stdout or "") + (result.stderr or ""))[:_DIAGNOSTIC_OUTPUT_LIMIT]
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output,
    }


@router.get("/diagnostics/host")
def diagnostics_host(_: None = Depends(_check_api_key)) -> dict:
    """Read-only host diagnostics: failed units, journal errors, clock status."""
    results = {
        name: _run_diagnostic(args, timeout)
        for name, args, timeout in _DIAGNOSTIC_COMMANDS
    }
    return {
        "collected_at": datetime.now(UTC).isoformat(),
        "commands": results,
    }
