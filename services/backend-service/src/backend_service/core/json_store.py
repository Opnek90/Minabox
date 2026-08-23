"""Crash-safe writing of the small JSON files the backend owns.

The box is meant to survive having its plug pulled at any moment. A plain
``write_text()`` truncates the target first, so losing power mid-write left a
half-written file behind. For ``auth_settings.json`` that is worse than it
sounds: the reader falls back to "no password configured" on invalid JSON, so a
box could come back up unprotected.

Same approach the audio service uses for its playback state: write a temporary
file next to the target, fsync it, then rename. A reader only ever sees the old
file or the complete new one.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def write_json_atomic(path: Path, payload: Any, *, chmod: int | None = None) -> None:
    """Serialize ``payload`` to ``path`` without ever leaving it half-written.

    Raises ``OSError`` like the plain write it replaces, so callers keep their
    existing error handling.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        if chmod is not None:
            os.chmod(tmp_name, chmod)
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    logger.debug("json_written_atomically", path=str(path))


__all__ = ["write_json_atomic"]
