"""FastAPI routes for the host-helper: every host-level operation the box offers."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import docker
import structlog
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from shared_lib.version import get_version as get_build_version
from starlette.background import BackgroundTask

from host_helper.config import Config, validate_path_under_allowed

logger = structlog.get_logger(__name__)

router = APIRouter()

_config: Config | None = None

# Move job state for progress (idle | running | done | error)
_move_state: dict = {"status": "idle", "total": 0, "current": 0, "error": None}
_move_lock = threading.Lock()

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


class ApplyAudioPathBody(BaseModel):
    audio_files_path: str


class MoveBody(BaseModel):
    source: str
    destination: str


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


def _host_path_to_container(path_str: str, host_root: str) -> Path:
    """Map a host-absolute path to its place inside the container."""
    p = path_str.strip()
    if not p.startswith("/"):
        return Path(p)
    if not host_root:
        return Path(p).resolve()
    return (Path(host_root) / p.lstrip("/")).resolve()


def _validate_host_path_under_allowed(
    path_str: str, allowed_base_paths: list[str], host_root: str
) -> Path:
    """Resolve a host path and require it to sit under an allowed base path."""
    if not path_str or ".." in path_str:
        raise ValueError("Invalid path")
    container_path = _host_path_to_container(path_str, host_root)
    if not container_path.is_absolute():
        raise ValueError("Path must be absolute")
    allowed = [
        Path(host_root) / b.lstrip("/") if host_root else Path(b)
        for b in allowed_base_paths
    ]
    for base in allowed:
        try:
            base_resolved = base.resolve()
            container_path.relative_to(base_resolved)
            return container_path
        except ValueError:
            continue
    raise ValueError("Path not under allowed base paths")


@router.get("/health")
async def health() -> dict:
    """Deliberately async: this is what the Docker healthcheck polls, and it
    does no blocking work. Keeping it off the threadpool means it stays
    answerable even while a long update occupies the worker threads."""
    return {"status": "ok", "service": "host-helper", "version": get_build_version()}


@router.get("/audio-path")
def get_audio_path(_: None = Depends(_check_api_key)) -> dict:
    """Read AUDIO_FILES_PATH from .env (saved value for next start)."""
    cfg = get_config()
    env_path = cfg.env_file_path
    if not env_path.exists():
        return {"audio_files_path": None}
    try:
        content = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"audio_files_path": None}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("AUDIO_FILES_PATH="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return {"audio_files_path": value or None}
    return {"audio_files_path": None}


@router.post("/apply-audio-path")
def apply_audio_path(
    body: ApplyAudioPathBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Update only AUDIO_FILES_PATH in the .env file."""
    path_str = body.audio_files_path.strip()
    if not path_str:
        raise HTTPException(status_code=400, detail="audio_files_path required")
    cfg = get_config()
    env_path = cfg.env_file_path
    allowed = cfg.allowed_base_paths
    logger.info("apply_audio_path_requested", path=path_str)

    try:
        validate_path_under_allowed(path_str, allowed)
    except ValueError as e:
        logger.warning(
            "apply_audio_path_validation_failed", path=path_str, error=str(e)
        )
        raise HTTPException(status_code=400, detail="Invalid path") from e

    if not env_path.exists():
        logger.warning("env_file_not_found", path=str(env_path))
        raise HTTPException(status_code=500, detail="Env file not available")

    try:
        content = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("env_file_read_failed", path=str(env_path), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read env file") from e

    new_line = f"AUDIO_FILES_PATH={path_str}"
    lines = content.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("AUDIO_FILES_PATH="):
            lines[i] = new_line
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines.append("")
        lines.append(new_line)

    try:
        env_path.write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
    except OSError as e:
        logger.error("env_file_write_failed", path=str(env_path), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write env file") from e

    logger.info(
        "apply_audio_path_ok", audio_files_path=path_str, env_path=str(env_path)
    )
    return {"ok": True, "audio_files_path": path_str}


def _remove_empty_dirs(root: Path) -> None:
    """Drop the directories a move emptied, deepest first.

    One pass is enough: sorting by path depth guarantees a child is visited
    before its parent, so a directory that only held other empty directories
    is empty by the time it is reached.
    """
    try:
        directories = sorted(
            (p for p in root.rglob("*") if p.is_dir()),
            key=lambda p: -len(p.parts),
        )
    except OSError as e:
        logger.warning("move_cleanup_dirs_failed", path=str(root), error=str(e))
        return
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue  # still holds something - leave it alone


def _run_move(source: Path, dest: Path) -> None:
    """Background worker: move a file, or the contents of a directory, to dest.

    Walking the tree happens here rather than in the request. On a large music
    library the walk alone takes long enough to be worth reporting on, and
    doing it before the reply would hold both the caller and a worker thread
    for no reason. Until the count is in, progress stays at 0/0, which the
    WebUI renders as an indeterminate bar.
    """
    try:
        if source.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
            with _move_lock:
                _move_state.update(
                    {"status": "done", "total": 1, "current": 1, "error": None}
                )
            logger.info("move_ok", source=str(source), destination=str(dest))
            return

        files = sorted(f for f in source.rglob("*") if f.is_file())
        total = len(files)
        dest.mkdir(parents=True, exist_ok=True)
        with _move_lock:
            _move_state["total"] = total

        for i, file_path in enumerate(files):
            try:
                target = dest / file_path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file_path), str(target))
            except OSError as e:
                # Whatever was moved stays moved. Moving it back could fail
                # halfway too, and would leave the caller with even less idea
                # of where their files are; the count says how far it got.
                with _move_lock:
                    _move_state.update(
                        {
                            "status": "error",
                            "total": total,
                            "current": i,
                            "error": str(e),
                        }
                    )
                logger.error(
                    "move_failed",
                    source=str(source),
                    dest=str(dest),
                    files_moved=i,
                    files_total=total,
                    error=str(e),
                )
                return
            with _move_lock:
                _move_state["current"] = i + 1

        _remove_empty_dirs(source)
        with _move_lock:
            _move_state["status"] = "done"
        logger.info(
            "move_ok", source=str(source), destination=str(dest), files_moved=total
        )
    except Exception as e:
        with _move_lock:
            _move_state.update({"status": "error", "error": str(e)})
        logger.exception("move_failed")


