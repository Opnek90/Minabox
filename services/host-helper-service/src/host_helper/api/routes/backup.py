"""Creating a backup archive and restoring one."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask

from host_helper.api.routes.deps import (
    _check_api_key,
    _run_compose_on_host,
    _run_compose_on_others,
    get_config,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


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
