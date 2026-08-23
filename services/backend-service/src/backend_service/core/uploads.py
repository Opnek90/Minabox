"""Size-bounded handling of uploaded files.

Every upload path used to go straight to ``await file.read()`` or an unbounded
``shutil.copyfileobj``. On a Pi Zero a single large request was therefore enough
to exhaust the RAM, and a large audio file could fill the SD card. The limit
``max_upload_size_mb`` existed in ``config/backend.json`` from the start but was
never read by anything - it is the source for the audio limit here.

Images (cover art, logo) get their own, much smaller budget: they are read into
memory in one piece, and no legitimate cover comes anywhere near it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO, Any

import structlog
from shared_lib.config import load_general_settings

from backend_service.config import get_config
from backend_service.core.api_errors import ApiError

logger = structlog.get_logger(__name__)

#: Cover art and logo. Read fully into memory, so this stays well below what a
#: Pi can spare.
MAX_IMAGE_UPLOAD_BYTES: int = 5 * 1024 * 1024

#: Read granularity. Large enough that the loop is not the bottleneck on an SD
#: card, small enough that the peak allocation stays irrelevant.
_CHUNK_BYTES: int = 1024 * 1024

#: Fallback when no configuration can be read at all - an upload must not fail
#: because of an unrelated config problem, but it must not become unbounded
#: either.
DEFAULT_UPLOAD_SIZE_MB: int = 100

#: A limit below this makes the feature unusable; above it, the spooled upload
#: plus the stored copy stop fitting on a typical SD card.
MIN_UPLOAD_SIZE_MB: int = 1
MAX_UPLOAD_SIZE_MB: int = 2048


def _general_settings_path() -> Path:
    return Path(os.environ.get("DATA_PATH", "/data")) / "general_settings.json"


def clamp_upload_size_mb(value: object) -> int:
    """Normalize a raw value to a usable limit in MB."""
    try:
        megabytes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_UPLOAD_SIZE_MB
    return max(MIN_UPLOAD_SIZE_MB, min(MAX_UPLOAD_SIZE_MB, megabytes))


def _configured_default_mb() -> int:
    """The default from ``config/backend.json``.

    That file is mounted read-only, so it can only ever supply the value a
    release ships with - never something the user changed.
    """
    try:
        return clamp_upload_size_mb(get_config().backend.max_upload_size_mb)
    except Exception as exc:  # pragma: no cover - config is validated elsewhere
        logger.warning("upload_limit_config_unreadable", error=str(exc))
        return DEFAULT_UPLOAD_SIZE_MB


def max_upload_size_mb() -> int:
    """The upload limit for audio files, in MB.

    Read fresh from ``general_settings.json`` on every call, so a change in the
    WebUI takes effect without a restart - the same contract the playback and
    parental settings follow. Without an entry there, the value shipped in
    ``config/backend.json`` applies.
    """
    settings = load_general_settings(_general_settings_path())
    if "max_upload_size_mb" in settings:
        return clamp_upload_size_mb(settings["max_upload_size_mb"])
    return _configured_default_mb()


def max_audio_upload_bytes() -> int:
    """The upload limit for audio files, in bytes."""
    return max_upload_size_mb() * 1024 * 1024


def upload_too_large(limit_bytes: int) -> ApiError:
    """The error every caller raises once a limit is hit."""
    limit_mb = max(1, limit_bytes // (1024 * 1024))
    return ApiError(
        status_code=413,
        code="upload_too_large",
        detail=f"Upload exceeds the limit of {limit_mb} MB",
        extra={"limit_bytes": limit_bytes},
    )


async def read_image_upload(
    upload: Any, limit_bytes: int = MAX_IMAGE_UPLOAD_BYTES
) -> bytes:
    """Read an uploaded image, refusing anything past ``limit_bytes``.

    Reads in chunks and stops at the first one that crosses the limit, so an
    oversized upload is never fully held in memory.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            logger.warning("upload_rejected_too_large", limit_bytes=limit_bytes)
            raise upload_too_large(limit_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


def copy_upload_limited(source: IO[bytes], target: Path, limit_bytes: int) -> int:
    """Copy an upload to ``target``, aborting once ``limit_bytes`` is exceeded.

    Blocking - call it through ``asyncio.to_thread``. The partial file is
    removed before the error propagates, so a refused upload leaves nothing
    behind on the SD card.
    """
    total = 0
    try:
        with open(target, "wb") as handle:
            while True:
                chunk = source.read(_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit_bytes:
                    logger.warning(
                        "upload_rejected_too_large",
                        limit_bytes=limit_bytes,
                        path=str(target),
                    )
                    raise upload_too_large(limit_bytes)
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return total


__all__ = [
    "DEFAULT_UPLOAD_SIZE_MB",
    "MAX_IMAGE_UPLOAD_BYTES",
    "MAX_UPLOAD_SIZE_MB",
    "MIN_UPLOAD_SIZE_MB",
    "clamp_upload_size_mb",
    "copy_upload_limited",
    "max_audio_upload_bytes",
    "max_upload_size_mb",
    "read_image_upload",
    "upload_too_large",
]
