"""Read-only access to host files mounted into the backend container.

The compose file mounts /proc, /sys, /etc/os-release, /boot/firmware, the dpkg
status file and the apt log under HOST_DIAG_ROOT (default /host), all :ro. This
module is the only way the export touches them, so the safety rules live in one
place:

* the resolved path must stay under the configured root - a symlink under
  /boot pointing at /etc/shadow resolves outside and is rejected,
* the final open uses O_NOFOLLOW and rejects anything that is not a regular
  file, so a swapped-in FIFO cannot block the export,
* every read is capped, because /proc has files that never end.

Nothing here executes anything. When the mounts are absent (tests, or a
container started from an older compose file) the reads fail softly and the
collector reports "skipped" instead of the export breaking.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_MAX_BYTES = 1024 * 1024


def host_root() -> Path:
    """Root under which the host filesystem is mounted read-only."""
    return Path(os.environ.get("HOST_DIAG_ROOT", "/host"))


def host_mounts_available() -> bool:
    root = host_root()
    return (root / "proc").is_dir() and (root / "sys").is_dir()


def host_path(relative: str) -> Path:
    """Map a host-absolute path such as /proc/uptime into the mounted root."""
    return host_root() / relative.lstrip("/")


def read_text(relative: str, max_bytes: int = DEFAULT_MAX_BYTES) -> str | None:
    """Read a host file safely. Returns None when it is missing or unreadable."""
    root = host_root()
    candidate = host_path(relative)
    try:
        resolved = candidate.resolve()
    except OSError as e:
        logger.debug("hostfile_resolve_failed", path=relative, error=str(e))
        return None

    try:
        root_resolved = root.resolve()
    except OSError:
        return None

    if resolved != root_resolved and root_resolved not in resolved.parents:
        logger.warning("hostfile_outside_root", path=relative, resolved=str(resolved))
        return None

    fd = None
    try:
        fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            logger.debug("hostfile_not_regular", path=relative)
            return None
        # /proc and /sys report st_size 0, so the cap is what actually bounds
        # the read.
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = None
            raw = handle.read(max_bytes + 1)
    except OSError as e:
        logger.debug("hostfile_read_failed", path=relative, error=str(e))
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += "\n[truncated]\n"
    return text


def read_stripped(relative: str, max_bytes: int = 4096) -> str | None:
    """Read a small single-value file such as /sys/class/thermal/.../temp."""
    text = read_text(relative, max_bytes=max_bytes)
    if text is None:
        return None
    return text.replace("\x00", "").strip() or None


def read_int(relative: str) -> int | None:
    text = read_stripped(relative)
    if text is None:
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def list_dir(relative: str) -> list[Path]:
    """List a directory under the host root; empty list when unavailable."""
    directory = host_path(relative)
    try:
        if not directory.is_dir():
            return []
        return sorted(directory.iterdir())
    except OSError as e:
        logger.debug("hostdir_list_failed", path=relative, error=str(e))
        return []
