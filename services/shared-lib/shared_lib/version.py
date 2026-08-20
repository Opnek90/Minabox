"""Build-time version information of the running service.

The values come from environment variables that the Dockerfile sets from
build args (see docs/Versionierung.md). A container built without those args -
a local ``docker compose build`` during development - reports ``0.0.0-dev``.
That is deliberate: an unversioned build should be recognisable as such rather
than pretend to be a release.

The same values are also written into the image as OCI labels, which is how
the backend learns the version of containers that have no Python at all
(mqtt, webui). This module covers the other direction: what the process itself
believes it is, reported via ``/health``.
"""

from __future__ import annotations

import os
from typing import Any

#: Version reported when no build arg was passed (local development build).
DEV_VERSION = "0.0.0-dev"


def get_version() -> str:
    """Semantic version of this service, e.g. ``1.2.0``."""
    return os.environ.get("APP_VERSION") or DEV_VERSION


def get_git_sha() -> str | None:
    """Short commit the image was built from, or ``None`` if unknown."""
    sha = os.environ.get("GIT_SHA")
    return sha if sha and sha != "unknown" else None


def get_build_date() -> str | None:
    """ISO-8601 build timestamp, or ``None`` if unknown."""
    date = os.environ.get("BUILD_DATE")
    return date if date and date != "unknown" else None


def is_dev_build() -> bool:
    """True when this image carries no release version."""
    return get_version() == DEV_VERSION


def version_info() -> dict[str, Any]:
    """Version fields for a health response. Unknown fields are omitted."""
    info: dict[str, Any] = {"version": get_version()}
    sha = get_git_sha()
    if sha:
        info["git_sha"] = sha
    date = get_build_date()
    if date:
        info["build_date"] = date
    return info