@router.post("/move")
def move(
    body: MoveBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Start moving source into destination in the background; answers 202.

    Both are host paths; with HOST_ROOT set they are translated to their
    container equivalents under /host. Poll GET /move-status for progress.
    """
    source_str = body.source.strip()
    dest_str = body.destination.strip()
    cfg = get_config()
    allowed = cfg.allowed_base_paths
    host_root = cfg.host_root

    try:
        source = _validate_host_path_under_allowed(source_str, allowed, host_root)
        dest = _validate_host_path_under_allowed(dest_str, allowed, host_root)
    except ValueError as e:
        logger.warning(
            "move_validation_failed", source=source_str, dest=dest_str, error=str(e)
        )
        raise HTTPException(status_code=400, detail="Invalid path") from e

    logger.info(
        "move_requested",
        source_str=source_str,
        dest_str=dest_str,
        container_source=str(source),
        container_dest=str(dest),
    )
    if not source.exists():
        logger.warning(
            "move_source_not_found",
            source_str=source_str,
            container_path=str(source),
            host_root=host_root,
        )
        raise HTTPException(status_code=404, detail="Source not found")

    with _move_lock:
        if _move_state.get("status") == "running":
            raise HTTPException(status_code=409, detail="Move already in progress")
        # Claim the job in the same lock that checked it. Two separate blocks
        # let two requests both pass the check and both start a worker.
        _move_state.update(
            {"status": "running", "total": 0, "current": 0, "error": None}
        )

    threading.Thread(target=_run_move, args=(source, dest), daemon=True).start()
    return JSONResponse(
        content={"ok": True, "status": "running", "message": "Move started"},
        status_code=202,
    )


@router.get("/move-status")
def move_status(_: None = Depends(_check_api_key)) -> dict:
    """Return current move job progress (status: idle | running | done | error)."""
    with _move_lock:
        state = dict(_move_state)
    return state


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


@router.post("/reboot")
def reboot_host(_: None = Depends(_check_api_key)) -> dict:
    """Reboot the host (Pi). Runs on the host via nsenter."""
    try:
        nsenter_bin = _nsenter_bin()
        # Run in background so we can return before the host goes down
        subprocess.Popen(
            [str(nsenter_bin), "-t", "1", "-n", "-m", "--", "/sbin/reboot"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available on host"
        ) from e
    except Exception as e:
        logger.exception("reboot_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("reboot_initiated")
    return {"ok": True, "message": "Reboot initiated"}


@router.post("/shutdown")
def shutdown_host(_: None = Depends(_check_api_key)) -> dict:
    """Shutdown the host (Pi). Runs on the host via nsenter."""
    try:
        nsenter_bin = _nsenter_bin()
        subprocess.Popen(
            [
                str(nsenter_bin),
                "-t",
                "1",
                "-n",
                "-m",
                "--",
                "/sbin/shutdown",
                "-h",
                "now",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available on host"
        ) from e
    except Exception as e:
        logger.exception("shutdown_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("shutdown_initiated")
    return {"ok": True, "message": "Shutdown initiated"}


@router.post("/restart")
def restart_services(_: None = Depends(_check_api_key)) -> dict:
    """Restart the Minabox containers via docker compose on the host."""
    try:
        nsenter_bin = _nsenter_bin()
        # On the host: read the compose project directory from a container
        # label, then restart from there.
        sh_cmd = (
            "WORKDIR=$(docker inspect minabox-backend --format "
            "'{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}' 2>/dev/null); "
            '[ -n "$WORKDIR" ] && cd "$WORKDIR" && docker compose restart'
        )
        result = subprocess.run(
            [str(nsenter_bin), "-t", "1", "-n", "-m", "--", "/bin/sh", "-c", sh_cmd],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(
                status_code=502, detail=(out or "Restart failed")[-1000:]
            )
        logger.info("restart_services_done")
        return {"ok": True, "message": "Services restart initiated"}
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter or docker not available on host"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Restart timed out") from e
    except Exception as e:
        logger.exception("restart_services_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── WLAN & Hotspot ─────────────────────────────────────────────────────────


def _run_nmcli_host_network(
    args: list[str], timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run nmcli in the host network namespace so it sees wlan0. Needs pid=host."""
    root_path = _host_root()
    if _host_tool("usr/bin/nmcli") is None:
        raise HTTPException(
            status_code=503, detail="nmcli not found on host (install NetworkManager)"
        )
    nsenter = _nsenter_bin()
    dbus_addr = "unix:path=/var/run/dbus/system_bus_socket"  # path inside chroot
    # nsenter -t 1 -n: enter the network namespace of host PID 1, where wlan0 is.
    cmd = [
        str(nsenter),
        "-t",
        "1",
        "-n",
        "--",
        "chroot",
        str(root_path),
        "env",
        f"DBUS_SYSTEM_BUS_ADDRESS={dbus_addr}",
        "nmcli",
    ] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class WifiConnectBody(BaseModel):
    ssid: str
    password: str = ""


class HotspotStartBody(BaseModel):
    ssid: str = "Minabox-Setup"
    password: str = ""


@router.get("/wifi/scan")
def wifi_scan(_: None = Depends(_check_api_key)) -> dict:
    """List the available WiFi networks with their signal strength."""
    try:
        _run_nmcli_host_network(["dev", "wifi", "rescan"], timeout=15)
    except (subprocess.TimeoutExpired, HTTPException, OSError):
        pass
    try:
        r = _run_nmcli_host_network(
            ["-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list"], timeout=25
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="WiFi scan timed out") from e
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(status_code=503, detail=f"WiFi scan failed: {e}") from e
    if r.returncode != 0:
        raise HTTPException(
            status_code=502, detail=(r.stderr or r.stdout or "Scan failed")[:500]
        )
    networks: list[dict] = []
    for line in (r.stdout or "").strip().splitlines():
        parts = line.split(":", 1)
        if len(parts) >= 2:
            networks.append(
                {
                    "ssid": parts[0].strip() or None,
                    "signal": int(parts[1]) if parts[1].strip().isdigit() else 0,
                }
            )
    # Dedupe by SSID, keep max signal
    by_ssid: dict[str, int] = {}
    for n in networks:
        sid = n.get("ssid") or ""
        if sid and (sid not in by_ssid or (n.get("signal") or 0) > by_ssid[sid]):
            by_ssid[sid] = n.get("signal") or 0
    return {
        "networks": [
            {"ssid": s, "signal": by_ssid[s]}
            for s in sorted(by_ssid.keys(), key=lambda x: -by_ssid[x])
        ]
    }


def _wifi_connection_name(ssid: str) -> str:
    """A safe NetworkManager profile name for an SSID."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (ssid or ""))[:32]
    return f"Minabox-{safe}" if safe else "Minabox-WiFi"


@router.post("/wifi/connect")
def wifi_connect(
    body: WifiConnectBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Connect to a WiFi network by SSID and password.

    key-mgmt is set explicitly; without it NetworkManager refuses the profile
    with "property is missing".
    """
    ssid = (body.ssid or "").strip()
    if not ssid:
        raise HTTPException(status_code=400, detail="SSID required")
    password = (body.password or "").strip()
    con_name = _wifi_connection_name(ssid)
    try:
        try:
            _run_nmcli_host_network(["con", "delete", con_name], timeout=5)
        except Exception:
            pass
        _run_nmcli_host_network(
            [
                "con",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "autoconnect",
                "yes",
                "con-name",
                con_name,
                "ssid",
                ssid,
            ],
            timeout=10,
        )
        if password:
            _run_nmcli_host_network(
                [
                    "con",
                    "modify",
                    con_name,
                    "wifi-sec.key-mgmt",
                    "wpa-psk",
                    "wifi-sec.psk",
                    password,
                ],
                timeout=5,
            )
        else:
            _run_nmcli_host_network(
                ["con", "modify", con_name, "wifi-sec.key-mgmt", "none"],
                timeout=5,
            )
        r = _run_nmcli_host_network(["con", "up", con_name], timeout=45)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Connect timed out") from e
    except HTTPException:
        raise
    if r.returncode != 0:
        raise HTTPException(
            status_code=400, detail=(r.stderr or r.stdout or "Connect failed")[:500]
        )
    return {"ok": True, "message": "Connected", "ssid": ssid}


HOTSPOT_CONN_ID = "Minabox-Setup"


@router.post("/wifi/hotspot/start")
def wifi_hotspot_start(
    body: HotspotStartBody | None = None,
    _: None = Depends(_check_api_key),
) -> dict:
    """Start AP (hotspot). Default SSID Minabox-Setup, optional password."""
    ssid = (body.ssid if body else "Minabox-Setup").strip() or "Minabox-Setup"
    password = (body.password if body else "").strip()
    if not password:
        import secrets

        password = secrets.token_hex(4)
    try:
        _run_nmcli_host_network(["con", "delete", HOTSPOT_CONN_ID], timeout=5)
    except Exception:
        pass
    try:
        _run_nmcli_host_network(
            [
                "con",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "autoconnect",
                "no",
                "con-name",
                HOTSPOT_CONN_ID,
                "ssid",
                ssid,
            ],
            timeout=10,
        )
    except HTTPException:
        raise
    _run_nmcli_host_network(
        [
            "con",
            "modify",
            HOTSPOT_CONN_ID,
            "802-11-wireless.mode",
            "ap",
            "ipv4.method",
            "shared",
        ],
        timeout=5,
    )
    _run_nmcli_host_network(
        [
            "con",
            "modify",
            HOTSPOT_CONN_ID,
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk",
            password,
        ],
        timeout=5,
    )
    r = _run_nmcli_host_network(["con", "up", HOTSPOT_CONN_ID], timeout=15)
    if r.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=(r.stderr or r.stdout or "Hotspot start failed")[:500],
        )
    logger.info("wifi_hotspot_started", ssid=ssid)
    return {
        "ok": True,
        "ssid": ssid,
        "password": password,
        "message": "Hotspot started",
    }


@router.post("/wifi/hotspot/stop")
def wifi_hotspot_stop(_: None = Depends(_check_api_key)) -> dict:
    """Stop the hotspot and bring wlan0 back to client mode."""
    try:
        _run_nmcli_host_network(["con", "down", HOTSPOT_CONN_ID], timeout=10)
    except HTTPException:
        raise
    logger.info("wifi_hotspot_stopped")
    return {"ok": True, "message": "Hotspot stopped"}


@router.get("/wifi/hotspot/status")
def wifi_hotspot_status(_: None = Depends(_check_api_key)) -> dict:
    """Return whether the hotspot is currently active."""
    try:
        r = _run_nmcli_host_network(
            ["-t", "-f", "NAME,STATE", "con", "show", "--active"], timeout=5
        )
    except HTTPException:
        return {"active": False, "ssid": None}
    out = (r.stdout or "").strip()
    active = HOTSPOT_CONN_ID in out and "activated" in out.lower()
    return {"active": active, "ssid": HOTSPOT_CONN_ID if active else None}


# ── USB ───────────────────────────────────────────────────────────────────


