"""FastAPI routes for Host-Helper: health, apply-audio-path, move, host-status, reboot."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from host_helper.config import load_config, validate_path_under_allowed

logger = structlog.get_logger(__name__)

router = APIRouter()

_config: dict | None = None

# Move job state for progress (idle | running | done | error)
_move_state: dict = {"status": "idle", "total": 0, "current": 0, "error": None}
_move_lock = threading.Lock()


class ApplyAudioPathBody(BaseModel):
    audio_files_path: str


class MoveBody(BaseModel):
    source: str
    destination: str


def get_config() -> dict:
    if _config is None:
        raise RuntimeError("Config not loaded")
    return _config


def set_config(cfg: dict) -> None:
    global _config
    _config = cfg


def _check_api_key(x_api_key: str | None = Header(None, alias="X-Api-Key")) -> None:
    if not x_api_key or x_api_key.strip() != get_config()["api_key"].strip():
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _host_path_to_container(path_str: str, host_root: str) -> Path:
    """Convert host-absolute path to path inside container (host is mounted at host_root)."""
    p = path_str.strip()
    if not p.startswith("/"):
        return Path(p)
    if not host_root:
        return Path(p).resolve()
    return (Path(host_root) / p.lstrip("/")).resolve()


def _validate_host_path_under_allowed(path_str: str, allowed_base_paths: list[str], host_root: str) -> Path:
    """Resolve path (optionally under host_root) and ensure it is under one of the allowed base paths."""
    if not path_str or ".." in path_str:
        raise ValueError("Invalid path")
    container_path = _host_path_to_container(path_str, host_root)
    if not container_path.is_absolute():
        raise ValueError("Path must be absolute")
    allowed = [Path(host_root) / b.lstrip("/") if host_root else Path(b) for b in allowed_base_paths]
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
    return {"status": "ok", "service": "host-helper"}


@router.get("/audio-path")
async def get_audio_path(_: None = Depends(_check_api_key)) -> dict:
    """Read AUDIO_FILES_PATH from .env (saved value for next start)."""
    cfg = get_config()
    env_path: Path = cfg["env_file_path"]
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
async def apply_audio_path(
    body: ApplyAudioPathBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Update only AUDIO_FILES_PATH in the .env file."""
    path_str = body.audio_files_path.strip()
    if not path_str:
        raise HTTPException(status_code=400, detail="audio_files_path required")
    cfg = get_config()
    env_path: Path = cfg["env_file_path"]
    allowed = cfg["allowed_base_paths"]
    logger.info("apply_audio_path_requested", path=path_str)

    try:
        validate_path_under_allowed(path_str, allowed)
    except ValueError as e:
        logger.warning("apply_audio_path_validation_failed", path=path_str, error=str(e))
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
        env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError as e:
        logger.error("env_file_write_failed", path=str(env_path), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to write env file") from e

    logger.info("apply_audio_path_ok", audio_files_path=path_str, env_path=str(env_path))
    return {"ok": True, "audio_files_path": path_str}


def _run_move(source: Path, dest: Path, items: list[Path] | None = None) -> None:
    """Background: move items (or source contents) into dest. When items is set, total is already in _move_state."""
    global _move_state
    # #region agent log
    try:
        import json
        with open("/workspace/.cursor/debug-36e3b3.log", "a") as _f:
            _f.write(json.dumps({"sessionId": "36e3b3", "hypothesisId": "H3", "location": "routes.py:_run_move", "message": "thread_entered", "data": {"source": str(source), "dest": str(dest), "items_len": len(items) if items else None}, "timestamp": __import__("time").time() * 1000}) + "\n")
    except Exception:
        pass
    # #endregion
    try:
        if items is not None:
            total = len(items)
            for i, file_path in enumerate(items):
                try:
                    rel = file_path.relative_to(source)
                    dest_file = dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file_path), str(dest_file))
                except OSError as e:
                    with _move_lock:
                        _move_state = {"status": "error", "total": total, "current": i, "error": str(e)}
                    logger.error("move_failed", source=str(source), dest=str(dest), error=str(e))
                    return
                with _move_lock:
                    _move_state["current"] = i + 1
            # Remove empty directories left in source (repeat until none left)
            try:
                while True:
                    removed = False
                    for p in sorted(source.rglob("*"), key=lambda x: -len(x.parts)):
                        if p.is_dir() and not any(p.iterdir()):
                            p.rmdir()
                            removed = True
                    if not removed:
                        break
            except OSError as e:
                logger.warning("move_cleanup_dirs_failed", path=str(source), error=str(e))
            with _move_lock:
                _move_state["status"] = "done"
            # #region agent log
            try:
                import json
                with open("/workspace/.cursor/debug-36e3b3.log", "a") as _f:
                    _f.write(json.dumps({"sessionId": "36e3b3", "hypothesisId": "H2", "location": "routes.py:_run_move", "message": "move_done", "data": {"total": total}, "timestamp": __import__("time").time() * 1000}) + "\n")
            except Exception:
                pass
            # #endregion
            logger.info("move_ok", source=str(source), destination=str(dest), files_moved=total)
            return
        with _move_lock:
            if _move_state.get("status") == "running":
                return
            _move_state = {"status": "running", "total": 0, "current": 0, "error": None}
        if source.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
            with _move_lock:
                _move_state = {"status": "done", "total": 1, "current": 1, "error": None}
            logger.info("move_ok", source=str(source), destination=str(dest))
            return
        dest.mkdir(parents=True, exist_ok=True)
        dir_items = list(source.iterdir())
        total = len(dir_items)
        with _move_lock:
            _move_state["total"] = total
        for i, item in enumerate(dir_items):
            try:
                shutil.move(str(item), str(dest / item.name))
            except OSError as e:
                with _move_lock:
                    _move_state = {"status": "error", "total": total, "current": i, "error": str(e)}
                logger.error("move_failed", source=str(source), dest=str(dest), error=str(e))
                return
            with _move_lock:
                _move_state["current"] = i + 1
        with _move_lock:
            _move_state["status"] = "done"
        logger.info("move_ok", source=str(source), destination=str(dest))
    except Exception as e:
        with _move_lock:
            _move_state = {"status": "error", "total": 0, "current": 0, "error": str(e)}
        logger.exception("move_failed")


