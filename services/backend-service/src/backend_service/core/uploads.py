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

from pathlib import Path
from typing import IO, Any

import structlog

from backend_service.config import get_config
from backend_service.core.api_errors import ApiError

logger = structlog.get_logger(__name__)

#: Cover art and logo. Read fully into memory, so this stays well below what a
#: Pi can spare.
MAX_IMAGE_UPLOAD_BYTES: int = 5 * 1024 * 1024

#: Read granularity. Large enough that the loop is not the bottleneck on an SD
#: card, small enough that the peak allocation stays irrelevant.
_CHUNK_BYTES: int = 1024 * 1024

#: Fallback when the configuration cannot be loaded - an upload must not fail
#: because of an unrelated config problem, but it must not become unbounded
#: either.
_DEFAULT_AUDIO_LIMIT_MB: int = 100


def max_audio_upload_bytes() -> int:
    """Upload limit for audio files, from ``max_upload_size_mb``."""
    try:
        return get_config().backend.max_upload_size_mb * 1024 * 1024
    except Exception as exc:  # pragma: no cover - config is validated elsewhere
        logger.warning("upload_limit_config_unreadable", error=str(exc))
        return _DEFAULT_AUDIO_LIMIT_MB * 1024 * 1024


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
    "MAX_IMAGE_UPLOAD_BYTES",
    "copy_upload_limited",
    "max_audio_upload_bytes",
    "read_image_upload",
    "upload_too_large",
]