def _run_lsblk() -> list[dict]:
    """Run lsblk on host (chroot) and return list of block devices (USB-relevant)."""
    root_path = _host_root()
    lsblk_path = _host_tool("usr/bin/lsblk")
    if lsblk_path is None:
        return []
    try:
        r = subprocess.run(
            [
                "chroot",
                str(root_path),
                "lsblk",
                "-J",
                "-o",
                "NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL,TRAN",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if r.returncode != 0:
        return []
    try:
        import json as _json

        data = _json.loads(r.stdout or "{}")
        blockdevices = data.get("blockdevices") or []
    except (ValueError, TypeError):
        return []
    out: list[dict] = []

    def add_dev(dev: dict) -> None:
        name = dev.get("name") or ""
        if not name or name.startswith("loop"):
            return
        children = dev.get("children") or []
        # With partitions, list those (sda1) rather than the raw disk (sda).
        if children:
            for child in children:
                add_dev(child)
            return
        size = dev.get("size") or ""
        fstype = dev.get("fstype") or ""
        mountpoint = dev.get("mountpoint") or ""
        label = dev.get("label") or ""
        out.append(
            {
                "id": name,
                "device": f"/dev/{name}",
                "size": size,
                "fstype": fstype,
                "mountpoint": mountpoint if mountpoint else None,
                "label": label or None,
            }
        )

    for dev in blockdevices:
        if (dev.get("tran") or "").strip().lower() == "usb":
            add_dev(dev)
    return out


@router.get("/usb/devices")
def usb_devices(_: None = Depends(_check_api_key)) -> dict:
    """List USB (and other removable) block devices."""
    devices = _run_lsblk()
    return {"devices": devices}


def _validate_device_id(device_id: str) -> str:
    """A bare block device name such as sda1. Raises HTTPException otherwise.

    The three USB routes each carried their own version of this check and only
    one of them rejected a slash, so the same value was accepted in one place
    and refused in another. The name ends up in /dev/<id>, so it has to be a
    name and nothing else.
    """
    name = (device_id or "").strip()
    if not name or len(name) > 32 or not all(c.isalnum() for c in name):
        raise HTTPException(status_code=400, detail="Invalid device_id")
    return name


def _ignore_symlinks(directory: str, names: list[str]) -> set[str]:
    """copytree filter: never follow a link off the stick.

    The requested names are checked, but their targets come from the device. A
    prepared stick with '../../../etc/shadow' behind a symlink would otherwise
    have its content copied into the audio directory, because the stick is
    mounted under /host and the link resolves against the host tree.
    """
    base = Path(directory)
    return {name for name in names if (base / name).is_symlink()}


class UsbImportBody(BaseModel):
    device_id: str
    source_paths: list[str]


class UsbEjectBody(BaseModel):
    device_id: str


@router.get("/usb/{device_id}/files")
def usb_files(
    device_id: str,
    _: None = Depends(_check_api_key),
) -> dict:
    """List files/dirs on a mounted USB device. device_id e.g. sda1."""
    device_id = _validate_device_id(device_id)
    root_path = _host_root()
    devices = _run_lsblk()
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    mountpoint = dev.get("mountpoint")
    if not mountpoint:
        # Try to mount
        udisks = root_path / "usr/bin/udisksctl"
        if udisks.exists():
            r = subprocess.run(
                [
                    "chroot",
                    str(root_path),
                    "udisksctl",
                    "mount",
                    "-b",
                    f"/dev/{device_id}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0:
                for line in (r.stdout or "").splitlines():
                    if "mounted at" in line:
                        mountpoint = (
                            line.split("mounted at", 1)[1].strip().rstrip(".").strip()
                        )
                        break
            devices = _run_lsblk()
            dev = next((d for d in devices if d.get("id") == device_id), None)
            mountpoint = dev.get("mountpoint") if dev else None
    if not mountpoint:
        raise HTTPException(status_code=400, detail="Device not mounted")
    base = (
        Path(mountpoint)
        if not str(mountpoint).startswith("/")
        else root_path / mountpoint.lstrip("/")
    )
    if not base.exists():
        base = Path(mountpoint)
    entries: list[dict] = []
    try:
        for p in sorted(base.iterdir()):
            rel = p.name
            entries.append(
                {
                    "path": rel,
                    "name": rel,
                    "type": "dir" if p.is_dir() else "file",
                }
            )
    except OSError as e:
        raise HTTPException(status_code=502, detail="Cannot list directory") from e
    return {"path": str(base), "entries": entries}


@router.post("/usb/import")
def usb_import(
    body: UsbImportBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Copy selected paths from USB to AUDIO_STORAGE_PATH."""
    device_id = _validate_device_id(body.device_id)
    cfg = get_config()
    dest_base = cfg.audio_storage_path.resolve()
    root_path = _host_root()
    devices = _run_lsblk()
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    mountpoint = dev.get("mountpoint")
    if not mountpoint:
        raise HTTPException(status_code=400, detail="Device not mounted")
    base = (
        root_path / mountpoint.lstrip("/")
        if mountpoint.startswith("/")
        else Path(mountpoint)
    )
    if not base.exists():
        base = Path(mountpoint)
    base_resolved = base.resolve()
    count = 0
    skipped = 0
    for rel in body.source_paths or []:
        if not rel or ".." in rel or rel.startswith("/"):
            skipped += 1
            continue
        src = base / rel
        # Resolve before use and require the result to still sit on the stick.
        # is_symlink() alone would miss a link somewhere along the path.
        try:
            src = src.resolve()
            src.relative_to(base_resolved)
        except (OSError, ValueError):
            logger.warning("usb_import_outside_device", entry=rel)
            skipped += 1
            continue
        if not src.exists():
            skipped += 1
            continue
        dst = dest_base / Path(rel).name
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_symlinks)
                count += sum(
                    1 for f in src.rglob("*") if f.is_file() and not f.is_symlink()
                )
            else:
                shutil.copy2(src, dst)
                count += 1
        except OSError as e:
            logger.warning("usb_import_copy_failed", src=str(src), error=str(e))
            skipped += 1
    logger.info(
        "usb_import_done", device=device_id, files_copied=count, skipped=skipped
    )
    return {"ok": True, "files_copied": count, "skipped": skipped}


@router.post("/usb/eject")
def usb_eject(
    body: UsbEjectBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Unmount and power-off USB device."""
    device_id = _validate_device_id(body.device_id)
    root_path = _host_root()
    udisks = root_path / "usr/bin/udisksctl"
    if not udisks.exists():
        raise HTTPException(status_code=503, detail="udisksctl not found on host")
    r = subprocess.run(
        ["chroot", str(root_path), "udisksctl", "unmount", "-b", f"/dev/{device_id}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0 and "not mounted" not in (r.stderr or "").lower():
        raise HTTPException(
            status_code=502, detail=(r.stderr or r.stdout or "Unmount failed")[:500]
        )
    subprocess.run(
        ["chroot", str(root_path), "udisksctl", "power-off", "-b", f"/dev/{device_id}"],
        capture_output=True,
        timeout=10,
    )
    return {"ok": True, "message": "Ejected"}


# ── Backup / Restore ───────────────────────────────────────────────────────

# The only entries under data/ that a restore may write. Everything else that
# lives there is runtime state this service owns - the update log, the OS
# update PID file, the pre-update backups, and minabox-update.sh, which the
# host executes as root. A blanket "anything under data/" let an uploaded
# archive drop a file into all of them. Nothing exploitable today, because the
# update script is rewritten before every run, but the allowlist should not be
# what stands between an upload and a root-executed file.
_BACKUP_DATA_FILES = frozenset({"data/minabox.db", "data/general_settings.json"})
_BACKUP_DATA_TREES = ("data/static/",)


def _backup_allowed_path(rel_path: str, workspace: Path) -> bool:
    """Whether a restore may write this archive entry.

    Mirrors what _backup_members() produces: the database and settings by name,
    the static tree by prefix, and per-service state/config. The service
    directories stay a prefix rule so a backup from a box with a different set
    of services still restores.
    """
    p = rel_path.strip().replace("\\", "/").lstrip("/")
    if not p or ".." in p or p.startswith("/"):
        return False
    if p in _BACKUP_DATA_FILES:
        return True
    if any(
        p.startswith(prefix) and len(p) > len(prefix) for prefix in _BACKUP_DATA_TREES
    ):
        return True
    parts = p.split("/")
    return (
        parts[0] == "services"
        and len(parts) >= 4
        and parts[1].endswith("-service")
        and parts[2] in ("state", "config")
    )


def _backup_members(workspace: Path, data_path: Path) -> Iterator[tuple[Path, str]]:
    """The files a backup consists of, as (source on disk, name in archive)."""
    for name in ("minabox.db", "general_settings.json"):
        candidate = data_path / name
        if candidate.is_file():
            yield candidate, f"data/{name}"

    static_dir = data_path / "static"
    if static_dir.is_dir():
        for entry in sorted(static_dir.rglob("*")):
            if entry.is_file():
                yield entry, "data/static/" + entry.relative_to(static_dir).as_posix()

    for rel in (
        "services/audio-service/state/audio_state.json",
        "services/led-service/config/leds.json",
        "services/button-service/config/buttons.json",
        "services/display-service/config/display.json",
    ):
        candidate = workspace / rel
        if candidate.is_file():
            yield candidate, rel


def _write_backup_zip(target: Path) -> None:
    """Write the backup archive - database, settings, static files, service state.

    Extracted so that the same snapshot can be handed to a download and dropped
    on disk before an update; a backup that only exists while someone downloads
    it helps nobody when an update goes wrong.

    Members are streamed with ZipFile.write() rather than read into memory
    first, and the archive goes straight to a file. The cover art under
    data/static/ is what grows here, and holding all of it plus a copy of the
    finished archive is not something a Pi should be asked to do.
    """
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    data_path = cfg.data_path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for source, arcname in _backup_members(workspace, data_path):
            zf.write(source, arcname)


@router.get("/backup/download")
def backup_download(_: None = Depends(_check_api_key)) -> Response:
    """Stream a ZIP of the database, settings, static files and service state."""
    cfg = get_config()
    data_path = cfg.data_path.resolve()
    filename = f"minabox-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.zip"

    data_path.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(data_path), prefix="download-", suffix=".zip"
    )
    os.close(fd)
    archive = Path(tmp_name)
    try:
        _write_backup_zip(archive)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    # Deleted once the response has been sent, whether or not it completed.
    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


# An archive is a few megabytes today. The caps exist so that a corrupt or
# hostile upload cannot fill the SD card or exhaust the RAM of a Pi: the file
# itself is streamed to disk, but every member is read into memory to be
# written, and a small ZIP can otherwise expand without bound.
RESTORE_MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
RESTORE_MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024

# Restore job state, same shape and lifecycle as the move job above.
_restore_state: dict = {"status": "idle", "error": None, "finished_at": None}
_restore_lock = threading.Lock()


def _validate_backup_archive(archive: Path, workspace: Path) -> None:
    """Reject anything that must not be unpacked. Raises HTTPException."""
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            unpacked = 0
            for info in zf.infolist():
                if not _backup_allowed_path(info.filename, workspace):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid path in backup: {info.filename}",
                    )
                unpacked += info.file_size
                if unpacked > RESTORE_MAX_UNPACKED_BYTES:
                    raise HTTPException(
                        status_code=413, detail="Backup expands beyond the size limit"
                    )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None


def _restore_backup_archive(archive: Path, workspace: Path) -> None:
    """Stop the other services, extract the archive, start everything again.

    The host-helper deliberately keeps running throughout. It holds none of the
    restored files, and it is the process doing the work - taking it down with
    the rest would abort the restore halfway through.

    Blocking by nature: minutes of compose plus the extraction. Runs in its own
    thread, started by the endpoint after it has already answered.
    """
    try:
        result = _run_compose_on_others(["stop"], timeout=180)
        if result.returncode != 0:
            # Without the writers stopped the database would be overwritten
            # under an open SQLite connection, which is how a restore turns a
            # working box into a broken one.
            raise RuntimeError(
                (result.stderr or result.stdout or "compose stop failed").strip()[-500:]
            )

        with zipfile.ZipFile(archive, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))

        result = _run_compose_on_host(["up", "-d"], timeout=300)
        if result.returncode != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or "compose up failed").strip()[-500:]
            )
    except Exception as e:
        with _restore_lock:
            _restore_state.update(
                {
                    "status": "error",
                    "error": str(e)[:500],
                    "finished_at": datetime.now(UTC).isoformat(),
                }
            )
        logger.exception("backup_restore_failed")
        # Leave the services running whatever state they are in rather than
        # guessing; a half-restored box that is up can still be reached.
        _run_compose_on_host(["up", "-d"], timeout=300)
        return
    finally:
        archive.unlink(missing_ok=True)

    with _restore_lock:
        _restore_state.update(
            {
                "status": "done",
                "error": None,
                "finished_at": datetime.now(UTC).isoformat(),
            }
        )
    logger.info("backup_restore_done")


@router.post("/backup/restore")
async def backup_restore(
    file: UploadFile = File(...),  # noqa: B008 - the FastAPI idiom for a required upload
    _: None = Depends(_check_api_key),
) -> dict:
    """Upload a backup ZIP and start the restore in the background.

    Answers 202 before anything is stopped. It has to: the restore stops the
    backend, and the backend is the caller - a synchronous reply would be cut
    off on the way out and a successful restore would look like a failure.
    Poll GET /backup/restore-status for the outcome.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip file")
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    data_path = cfg.data_path.resolve()
    if not (workspace / "docker-compose.yml").exists():
        raise HTTPException(status_code=500, detail="docker-compose.yml not found")

    with _restore_lock:
        if _restore_state.get("status") == "running":
            raise HTTPException(status_code=409, detail="Restore already in progress")

    # Spool to disk instead of reading the upload into a bytes object: a backup
    # grows with the cover art, and the Pi has no memory to spare for a copy.
    data_path.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(data_path), prefix="restore-", suffix=".zip"
    )
    archive = Path(tmp_name)
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > RESTORE_MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Backup too large")
                out.write(chunk)
        await asyncio.to_thread(_validate_backup_archive, archive, workspace)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise

    with _restore_lock:
        _restore_state.update({"status": "running", "error": None, "finished_at": None})
    threading.Thread(
        target=_restore_backup_archive, args=(archive, workspace), daemon=True
    ).start()
    logger.info("backup_restore_started", bytes=written)
    return JSONResponse(
        content={"ok": True, "status": "running", "message": "Restore started"},
        status_code=202,
    )


@router.get("/backup/restore-status")
def backup_restore_status(_: None = Depends(_check_api_key)) -> dict:
    """State of the running or last restore (idle | running | done | error)."""
    with _restore_lock:
        return dict(_restore_state)


def _read_host_status(cfg: Config) -> dict:
    """Read host status from mounted /host/proc, /host/etc/hostname, etc."""
    out: dict = {
        "hostname": None,
        "ip": cfg.host_ip,
        "uptime_seconds": None,
        "memory": None,
        "cpu": None,
        "disk": None,
        "temperature_celsius": None,
    }
    host_proc = cfg.host_proc
    host_etc_hostname = cfg.host_etc_hostname
    host_root = cfg.host_root

    # Host uptime from /proc/uptime (seconds since boot)
    try:
        uptime_path = Path(host_proc) / "uptime"
        if uptime_path.exists():
            line = uptime_path.read_text(encoding="utf-8", errors="replace").strip()
            if line:
                out["uptime_seconds"] = int(float(line.split()[0]))
    except (OSError, ValueError):
        pass

    # Hostname
    try:
        p = Path(host_etc_hostname)
        if p.exists():
            out["hostname"] = p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass

    # Memory from /proc/meminfo
    try:
        meminfo = Path(host_proc) / "meminfo"
        if meminfo.exists():
            total_kb = available_kb = None
            for line in meminfo.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                if total_kb is not None and available_kb is not None:
                    break
            if total_kb is not None and total_kb > 0:
                total_mb = total_kb // 1024
                available_mb = (available_kb or 0) // 1024
                used_mb = total_mb - available_mb
                pct = round(100 * used_mb / total_mb) if total_mb else 0
                out["memory"] = {
                    "total_mb": total_mb,
                    "available_mb": available_mb,
                    "percent_used": pct,
                }
    except (OSError, ValueError):
        pass

    # CPU load from /proc/loadavg (1m, 5m, 15m)
    try:
        loadavg = Path(host_proc) / "loadavg"
        if loadavg.exists():
            parts = (
                loadavg.read_text(encoding="utf-8", errors="replace").strip().split()
            )
            load_1m = float(parts[0]) if len(parts) >= 1 else 0.0
            load_5m = float(parts[1]) if len(parts) >= 2 else 0.0
            load_15m = float(parts[2]) if len(parts) >= 3 else 0.0
            out["cpu"] = {
                "load_1m": load_1m,
                "load_5m": load_5m,
                "load_15m": load_15m,
                "percent_used": None,
            }
    except (OSError, ValueError):
        pass

    # Disk from host root mount
    if host_root:
        try:
            st = os.statvfs(host_root)
            total_gb = (st.f_blocks * st.f_frsize) / (1024**3)
            free_gb = (st.f_bfree * st.f_frsize) / (1024**3)
            used_gb = total_gb - free_gb
            pct = round(100 * used_gb / total_gb) if total_gb > 0 else 0
            out["disk"] = {
                "path": host_root,
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "percent_used": pct,
            }
        except OSError:
            pass

    # CPU/SoC temperature (e.g. Raspberry Pi thermal_zone0)
    try:
        if host_root:
            temp_path = (
                Path(host_root) / "sys" / "class" / "thermal" / "thermal_zone0" / "temp"
            )
        else:
            temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            value = temp_path.read_text(encoding="utf-8", errors="replace").strip()
            if value:
                out["temperature_celsius"] = round(int(value) / 1000, 1)
    except (OSError, ValueError):
        pass

    return out


@router.get("/host-status")
def host_status(_: None = Depends(_check_api_key)) -> dict:
    """Return host info (hostname, IP, memory, CPU, disk) from mounted host paths."""
    cfg = get_config()
    return _read_host_status(cfg)


@router.get("/syslog")
def get_syslog(
    n: int = 200,
    source: str = "kernel",  # kernel | docker
    _: None = Depends(_check_api_key),
) -> dict:
    """Return the last N lines of the host kernel or docker unit log.

    The cap is generous on purpose: the debug export filters container-network
    noise out of the kernel log *before* it truncates, so it has to be able to
    ask for a window wide enough to still contain the last boot.
    """
    n = max(1, min(int(n), 20000))
    root_path = _host_root()
    # Run journalctl in host context via chroot so it sees host's journal
    journalctl_path = _host_tool("usr/bin/journalctl")
    if journalctl_path is not None:
        args = [
            "chroot",
            str(root_path),
            "journalctl",
            "-n",
            str(n),
            "--no-pager",
            "-o",
            "short-iso",
        ]
        if source == "docker":
            args.extend(["-u", "docker"])
        else:
            args.extend(["-k"])
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = (result.stdout or "") + (result.stderr or "")
            lines = [s for s in out.strip().splitlines() if s.strip()]
            return {"lines": lines[-n:], "source": source}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("syslog_journalctl_failed", error=str(e))
    # Fallback: read host /var/log/syslog or kern.log
    log_paths = [
        root_path / "var/log/syslog",
        root_path / "var/log/kern.log",
    ]
    lines_list: list[str] = []
    for lp in log_paths:
        if lp.exists() and lp.is_file():
            try:
                content = lp.read_text(encoding="utf-8", errors="replace")
                lines_list = content.strip().splitlines()[-n:]
                break
            except OSError:
                continue
    return {"lines": lines_list, "source": source}


# ── Timezone & Time ───────────────────────────────────────────────────────


class TimezoneBody(BaseModel):
    timezone: str


@router.put("/system/timezone")
def set_timezone(
    body: TimezoneBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set host timezone (e.g. Europe/Berlin). Runs timedatectl via chroot."""
    tz = (body.timezone or "").strip()
    if not tz or ".." in tz or "/" not in tz:
        raise HTTPException(status_code=400, detail="Invalid timezone")
    root_path = _host_root()
    timedatectl_path = root_path / "usr/bin/timedatectl"
    if not timedatectl_path.exists():
        raise HTTPException(status_code=503, detail="timedatectl not found on host")
    try:
        result = subprocess.run(
            ["chroot", str(root_path), "timedatectl", "set-timezone", tz],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=(result.stderr or result.stdout or "Failed to set timezone")[
                    :500
                ],
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("set_timezone_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set timezone") from e
    logger.info("timezone_set", timezone=tz)
    return {"ok": True, "timezone": tz}


@router.get("/system/time-status")
def get_time_status(_: None = Depends(_check_api_key)) -> dict:
    """Return host timezone, NTP sync status, and local time."""
    root_path = _host_root()
    timedatectl_path = root_path / "usr/bin/timedatectl"
    out = {"timezone": None, "ntp_sync": False, "local_time": None}
    if not timedatectl_path.exists():
        return out
    try:
        result = subprocess.run(
            ["chroot", str(root_path), "timedatectl", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = (result.stdout or "") + (result.stderr or "")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("Time zone:"):
                out["timezone"] = line.split(":", 1)[1].strip()
            elif "synchronized: yes" in line.lower():
                out["ntp_sync"] = True
            elif line.startswith("Local time:"):
                out["local_time"] = line.split(":", 1)[1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return out


# ── Hostname ───────────────────────────────────────────────────────────────


class HostnameBody(BaseModel):
    hostname: str


def _read_hostname(cfg: Config) -> str | None:
    """Read current hostname from /host/etc/hostname."""
    path = cfg.host_etc_hostname
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


@router.get("/system/hostname")
def get_hostname(_: None = Depends(_check_api_key)) -> dict:
    """Return current hostname."""
    cfg = get_config()
    return {"hostname": _read_hostname(cfg)}


@router.put("/system/hostname")
def set_hostname(
    body: HostnameBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set host hostname and update /etc/hosts. Requires hostnamectl on host."""
    name = (body.hostname or "").strip().lower()
    if not name or len(name) > 63:
        raise HTTPException(status_code=400, detail="Hostname must be 1-63 characters")
    if not all(c.isalnum() or c == "-" for c in name):
        raise HTTPException(
            status_code=400, detail="Hostname may only contain a-z, 0-9, hyphen"
        )
    root_path = _host_root()
    hostnamectl = _host_tool("usr/bin/hostnamectl")
    if hostnamectl is None:
        raise HTTPException(status_code=503, detail="hostnamectl not found on host")
    old_name = _read_hostname(get_config())
    try:
        r = subprocess.run(
            ["chroot", str(root_path), "hostnamectl", "set-hostname", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            raise HTTPException(
                status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("set_hostname_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set hostname") from e
    hosts_file = root_path / "etc/hosts"
    if hosts_file.exists():
        try:
            content = hosts_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            new_lines = []
            replaced = False
            for line in lines:
                parts = line.split()
                if (
                    len(parts) >= 2
                    and parts[0] == "127.0.1.1"
                    and old_name
                    and parts[1] == old_name
                ):
                    new_lines.append("127.0.1.1\t" + name)
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append("127.0.1.1\t" + name)
            hosts_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError as e:
            logger.warning("hosts_file_update_failed", error=str(e))
    logger.info("hostname_set", hostname=name)
    return {"ok": True, "hostname": name}


# ── Board LEDs (Stealth) ───────────────────────────────────────────────────


def _boot_config_path(root_path: Path) -> Path | None:
    """Return host boot config.txt path for persistent LED/stealth settings."""
    for name in ("boot/firmware/config.txt", "boot/config.txt"):
        p = root_path / name
        if p.exists():
            return p
    return None


def _set_stealth_persistent(root_path: Path, stealth: bool) -> None:
    """Persist the LED triggers in config.txt so stealth survives a reboot."""
    config_path = _boot_config_path(root_path)
    if not config_path:
        return
    try:
        content = config_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        new_lines: list[str] = []
        seen_act = False
        seen_pwr = False
        act_none = "dtparam=act_led_trigger=none"
        pwr_none = "dtparam=pwr_led_trigger=none"
        for line in lines:
            stripped = line.strip()
            if "act_led_trigger" in stripped:
                seen_act = True
                new_lines.append(act_none if stealth else "# " + act_none)
                continue
            if "pwr_led_trigger" in stripped:
                seen_pwr = True
                new_lines.append(pwr_none if stealth else "# " + pwr_none)
                continue
            new_lines.append(line)
        if stealth:
            if not seen_act:
                new_lines.append(act_none)
            if not seen_pwr:
                new_lines.append(pwr_none)
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning("board_leds_config_txt_failed", error=str(e))


def _board_led_paths(root_path: Path) -> tuple[Path | None, Path | None]:
    """The (power, activity) brightness paths. Tries PWR/ACT, then led0/led1."""
    sys_leds = root_path / "sys/class/leds"
    if not sys_leds.exists():
        return (None, None)
    power = activity = None
    for name in ("led1", "PWR", "ACT", "led0"):
        p = sys_leds / name / "brightness"
        if p.exists():
            if name in ("led1", "PWR"):
                power = p
            else:
                activity = p
            if power is not None and activity is not None:
                break
    if power is None and activity is None:
        for d in sys_leds.iterdir():
            if d.is_dir():
                b = d / "brightness"
                if b.exists():
                    if activity is None:
                        activity = b
                    else:
                        power = b
                    break
    return (power, activity)


@router.get("/system/board-leds")
def get_board_leds(_: None = Depends(_check_api_key)) -> dict:
    """Return current board LED state (stealth on/off)."""
    root_path = _host_root()
    power_path, activity_path = _board_led_paths(root_path)
    out = {"stealth": False, "power_led": "on", "activity_led": "on"}
    try:
        if power_path and power_path.exists():
            v = power_path.read_text(encoding="utf-8").strip()
            out["power_led"] = "off" if v == "0" else "on"
        if activity_path and activity_path.exists():
            v = activity_path.read_text(encoding="utf-8").strip()
            out["activity_led"] = "off" if v == "0" else "on"
        out["stealth"] = out["power_led"] == "off" and out["activity_led"] == "off"
    except OSError:
        pass
    return out


class BoardLedsBody(BaseModel):
    stealth: bool


@router.put("/system/board-leds")
def set_board_leds(
    body: BoardLedsBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Switch the board LEDs on or off (stealth mode).

    Written twice: to sysfs for the immediate effect, and to config.txt so it
    survives a reboot.
    """
    root_path = _host_root()
    power_path, activity_path = _board_led_paths(root_path)
    val = "0" if body.stealth else "1"
    try:
        for p in (power_path, activity_path):
            if p and p.exists():
                p.write_text(val, encoding="utf-8")
    except OSError as e:
        logger.warning("board_leds_write_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail="Cannot write to LED brightness"
        ) from e
    _set_stealth_persistent(root_path, body.stealth)
    logger.info("board_leds_set", stealth=body.stealth)
    return {"ok": True, "stealth": body.stealth}


# ── Network (IP config: DHCP / static) ────────────────────────────────────


def _get_active_connection_name() -> str | None:
    """The first active connection that is not the hotspot."""
    try:
        r = _run_nmcli_host_network(
            ["-t", "-f", "NAME", "con", "show", "--active"], timeout=10
        )
        if r.returncode != 0:
            return None
        for line in (r.stdout or "").strip().splitlines():
            name = line.strip()
            if name and name != HOTSPOT_CONN_ID:
                return name
    except (HTTPException, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _parse_ipv4_address(addr: str) -> tuple[str | None, str | None]:
    """Parse '192.168.1.10/24' -> (address, netmask as prefix or dotted)."""
    if not addr or not addr.strip():
        return (None, None)
    addr = addr.strip().split(",")[0].strip()
    if "/" in addr:
        a, prefix = addr.split("/", 1)
        a = a.strip()
        try:
            p = int(prefix.strip())
            if 0 <= p <= 32:
                return (a if a else None, str(p))
        except ValueError:
            pass
        return (a if a else None, None)
    return (addr, None)


@router.get("/system/network")
def get_network(_: None = Depends(_check_api_key)) -> dict:
    """The IPv4 configuration of the active connection."""
    out = {
        "method": "dhcp",
        "address": None,
        "netmask": None,
        "gateway": None,
        "dns": None,
    }
    con_name = _get_active_connection_name()
    if not con_name:
        return out
    try:
        r = _run_nmcli_host_network(
            [
                "-t",
                "-f",
                "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns",
                "con",
                "show",
                con_name,
            ],
            timeout=10,
        )
        if r.returncode != 0:
            return out
        fields = {}
        for line in (r.stdout or "").strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        method = (fields.get("ipv4.method") or "auto").lower()
        out["method"] = "dhcp" if method == "auto" else "manual"
        addr_str = fields.get("ipv4.addresses") or fields.get("IP4.ADDRESS") or ""
        if addr_str:
            a, nm = _parse_ipv4_address(addr_str)
            out["address"] = a
            out["netmask"] = nm
        out["gateway"] = (
            fields.get("ipv4.gateway") or fields.get("IP4.GATEWAY") or ""
        ).strip() or None
        dns = (fields.get("ipv4.dns") or fields.get("IP4.DNS") or "").strip()
        out["dns"] = dns.split(",")[0].strip() if dns else None
    except (HTTPException, subprocess.TimeoutExpired, OSError):
        pass
    return out


class NetworkBody(BaseModel):
    method: str  # "dhcp" | "manual"
    address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    dns: str | None = None


@router.put("/system/network")
def set_network(
    body: NetworkBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Set IPv4 config: DHCP or manual (address, netmask, gateway, dns)."""
    con_name = _get_active_connection_name()
    if not con_name:
        raise HTTPException(
            status_code=503,
            detail="No active connection (use WLAN or connect Ethernet)",
        )
    method = (body.method or "dhcp").strip().lower()
    if method not in ("dhcp", "manual"):
        raise HTTPException(status_code=400, detail="method must be 'dhcp' or 'manual'")
    try:
        # Bring connection down first so the old address/DHCP lease is released;
        # otherwise the interface keeps two addresses, the static and the old
        # DHCP one.
        _run_nmcli_host_network(["con", "down", con_name], timeout=10)
        if method == "dhcp":
            r = _run_nmcli_host_network(
                ["con", "modify", con_name, "ipv4.method", "auto"], timeout=10
            )
            if r.returncode != 0:
                raise HTTPException(
                    status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
                )
        else:
            address = (body.address or "").strip()
            if not address:
                raise HTTPException(
                    status_code=400, detail="address required for manual config"
                )
            prefix = (body.netmask or "24").strip()
            if prefix.isdigit():
                addr_spec = f"{address}/{prefix}"
            else:
                addr_spec = address
            args = [
                "con",
                "modify",
                con_name,
                "ipv4.method",
                "manual",
                "ipv4.addresses",
                addr_spec,
            ]
            if (body.gateway or "").strip():
                args += ["ipv4.gateway", body.gateway.strip()]
            if (body.dns or "").strip():
                args += ["ipv4.dns", body.dns.strip()]
            r = _run_nmcli_host_network(args, timeout=10)
            if r.returncode != 0:
                raise HTTPException(
                    status_code=400, detail=(r.stderr or r.stdout or "Failed")[:500]
                )
        r = _run_nmcli_host_network(["con", "up", con_name], timeout=15)
        if r.returncode != 0:
            raise HTTPException(
                status_code=502, detail=(r.stderr or r.stdout or "Apply failed")[:500]
            )
    except HTTPException:
        raise
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("set_network_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set network") from e
    logger.info("network_set", method=method, connection=con_name)
    return {"ok": True, "method": "dhcp" if method == "dhcp" else "manual"}


# ── System password (chpasswd in chroot) ──────────────────────────────────


def _default_system_user() -> str:
    return get_config().default_user


class PasswordBody(BaseModel):
    username: str
    new_password: str


@router.post("/system/password")
def set_system_password(
    body: PasswordBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Change the system password with chpasswd, writing the host /etc/shadow."""
    username = (body.username or "").strip()
    allowed = _default_system_user()
    if username != allowed:
        raise HTTPException(
            status_code=400, detail=f"Only user '{allowed}' can be changed"
        )
    password = (body.new_password or "").strip()
    if len(password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )
    root_path = _host_root()
    chpasswd_path = _host_tool("usr/sbin/chpasswd")
    if chpasswd_path is None:
        raise HTTPException(status_code=503, detail="chpasswd not found on host")
    try:
        proc = subprocess.run(
            ["chroot", str(root_path), "chpasswd"],
            input=f"{username}:{password}\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise HTTPException(
                status_code=400, detail=(proc.stderr or proc.stdout or "Failed")[:500]
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("set_password_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to set password") from e
    logger.info("password_changed", user=username)
    return {"ok": True, "message": "Password updated"}


# ── Docker prune (on host via nsenter) ───────────────────────────────────────


@router.post("/system/docker-prune")
def docker_prune(_: None = Depends(_check_api_key)) -> dict:
    """Run docker system prune -f on the host. Keeps tagged images and cache."""
    try:
        nsenter_bin = _nsenter_bin()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available (run on host)"
        ) from e
    # With -m we are in the host mount namespace, so this is the host's docker.
    cmd = [
        str(nsenter_bin),
        "-t",
        "1",
        "-n",
        "-m",
        "--",
        "/usr/bin/docker",
        "system",
        "prune",
        "-f",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(status_code=502, detail=(out or "Prune failed")[-1000:])
        lines = [
            ln
            for ln in out.strip().splitlines()
            if "reclaimed" in ln.lower() or "freed" in ln.lower()
        ]
        summary = lines[-1] if lines else out.strip()[-200:] or "Done"
        logger.info("docker_prune_done", summary=summary[:200])
        return {
            "ok": True,
            "message": "Docker cleanup completed",
            "summary": summary[:500],
        }
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Docker prune timed out") from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="Docker not available on host"
        ) from e


# ── SSH Toggle (systemctl on host; host-helper runs with pid=host) ───────────


def _run_host_systemctl(
    args: list[str], timeout: int = 15
) -> subprocess.CompletedProcess:
    """Run systemctl on the host via chroot. Requires pid=host."""
    host_root = str(_host_root())
    systemctl_path = Path(host_root) / "usr" / "bin" / "systemctl"
    if not systemctl_path.exists():
        systemctl_path = Path(host_root) / "bin" / "systemctl"
    path_in_chroot = (
        ("/" + str(systemctl_path.relative_to(host_root)))
        if systemctl_path.exists()
        else "/usr/bin/systemctl"
    )
    cmd = ["chroot", host_root, path_in_chroot] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


@router.get("/system/ssh-status")
def get_ssh_status(_: None = Depends(_check_api_key)) -> dict:
    """Return whether SSH is enabled and active on the host."""
    out = {"enabled": False, "active": False}
    try:
        r = _run_host_systemctl(["is-enabled", "ssh"], timeout=5)
        r2 = _run_host_systemctl(["is-active", "ssh"], timeout=5)
        enabled_out = (r.stdout or "").strip().lower()
        active_out = (r2.stdout or "").strip().lower()
        out["enabled"] = enabled_out in ("enabled", "enabled-runtime", "indirect")
        out["active"] = active_out in ("active", "activating")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return out


# systemctl answers in well under a second on the box. The generous cap is for
# a systemd that hangs, and it is deliberately small enough that four chained
# calls cannot occupy a worker thread for minutes on end.
SSH_UNIT_TIMEOUT = 30


class SshToggleBody(BaseModel):
    enable: bool


@router.post("/system/ssh-toggle")
def ssh_toggle(
    body: SshToggleBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Enable or disable SSH on the host (systemctl enable/disable, start/stop)."""
    try:
        if body.enable:
            for args in (["enable", "ssh"], ["start", "ssh"]):
                r = _run_host_systemctl(args, timeout=SSH_UNIT_TIMEOUT)
                if r.returncode != 0:
                    raise HTTPException(
                        status_code=502, detail=(r.stderr or r.stdout or "Failed")[:500]
                    )
        else:
            # The socket first: otherwise socket activation brings SSH back.
            for unit in ("ssh.socket", "ssh"):
                for args in (["stop", unit], ["disable", unit]):
                    r = _run_host_systemctl(args, timeout=SSH_UNIT_TIMEOUT)
                    if r.returncode != 0 and unit == "ssh":
                        raise HTTPException(
                            status_code=502,
                            detail=(r.stderr or r.stdout or "Failed")[:500],
                        )
        r_en = _run_host_systemctl(["is-enabled", "ssh"], timeout=5)
        r_ac = _run_host_systemctl(["is-active", "ssh"], timeout=5)
        enabled_out = (r_en.stdout or "").strip().lower()
        active_out = (r_ac.stdout or "").strip().lower()
        enabled = enabled_out in ("enabled", "enabled-runtime", "indirect")
        active = active_out in ("active", "activating")
        logger.info("ssh_toggled", enable=body.enable)
        return {"ok": True, "enabled": enabled, "active": active}
    except HTTPException:
        raise
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("ssh_toggle_failed", error=str(e))
        detail = f"Failed to toggle SSH: {e!s}"[:500]
        raise HTTPException(status_code=500, detail=detail) from e


# ── Factory Reset ──────────────────────────────────────────────────────────


class FactoryResetBody(BaseModel):
    delete_audio: bool = False


@router.post("/system/factory-reset")
def factory_reset(
    body: FactoryResetBody | None = None,
    _: None = Depends(_check_api_key),
) -> dict:
    """Reset DB, configs, optionally clear audio; start hotspot; restart containers."""
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    data_path = cfg.data_path.resolve()
    audio_storage_path = Path(cfg.audio_storage_path).resolve()
    compose_file = workspace / "docker-compose.yml"

    # 1) Delete DB
    db_file = data_path / "minabox.db"
    if db_file.exists():
        try:
            db_file.unlink()
        except OSError as e:
            logger.warning("factory_reset_db_unlink_failed", error=str(e))

    # 2) Reset general_settings.json
    gs_file = data_path / "general_settings.json"
    try:
        gs_file.parent.mkdir(parents=True, exist_ok=True)
        gs_file.write_text("{}", encoding="utf-8")
    except OSError as e:
        logger.warning("factory_reset_gs_failed", error=str(e))

    # 3) Reset audio_state.json
    audio_state = workspace / "services/audio-service/state/audio_state.json"
    if audio_state.exists() or audio_state.parent.exists():
        try:
            audio_state.parent.mkdir(parents=True, exist_ok=True)
            audio_state.write_text("{}", encoding="utf-8")
        except OSError as e:
            logger.warning("factory_reset_audio_state_failed", error=str(e))

    # 4) Optional: clear audio storage (only if under allowed base)
    if body and body.delete_audio and audio_storage_path.exists():
        allowed_bases = [Path(b).resolve() for b in cfg.allowed_base_paths]
        allowed_bases.append(workspace)
        try:
            for base in allowed_bases:
                try:
                    audio_storage_path.relative_to(base)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Audio path not under allowed base")
            for child in list(audio_storage_path.iterdir()):
                try:
                    if child.is_file():
                        child.unlink()
                    else:
                        shutil.rmtree(child, ignore_errors=True)
                except OSError as e:
                    logger.warning(
                        "factory_reset_audio_delete_failed",
                        path=str(child),
                        error=str(e),
                    )
        except (ValueError, OSError) as e:
            logger.warning("factory_reset_audio_clear_skipped", error=str(e))

    # 5) Start hotspot so box is reachable in setup mode
    try:
        _run_nmcli_host_network(["con", "down", HOTSPOT_CONN_ID], timeout=5)
    except Exception:
        pass
    try:
        _run_nmcli_host_network(["con", "delete", HOTSPOT_CONN_ID], timeout=5)
    except Exception:
        pass
    try:
        import secrets

        hotspot_pwd = secrets.token_hex(4)
        _run_nmcli_host_network(
            [
                "con",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "autoconnect",
                "no",
                "con-name",
                HOTSPOT_CONN_ID,
                "ssid",
                "Minabox-Setup",
            ],
            timeout=10,
        )
        _run_nmcli_host_network(
            [
                "con",
                "modify",
                HOTSPOT_CONN_ID,
                "802-11-wireless.mode",
                "ap",
                "ipv4.method",
                "shared",
            ],
            timeout=5,
        )
        _run_nmcli_host_network(
            [
                "con",
                "modify",
                HOTSPOT_CONN_ID,
                "wifi-sec.key-mgmt",
                "wpa-psk",
                "wifi-sec.psk",
                hotspot_pwd,
            ],
            timeout=5,
        )
        _run_nmcli_host_network(["con", "up", HOTSPOT_CONN_ID], timeout=15)
    except (HTTPException, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("factory_reset_hotspot_failed", error=str(e))

    # 6) Restart containers so DB/config are reloaded. Runs on the host and
    #    skips this service: restarting ourselves would cut the reply off.
    if compose_file.exists():
        try:
            result = _run_compose_on_others(["restart"], timeout=180)
            if result.returncode != 0:
                logger.warning(
                    "factory_reset_restart_failed",
                    error=(result.stderr or result.stdout or "").strip()[-500:],
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("factory_reset_restart_failed", error=str(e))

    logger.info("factory_reset_done", delete_audio=body.delete_audio if body else False)
    return {
        "ok": True,
        "message": "Factory reset complete. Reconnect via hotspot (Minabox-Setup).",
    }


# ── Minabox Update & Version ──────────────────────────────────────────────

# The update runs as a transient systemd unit on the HOST, not as a child of
# this container. Two reasons:
#
#   1. "docker compose up -d" recreates the host-helper as soon as its own
#      image has changed. A child process of this container would die with it,
#      halfway through the update.
#   2. There is no Docker CLI inside the container; the host has one.
#
# Progress is written to the log as markers. That survives any restart of the
# host-helper, because the file lives in the project directory.
#
# The step keys below are part of the contract: the WebUI translates them as
# system.update_step_<key>. Do not rename them.
UPDATE_UNIT = "minabox-update"
UPDATE_STEPS = ("backup", "repo", "pull", "restart", "verify")

# How many pre-update backups to keep. Five is enough to survive an update
# that went wrong without filling up the SD card.
BACKUP_KEEP = 5

UPDATE_SCRIPT = """#!/bin/sh
# Generated by the host-helper (see host_helper/api/routes.py). Do not edit by
# hand - this file is overwritten on every update.
exec >>"{log}" 2>&1
cd "{workspace}" || {{
  echo "Working directory {workspace} not found"
  echo "=== MINABOX-DONE 1"
  exit 1
}}

rc=0
SERVICES="{services}"

echo "=== MINABOX-STEP 2/5 repo"
# git runs as the owner of the project directory, not as root. Otherwise it
# would leave root-owned files behind in .git and the user could no longer
# work in their own tree.
#
# Deliberately not fatal: a box with local changes, or without access to the
# git remote, must still be able to update its images.
OWNER="$(stat -c %U .)"
if [ -n "$OWNER" ] && [ "$OWNER" != "UNKNOWN" ]; then
  runuser -u "$OWNER" -- git pull --ff-only \
    || echo "(git pull not possible - updating the images anyway)"
else
  echo "(cannot determine the owner of the project directory - skipping git pull)"
fi

echo "=== MINABOX-STEP 3/5 pull"
# An empty service list means all of them - that is the "everything to the
# newest build" path.
docker compose pull $SERVICES || rc=$?

if [ "$rc" = "0" ]; then
  echo "=== MINABOX-STEP 4/5 restart"
  docker compose up -d $SERVICES || rc=$?
fi

if [ "$rc" = "0" ]; then
  echo "=== MINABOX-STEP 5/5 verify"
  # Not just "is running" but "is running the version we asked for": a
  # container compose did not recreate looks healthy while still executing
  # the old build.
  for entry in {expected}; do
    name="${{entry%%=*}}"
    want="${{entry#*=}}"
    got="$(docker inspect --format '{{{{ index .Config.Labels "org.opencontainers.image.version" }}}}' "minabox-$name" 2>/dev/null)"
    if [ "$got" = "$want" ]; then
      echo "  $name: $got"
    else
      echo "  $name: expected $want, running $got"
      rc=1
    fi
  done
fi

echo "=== MINABOX-DONE $rc"
"""


class UpdateTargetsBody(BaseModel):
    """Target version per service. Empty means: everything to the newest build."""

    targets: dict[str, str] | None = None
    backup: bool = True


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


def _update_paths() -> tuple[Path, Path, Path, str]:
    """(log, script, state file) inside the container, plus the log path on the host."""
    cfg = get_config()
    data_path = cfg.data_path.resolve()
    host_workspace = _host_workspace()
    return (
        data_path / "minabox-update.log",
        data_path / "minabox-update.sh",
        data_path / "minabox-update-state.json",
        f"{host_workspace}/data/minabox-update.log",
    )


def _service_names() -> list[str]:
    """The services this project knows, derived from the VERSION files on disk."""
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    return sorted(
        p.parent.name.removesuffix("-service")
        for p in (workspace / "services").glob("*-service/VERSION")
    )


def _tag_var(service: str) -> str:
    return f"MINABOX_{service.upper().replace('-', '_')}_TAG"


def _running_versions() -> dict[str, str]:
    """The running version per service, read from the container label."""
    versions: dict[str, str] = {}
    try:
        client = _docker()
    except Exception as e:
        _drop_docker_client()
        logger.debug("running_versions_unavailable", error=str(e))
        return versions
    for service in _service_names():
        try:
            container = client.containers.get(f"minabox-{service}")
            version = (container.labels or {}).get("org.opencontainers.image.version")
            if version:
                versions[service] = version
        except Exception:
            continue
    return versions


def _read_env_tags(env_path: Path) -> dict[str, str]:
    """The image tags currently pinned in .env, per service."""
    tags: dict[str, str] = {}
    if not env_path.exists():
        return tags
    try:
        content = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return tags
    wanted = {_tag_var(service): service for service in _service_names()}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        service = wanted.get(key.strip())
        if service and value.strip():
            tags[service] = value.strip()
    return tags


def _write_env_tags(env_path: Path, tags: dict[str, str]) -> None:
    """Set or append the tag lines in .env; everything else stays untouched."""
    content = (
        env_path.read_text(encoding="utf-8", errors="replace")
        if env_path.exists()
        else ""
    )
    lines = content.splitlines()
    for service, version in sorted(tags.items()):
        new_line = f"{_tag_var(service)}={version}"
        prefix = f"{_tag_var(service)}="
        for i, line in enumerate(lines):
            if line.strip().startswith(prefix):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
    env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _prune_backups(backup_dir: Path) -> None:
    files = sorted(
        backup_dir.glob("pre-update-*.zip"), key=lambda p: p.name, reverse=True
    )
    for old in files[BACKUP_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass


def _update_unit_active() -> bool:
    try:
        result = _run_on_host_via_nsenter(
            ["systemctl", "is-active", f"{UPDATE_UNIT}.service"], timeout=10
        )
        return result.stdout.strip() == "active"
    except Exception as e:
        logger.debug("update_unit_state_failed", error=str(e))
        return False


def _parse_update_log(text: str) -> dict:
    """Read the current step and the result from the markers in the log."""
    step: int | None = None
    step_count = len(UPDATE_STEPS)
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


@router.post("/system/update-minabox")
def update_minabox(
    body: UpdateTargetsBody | None = None,
    _: None = Depends(_check_api_key),
) -> dict:
    """Start the update in the background.

    With `targets`, exactly the named services go to exactly the named
    versions, and every other service is pinned to the version it currently
    runs so a targeted update cannot drag anything else along. Without
    `targets`, everything goes to the newest published build.
    """
    log_path, script_path, state_path, host_log = _update_paths()
    host_workspace = _host_workspace()
    cfg = get_config()
    env_path = cfg.env_file_path

    if _update_unit_active():
        raise HTTPException(status_code=409, detail="An update is already running")

    targets = dict((body.targets or {}) if body else {})
    known = set(_service_names())
    unknown = sorted(set(targets) - known)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown services: {', '.join(unknown)}"
        )
    for service, version in targets.items():
        if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,63}", version or ""):
            raise HTTPException(
                status_code=400, detail=f"Invalid version for {service}"
            )

    running = _running_versions()
    previous = {**running, **_read_env_tags(env_path)}

    log_lines = ["=== MINABOX-STEP 1/5 backup"]
    if body is None or body.backup:
        try:
            backup_dir = cfg.data_path
            backup_dir = backup_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            backup_file = backup_dir / f"pre-update-{stamp}.zip"
            _write_backup_zip(backup_file)
            _prune_backups(backup_dir)
            log_lines.append(f"  Backup: data/backups/{backup_file.name}")
        except Exception as e:
            # No backup, no update. Without one the way back would be
            # nothing but hope.
            raise HTTPException(status_code=503, detail=f"Backup failed: {e}") from e
    else:
        log_lines.append("  (skipped)")

    if targets:
        # Pin every other service to what it currently runs. Without that,
        # "compose up -d" would drag them all to latest on the next run and a
        # targeted update would not be one.
        pinned = {**running, **targets}
        services = " ".join(sorted(targets))
        expected = {service: targets[service] for service in targets}
    else:
        pinned = {}
        services = ""
        expected = {}

    try:
        if pinned:
            _write_env_tags(env_path, pinned)
            log_lines.append(
                "  Pinned: " + ", ".join(f"{k}={v}" for k, v in sorted(pinned.items()))
            )
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            UPDATE_SCRIPT.format(
                log=host_log,
                workspace=host_workspace,
                services=services,
                expected=" ".join(f"{k}={v}" for k, v in sorted(expected.items())),
            ),
            encoding="utf-8",
        )
        script_path.chmod(0o755)
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        state_path.write_text(
            json.dumps(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "previous": previous,
                    "targets": targets,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        raise HTTPException(
            status_code=503, detail=f"Could not prepare the update: {e}"
        ) from e

    host_script = f"{host_workspace}/data/minabox-update.sh"
    try:
        result = _run_on_host_via_nsenter(
            [
                "systemd-run",
                f"--unit={UPDATE_UNIT}",
                "--collect",
                "--description=Minabox update",
                "/bin/sh",
                host_script,
            ],
            timeout=30,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Could not start the update: {e}"
        ) from e

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "systemd-run failed")[-500:]
        raise HTTPException(status_code=503, detail=detail)

    logger.info("update_minabox_started", targets=targets or "all")
    return {"ok": True, "message": "Update started", "steps": list(UPDATE_STEPS)}


@router.get("/system/update-minabox/status")
def update_minabox_status(_: None = Depends(_check_api_key)) -> dict:
    """Progress and output of the running or last update."""
    log_path, _script, state_path, _host_log = _update_paths()

    log_text = ""
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > 2000:
                lines = lines[-2000:]
            log_text = "\n".join(lines)
        except OSError:
            pass

    parsed = _parse_update_log(log_text)
    # The unit is the truth about "still running". Without asking it, a run
    # that was killed before writing its closing marker would count as running
    # forever.
    running = parsed["exit_code"] is None and _update_unit_active()

    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}

    # "previous" stays in the state file: for a support request, "what was
    # running before" is the first question. It is not offered as an action -
    # stepping back to an older build can leave data behind that the older
    # build cannot read.
    return {
        "running": running,
        "steps": list(UPDATE_STEPS),
        "log": log_text,
        "targets": state.get("targets") or {},
        **parsed,
    }


@router.get("/system/version")
def get_version(_: None = Depends(_check_api_key)) -> dict:
    """Return the commit the project directory sits on.

    `update_available` is always False here. Whether a newer *image* exists is
    a different question from whether the git worktree is behind origin/main -
    a box can be git-current and still run last week's containers. The backend
    answers it properly against the registry (core/update_check.py); this route
    keeps the field only so its response shape stays stable.
    """
    cfg = get_config()
    workspace = cfg.workspace_path.resolve()
    current_commit: str | None = None
    ref_file = workspace / ".git/refs/heads/main"
    if ref_file.exists():
        try:
            current_commit = ref_file.read_text(encoding="utf-8").strip()[:12]
        except OSError:
            pass
    if not current_commit and (workspace / ".git/HEAD").exists():
        try:
            head = (workspace / ".git/HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref: "):
                ref_path = workspace / ".git" / head[5:].strip()
                if ref_path.exists():
                    current_commit = ref_path.read_text(encoding="utf-8").strip()[:12]
        except OSError:
            pass
    return {
        "current_version": current_commit or "unknown",
        "current_commit": current_commit,
        "update_available": False,
    }


def _os_update_running(pid_path: Path) -> bool:
    """True while the apt process from an earlier call is still alive.

    The container shares the host PID namespace (pid: host in compose), so the
    recorded PID is visible here and signal 0 is enough to ask about it.
    """
    if not pid_path.exists():
        return False
    try:
        os.kill(int(pid_path.read_text(encoding="utf-8").strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def _os_update_wait_and_finish(
    proc: subprocess.Popen, log_path: Path, pid_path: Path
) -> None:
    """Wait for apt, append its exit code to the log, drop the PID file."""
    try:
        proc.wait(timeout=3600)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- Exit code: {code} ---\n")
    except OSError:
        pass
    try:
        pid_path.unlink(missing_ok=True)
    except OSError:
        pass


@router.post("/system/update-os")
def update_os(_: None = Depends(_check_api_key)) -> dict:
    """Start the host OS upgrade in the background and return immediately."""
    cfg = get_config()
    data_path = cfg.data_path.resolve()
    log_path = data_path / "os-update.log"
    pid_path = data_path / "os-update.pid"
    # Two apt processes only ever fight over the dpkg lock, and the second one
    # would overwrite the log the first is still writing.
    if _os_update_running(pid_path):
        raise HTTPException(status_code=409, detail="An OS update is already running")
    if _host_tool("usr/bin/apt-get") is None:
        raise HTTPException(status_code=503, detail="apt-get not found on host")
    try:
        nsenter = _nsenter_bin()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available on host"
        ) from e
    cmd = [
        # /bin/sh is resolved in the host's mount namespace, after nsenter.
        str(nsenter),
        "-t",
        "1",
        "-n",
        "-m",
        "--",
        "/bin/sh",
        "-c",
        "export DEBIAN_FRONTEND=noninteractive PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
        "apt-get update -qq && apt-get upgrade -y",
    ]
    try:
        data_path.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        t = threading.Thread(
            target=_os_update_wait_and_finish,
            args=(proc, log_path, pid_path),
            daemon=True,
        )
        t.start()
        logger.info("update_os_started", pid=proc.pid)
        return {
            "ok": True,
            "message": "OS update started in background (may take several minutes)",
        }
    except OSError as e:
        raise HTTPException(
            status_code=503, detail=f"Host OS update failed: {e}"
        ) from e


@router.get("/system/update-os/log")
def update_os_log(_: None = Depends(_check_api_key)) -> dict:
    """Return current OS update log and whether the process is still running."""
    cfg = get_config()
    data_path = cfg.data_path.resolve()
    log_path = data_path / "os-update.log"
    pid_path = data_path / "os-update.pid"
    running = _os_update_running(pid_path)
    log_text = ""
    if log_path.exists():
        try:
            raw = log_path.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            if len(lines) > 2000:
                lines = lines[-2000:]
            log_text = "\n".join(lines)
        except OSError:
            pass
    return {"running": running, "log": log_text}


# ── Bluetooth ─────────────────────────────────────────────────────────────


def _run_bluetoothctl_on_host(
    args: list[str], timeout: int = 15
) -> subprocess.CompletedProcess:
    """Run bluetoothctl on the host, where the Bluetooth management socket is."""
    nsenter_bin = _nsenter_bin()
    # /usr/bin/bluetoothctl is resolved in the host's mount namespace after nsenter
    cmd = [
        str(nsenter_bin),
        "-t",
        "1",
        "-m",
        "-n",
        "--",
        "/usr/bin/bluetoothctl",
    ] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class BluetoothPairBody(BaseModel):
    address: str


@router.get("/bluetooth/scan")
async def bluetooth_scan(_: None = Depends(_check_api_key)) -> dict:
    """Scan for Bluetooth devices and return their address and name.

    One bluetoothctl process is kept alive for the whole 12 seconds. On most
    setups discovery stops the moment the client disconnects, so running
    "scan on" with a timeout would end the scan before anything is listed.
    """
    # Power the adapter on first: a box driven only from the WebUI has never
    # had bluetoothctl run on it, and BlueZ answers NotReady.
    try:
        _run_bluetoothctl_on_host(["power", "on"], timeout=5)
    except Exception:
        pass
    # Keep one client alive so discovery stays active for the full window.
    nsenter_bin = _nsenter_bin()
    cmd_bt = [str(nsenter_bin), "-t", "1", "-m", "-n", "--", "/usr/bin/bluetoothctl"]
    proc = None
    devices: list[dict] = []
    stdout_lines: list[str] = []

    def read_stdout() -> None:
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            stdout_lines.append(line.rstrip("\n\r"))

    try:
        proc = subprocess.Popen(
            cmd_bt,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        proc.stdin.write("power on\n")
        proc.stdin.write("scan on\n")
        proc.stdin.flush()
        await asyncio.sleep(12)
        proc.stdin.write("devices\n")
        proc.stdin.write("scan off\n")
        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.stdin.close()
        try:
            await asyncio.to_thread(proc.wait, 5)
        except subprocess.TimeoutExpired:
            proc.kill()
        await asyncio.to_thread(reader.join, 2)
        for line in stdout_lines:
            if line.startswith("Device "):
                parts = line[7:].strip().split(" ", 1)
                addr = parts[0] if parts else ""
                name = parts[1].strip() if len(parts) > 1 else ""
                if addr:
                    devices.append({"address": addr, "name": name or None})
    except FileNotFoundError:
        return {"devices": []}
    except Exception:
        return {"devices": []}
    return {"devices": devices}


@router.post("/bluetooth/pair")
def bluetooth_pair(
    body: BluetoothPairBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Pair with a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_pair_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["pair", addr], timeout=30)
    except HTTPException:
        raise
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_pair_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth pairing unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Pairing failed").strip()
        logger.warning(
            "bluetooth_pair_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    # Trust so the device can connect automatically when in range
    try:
        _run_bluetoothctl_on_host(["trust", addr], timeout=10)
    except Exception:
        pass
    logger.info("bluetooth_pair_ok", address=addr)
    return {"ok": True, "message": "Paired", "address": addr}


def _parse_bluetooth_devices(output: str) -> dict[str, str | None]:
    """Turn `bluetoothctl devices` output into {address: name}."""
    devices: dict[str, str | None] = {}
    for line in (output or "").strip().splitlines():
        if not line.startswith("Device "):
            continue
        address, _, name = line[len("Device ") :].strip().partition(" ")
        if address:
            devices[address] = name.strip() or None
    return devices


@router.get("/bluetooth/paired")
def bluetooth_paired(_: None = Depends(_check_api_key)) -> dict:
    """Return the paired devices (address, name, connected). No scan.

    Two fixed calls, not one per device. Asking `bluetoothctl info <addr>` for
    every entry used to cost up to five seconds each, so a box with a handful
    of remembered headphones answered slower than the WebUI was willing to
    wait. BlueZ filters the list itself.
    """
    try:
        paired = _run_bluetoothctl_on_host(["devices", "Paired"], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"devices": []}
    if paired.returncode != 0:
        return {"devices": []}

    connected_addresses: set[str] = set()
    try:
        connected = _run_bluetoothctl_on_host(["devices", "Connected"], timeout=10)
        if connected.returncode == 0:
            connected_addresses = set(_parse_bluetooth_devices(connected.stdout))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Knowing the pairs matters more than knowing which one is live.
        pass

    return {
        "devices": [
            {
                "address": address,
                "name": name,
                "connected": address in connected_addresses,
            }
            for address, name in _parse_bluetooth_devices(paired.stdout).items()
        ]
    }


class BluetoothAddressBody(BaseModel):
    address: str


@router.post("/bluetooth/connect")
def bluetooth_connect(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Connect to a paired Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_connect_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["connect", addr], timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_connect_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth connect unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Connect failed").strip()
        logger.warning(
            "bluetooth_connect_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_connect_ok", address=addr)
    return {"ok": True, "message": "Connected", "address": addr}


@router.post("/bluetooth/disconnect")
def bluetooth_disconnect(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Disconnect a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_disconnect_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["disconnect", addr], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_disconnect_error",
            address=addr,
            error=type(e).__name__,
            msg=str(e),
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth disconnect unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Disconnect failed").strip()
        logger.warning(
            "bluetooth_disconnect_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_disconnect_ok", address=addr)
    return {"ok": True, "message": "Disconnected", "address": addr}


@router.post("/bluetooth/remove")
def bluetooth_remove(
    body: BluetoothAddressBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Remove (unpair) a Bluetooth device by address."""
    addr = (body.address or "").strip()
    if not addr or ".." in addr:
        raise HTTPException(status_code=400, detail="Address required")
    logger.info("bluetooth_remove_start", address=addr)
    try:
        r = _run_bluetoothctl_on_host(["remove", addr], timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(
            "bluetooth_remove_error", address=addr, error=type(e).__name__, msg=str(e)
        )
        raise HTTPException(
            status_code=503, detail="Bluetooth remove unavailable or timed out"
        ) from e
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Remove failed").strip()
        logger.warning(
            "bluetooth_remove_failed",
            address=addr,
            returncode=r.returncode,
            stderr=(r.stderr or "")[:300],
            stdout=(r.stdout or "")[:300],
        )
        raise HTTPException(status_code=400, detail=err[:500])
    logger.info("bluetooth_remove_ok", address=addr)
    return {"ok": True, "message": "Removed", "address": addr}


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