@router.post("/move")
async def move(
    body: MoveBody,
    _: None = Depends(_check_api_key),
) -> dict:
    """Start moving contents of source into destination (background). Returns 202; poll GET /move-status for progress.
    Source and destination are host paths; when HOST_ROOT is set they are translated to container paths (/host/...).
    """
    source_str = body.source.strip()
    dest_str = body.destination.strip()
    cfg = get_config()
    allowed = cfg["allowed_base_paths"]
    host_root = (cfg.get("host_root") or "").strip()

    try:
        source = _validate_host_path_under_allowed(source_str, allowed, host_root)
        dest = _validate_host_path_under_allowed(dest_str, allowed, host_root)
    except ValueError as e:
        logger.warning("move_validation_failed", source=source_str, dest=dest_str, error=str(e))
        raise HTTPException(status_code=400, detail="Invalid path") from e

    logger.info("move_requested", source_str=source_str, dest_str=dest_str, container_source=str(source), container_dest=str(dest))
    if not source.exists():
        # #region agent log
        try:
            import json
            with open("/workspace/.cursor/debug-36e3b3.log", "a") as _f:
                _f.write(json.dumps({"sessionId": "36e3b3", "hypothesisId": "source_not_found", "location": "routes.py:move", "message": "source_not_found", "data": {"source_str": source_str, "dest_str": dest_str, "container_source": str(source), "container_dest": str(dest), "host_root": host_root, "source_resolved": str(source.resolve())}, "timestamp": __import__("time").time() * 1000}) + "\n")
        except Exception:
            pass
        # #endregion
        logger.warning("move_source_not_found", source_str=source_str, container_path=str(source), host_root=host_root)
        raise HTTPException(status_code=404, detail="Source not found")

    # #region agent log
    try:
        _nfiles = len([f for f in source.rglob("*") if f.is_file()]) if source.is_dir() else (1 if source.is_file() else 0)
        import json
        with open("/workspace/.cursor/debug-36e3b3.log", "a") as _f:
            _f.write(json.dumps({"sessionId": "36e3b3", "hypothesisId": "H2,H3", "location": "routes.py:move", "message": "move_start", "data": {"source_str": source_str, "container_source": str(source), "exists": source.exists(), "is_dir": source.is_dir(), "is_file": source.is_file(), "nfiles": _nfiles, "host_root": host_root}, "timestamp": __import__("time").time() * 1000}) + "\n")
    except Exception:
        pass
    # #endregion

    with _move_lock:
        if _move_state.get("status") == "running":
            raise HTTPException(status_code=409, detail="Move already in progress")

    if source.is_dir():
        files_list = sorted(f for f in source.rglob("*") if f.is_file())
        total = len(files_list)
        dest.mkdir(parents=True, exist_ok=True)
        with _move_lock:
            _move_state.update({"status": "running", "total": total, "current": 0, "error": None})
        thread = threading.Thread(target=_run_move, args=(source, dest, files_list), daemon=True)
    else:
        with _move_lock:
            _move_state.update({"status": "running", "total": 0, "current": 0, "error": None})
        thread = threading.Thread(target=_run_move, args=(source, dest, None), daemon=True)
    thread.start()
    return JSONResponse(
        content={"ok": True, "status": "running", "message": "Move started"},
        status_code=202,
    )


