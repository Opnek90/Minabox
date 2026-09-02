"""Shared foundation for the route modules: config, auth, host access."""

from __future__ import annotations

import os
import secrets
import shlex
import subprocess
import threading
from pathlib import Path

import docker
import structlog
from fastapi import Header, HTTPException

from host_helper.config import Config

logger = structlog.get_logger(__name__)

_config: Config | None = None


_docker_client: docker.DockerClient | None = None


_docker_client_lock = threading.Lock()


def _docker() -> docker.DockerClient:
    """The shared Docker client.

    docker.from_env() builds a fresh connection pool every time, and nothing
    ever closed the old one; with the WebUI polling container logs those add
    up. One client is enough - it opens a connection per call and is cheap to
    keep - so it is cached here and dropped only when a call fails, which is
    the one situation where a stale client would show.
    """
    global _docker_client
    with _docker_client_lock:
        if _docker_client is None:
            _docker_client = docker.from_env()
        return _docker_client


def _drop_docker_client() -> None:
    """Forget the cached client so the next caller builds a fresh one."""
    global _docker_client
    with _docker_client_lock:
        client, _docker_client = _docker_client, None
    if client is not None:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - closing must never be the failure
            pass


def get_config() -> Config:
    if _config is None:
        raise RuntimeError("Config not loaded")
    return _config


def set_config(cfg: Config) -> None:
    global _config
    _config = cfg


def _check_api_key(x_api_key: str | None = Header(None, alias="X-Api-Key")) -> None:
    """Validate the shared secret. This is the only gate in front of a service
    that runs as root with the host filesystem mounted, so the comparison must
    not leak the key through its timing."""
    expected = get_config().api_key.strip()
    if not x_api_key or not expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    if not secrets.compare_digest(x_api_key.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def parse_step_markers(text: str, default_step_count: int) -> dict:
    """Read the current step and the result out of a run log.

    Every long-running job on the host writes the same two markers, because
    they have to survive a restart of this service:

        === MINABOX-STEP <n>/<total> <key>
        === MINABOX-DONE <exit code>

    The step keys are part of the contract with the WebUI, which translates
    them; the parser itself does not care what they are called.
    """
    step: int | None = None
    step_count = default_step_count
    step_key: str | None = None
    exit_code: int | None = None
    for line in text.splitlines():
        if line.startswith("=== MINABOX-STEP "):
            parts = line.removeprefix("=== MINABOX-STEP ").split()
            if len(parts) >= 2 and "/" in parts[0]:
                current, _, total = parts[0].partition("/")
                if current.isdigit() and total.isdigit():
                    step, step_count = int(current), int(total)
                    step_key = parts[1]
        elif line.startswith("=== MINABOX-DONE "):
            value = line.removeprefix("=== MINABOX-DONE ").strip()
            exit_code = int(value) if value.lstrip("-").isdigit() else -1
    return {
        "step": step,
        "step_count": step_count,
        "step_key": step_key,
        "exit_code": exit_code,
    }


def _host_root() -> Path:
    """Where the host filesystem is mounted inside this container.

    Configured as HOST_ROOT and in practice always /host, but the fallback
    stays: a container started without the mount would otherwise resolve every
    host tool path against a directory that does not exist, and fail with a
    confusing "not found on host" instead of an obvious one.
    """
    configured = get_config().host_root or "/host"
    root = Path(configured).resolve()
    return root if root.exists() else Path("/host").resolve()


def _host_tool(*relative: str) -> Path | None:
    """The first of these host binaries that exists, or None.

    Paths are relative to the host root, e.g. _host_tool("usr/bin/nmcli").
    """
    root = _host_root()
    for rel in relative:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def _nsenter_bin() -> Path:
    """nsenter, preferably the host's copy, otherwise the container's."""
    nsenter = _host_tool("usr/bin/nsenter")
    if nsenter is not None:
        return nsenter
    if Path("/usr/bin/nsenter").exists():
        return Path("/usr/bin/nsenter")
    raise FileNotFoundError("nsenter not available on host")


def _run_on_host_via_nsenter(
    args: list[str], timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run a command on the host via nsenter (host PID, network, mount)."""
    nsenter_bin = _nsenter_bin()
    cmd = [str(nsenter_bin), "-t", "1", "-n", "-m", "--"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# This container has no Docker CLI, and shipping one would only duplicate what
# the host already runs. Every compose call therefore goes through the host's
# namespaces - the same route the update takes, and the only one that works.
SELF_SERVICE = "host-helper"


def _run_compose_on_host(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run `docker compose <args>` in the project directory on the host."""
    workspace = _host_workspace()
    argv = " ".join(shlex.quote(a) for a in args)
    script = f"cd {shlex.quote(workspace)} || exit 1; docker compose {argv}"
    return _run_on_host_via_nsenter(["/bin/sh", "-c", script], timeout=timeout)


def _run_compose_on_others(
    action: list[str], timeout: int
) -> subprocess.CompletedProcess:
    """Run `docker compose <action>` for every service except this one.

    Stopping or restarting the host-helper along with the rest would kill the
    process that still has to finish the job. Nothing a restore or a factory
    reset writes belongs to this service, so leaving it running costs nothing.
    """
    workspace = _host_workspace()
    verb = " ".join(shlex.quote(a) for a in action)
    script = (
        f"cd {shlex.quote(workspace)} || exit 1; "
        f"others=$(docker compose ps --services "
        f"| grep -vx {shlex.quote(SELF_SERVICE)} | tr '\\n' ' '); "
        f'[ -n "$others" ] || exit 0; '
        f"docker compose {verb} $others"
    )
    return _run_on_host_via_nsenter(["/bin/sh", "-c", script], timeout=timeout)


def _host_workspace() -> str:
    """The project path on the host - not the container path /workspace.

    Compose stamps it as a label onto every container it creates. Reading it
    there is more reliable than configuring it: by definition it matches how
    the box was actually started.
    """
    configured = os.environ.get("HOST_WORKSPACE_PATH")
    if configured:
        return configured
    try:
        own = _docker().containers.get(os.uname().nodename)
        path = (own.labels or {}).get("com.docker.compose.project.working_dir")
        if path:
            return str(path)
    except Exception as e:
        _drop_docker_client()
        logger.debug("host_workspace_lookup_failed", error=str(e))
    return "/home/pi/minabox"
