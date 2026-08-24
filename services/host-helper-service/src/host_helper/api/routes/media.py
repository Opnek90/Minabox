"""The audio folder: where it lives and moving it somewhere else."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from host_helper.api.routes.deps import (
    _check_api_key,
    get_config,
)
from host_helper.config import validate_path_under_allowed

logger = structlog.get_logger(__name__)

router = APIRouter()


class ApplyAudioPathBody(BaseModel):
    audio_files_path: str


class MoveBody(BaseModel):
    source: str
    destination: str


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


# Move job state for progress (idle | running | done | error)
_move_state: dict = {"status": "idle", "total": 0, "current": 0, "error": None}


_move_lock = threading.Lock()


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