@router.get("/move-status")
async def move_status(_: None = Depends(_check_api_key)) -> dict:
    """Return current move job progress (status: idle | running | done | error)."""
    with _move_lock:
        state = dict(_move_state)
    return state


@router.post("/reboot")
async def reboot_host(_: None = Depends(_check_api_key)) -> dict:
    """Reboot the host (Pi). Uses a privileged container with --pid=host so the reboot affects the host."""
    try:
        # Run reboot in background; we return immediately so the client gets a response before the host goes down.
        subprocess.Popen(
            [
                "docker", "run", "--rm", "--privileged", "--pid=host",
                "alpine", "reboot",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.error("reboot_docker_not_found")
        raise HTTPException(status_code=503, detail="Docker not available")
    except Exception as e:
        logger.exception("reboot_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("reboot_initiated")
    return {"ok": True, "message": "Reboot initiated"}


def _read_host_status(cfg: dict) -> dict:
    """Read host status from mounted /host/proc, /host/etc/hostname, etc."""
    out: dict = {
        "hostname": None,
        "ip": cfg.get("host_ip"),
        "memory": None,
        "cpu": None,
        "disk": None,
    }
    host_proc = cfg.get("host_proc", "/host/proc")
    host_etc_hostname = cfg.get("host_etc_hostname", "/host/etc/hostname")
    host_root = cfg.get("host_root")

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
            for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
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

    # CPU load from /proc/loadavg
    try:
        loadavg = Path(host_proc) / "loadavg"
        if loadavg.exists():
            parts = loadavg.read_text(encoding="utf-8", errors="replace").strip().split()
            load_1m = float(parts[0]) if len(parts) >= 1 else 0.0
            out["cpu"] = {"load_1m": load_1m, "percent_used": None}
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

    return out


@router.get("/host-status")
async def host_status(_: None = Depends(_check_api_key)) -> dict:
    """Return host info (hostname, IP, memory, CPU, disk) from mounted host paths."""
    cfg = get_config()
    return _read_host_status(cfg)
