"""REST API for the debug export.

Security rules implemented here (docs/DebugExport.md 4.5):

* reachable without a login, but only from private networks - checked against
  the connection's peer address, never against X-Forwarded-For, which the
  caller controls,
* rate limited and single-flight, so it cannot be used to grind a Pi down,
* without an admin session the options are forced down to the standard tier:
  no filenames, no listening history, no database copy,
* every call is logged with the client address.

The endpoint takes exactly one shaped input (the option object). Option names
map to collectors from a registry - nothing from the request ever becomes a
path or a command.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Body, Request
from fastapi.responses import Response
from shared_lib.version import get_version

from backend_service.api.routes_auth import COOKIE_NAME
from backend_service.config import get_config
from backend_service.core.api_errors import ApiError
from backend_service.core.auth import read_auth_settings, verify_session_token
from backend_service.core.debug_export import (
    SCHEMA_VERSION,
    ExportOptions,
    create_export,
)
from backend_service.core.debug_export.descriptions import describe

logger = structlog.get_logger(__name__)
router = APIRouter()

RATE_LIMIT_SECONDS = 60.0
EXPORT_TIMEOUT_SECONDS = 180.0

_last_export_at: float = 0.0
_export_lock = asyncio.Lock()

# One-slot cache so "Inhalt vorher ansehen" does not build the archive twice.
# It lives as a file under DATA_PATH/tmp with mode 0600 rather than in memory:
# 25 MB of resident bytes matter on a Pi Zero, and the preview may sit around
# for minutes before anyone clicks download.
PREVIEW_TTL_SECONDS = 900
_preview: dict[str, Any] = {}


def _preview_dir() -> Path:
    directory = Path(os.environ.get("DATA_PATH", "/data")) / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _store_preview(archive: bytes, manifest: dict[str, Any], filename: str) -> str:
    _drop_preview()
    export_id = secrets.token_urlsafe(12)
    path = _preview_dir() / f"debug-export-{export_id}.zip"
    path.write_bytes(archive)
    path.chmod(0o600)
    _preview.update(
        {
            "id": export_id,
            "path": path,
            "manifest": manifest,
            "filename": filename,
            "created_at": time.monotonic(),
        }
    )
    return export_id


def _load_preview(export_id: str) -> tuple[bytes, str] | None:
    if not _preview or _preview.get("id") != export_id:
        return None
    if time.monotonic() - _preview.get("created_at", 0) > PREVIEW_TTL_SECONDS:
        _drop_preview()
        return None
    path: Path = _preview["path"]
    if not path.exists():
        _drop_preview()
        return None
    return path.read_bytes(), _preview["filename"]


def _drop_preview() -> None:
    path = _preview.get("path")
    if isinstance(path, Path):
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.debug("debug_export_preview_cleanup_failed", error=str(e))
    _preview.clear()


def _client_address(request: Request) -> str | None:
    """The peer address of the connection.

    Deliberately not X-Forwarded-For: that header is set by the caller, and
    trusting it would turn the private-network check into decoration.
    """
    return request.client.host if request.client else None


def _is_private_client(address: str | None) -> bool:
    if not address:
        return False
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    # is_private already covers loopback, link-local and unique-local.
    return parsed.is_private


def _has_admin_session(request: Request) -> bool:
    """True when the caller holds a valid session, or no password is configured."""
    settings = read_auth_settings()
    if not (settings.get("web_password_hash") or "").strip():
        # Without a configured password there is no elevated state to hold -
        # the box is as open as its network.
        return True
    token = request.cookies.get(COOKIE_NAME)
    return bool(token and verify_session_token(token))


def _versions() -> dict[str, Any]:
    config = get_config()
    return {
        "backend": get_version(),
        "schema_version": SCHEMA_VERSION,
        "device_id": config.device_id,
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def _build_archive(
    request: Request, payload: dict[str, Any]
) -> tuple[bytes, dict[str, Any], str]:
    global _last_export_at

    address = _client_address(request)
    if not _is_private_client(address):
        logger.warning("debug_export_rejected_public", client=address)
        raise ApiError(
            status_code=403,
            code="debug_export_local_only",
            detail="Debug package is only available from the local network.",
        )

    # Both cases are 429, but they mean different things to the user: one is
    # "your own export is still running" (the usual double-click), the other is
    # "you just made one". The code lets the WebUI say which apart.
    if _export_lock.locked():
        raise ApiError(
            status_code=429,
            code="export_in_progress",
            detail="An export is already running.",
        )

    since_last = time.monotonic() - _last_export_at
    if _last_export_at and since_last < RATE_LIMIT_SECONDS:
        retry_after = int(RATE_LIMIT_SECONDS - since_last)
        raise ApiError(
            status_code=429,
            code="export_rate_limited",
            detail=f"Please wait {retry_after} seconds.",
            headers={"Retry-After": str(max(1, retry_after))},
            extra={"retry_after": retry_after},
        )

    options = ExportOptions.from_payload(payload.get("options"))
    elevated = _has_admin_session(request)
    if not elevated:
        options = options.restrict_to_standard()

    client_payload = payload.get("client")
    if not isinstance(client_payload, dict):
        client_payload = {}

    config = get_config()
    async with _export_lock:
        _last_export_at = time.monotonic()
        try:
            archive, manifest = await asyncio.wait_for(
                create_export(
                    options=options,
                    device_id=config.device_id,
                    client_payload=client_payload,
                    versions=_versions(),
                ),
                timeout=EXPORT_TIMEOUT_SECONDS,
            )
        except TimeoutError as e:
            logger.error("debug_export_timeout", client=address)
            raise ApiError(
                status_code=504,
                code="debug_export_timeout",
                detail="Building the debug package took too long.",
            ) from e
        except Exception as e:
            logger.error("debug_export_failed", error=str(e), client=address)
            raise ApiError(
                status_code=500, code="debug_export_failed", detail="Could not build the debug package."
            ) from e

    logger.info(
        "debug_export_created",
        client=address,
        elevated=elevated,
        options=options.as_manifest(),
        bytes=len(archive),
        blocked_secrets=len(manifest.get("secret_tripwire", {}).get("blocked", [])),
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    filename = f"minabox-debug-{config.device_id}-{stamp}.zip"
    return archive, manifest, filename


def _zip_response(archive: bytes, filename: str) -> Response:
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Minabox-Schema-Version": str(SCHEMA_VERSION),
        },
    )


@router.post("/debug-export")
async def debug_export(
    request: Request, payload: dict[str, Any] = Body(default=None)
) -> Response:
    """Create the archive from the options the dialog sent."""
    archive, _, filename = await _build_archive(request, payload or {})
    return _zip_response(archive, filename)


@router.get("/debug-export")
async def debug_export_default(request: Request) -> Response:
    """Fallback path: paste the URL into a browser when the WebUI is dead.

    Same tier rules apply - without a session this yields the standard tier.
    """
    archive, _, filename = await _build_archive(request, {})
    return _zip_response(archive, filename)


@router.post("/debug-export/preview")
async def debug_export_preview(
    request: Request, payload: dict[str, Any] = Body(default=None)
) -> dict[str, Any]:
    """Build the archive, keep it, and describe its contents in plain language.

    This is what makes the privacy notice checkable rather than merely claimed:
    the user sees every file with a sentence about what it is before deciding to
    send anything.
    """
    archive, manifest, filename = await _build_archive(request, payload or {})
    export_id = _store_preview(archive, manifest, filename)

    files = [
        {
            "path": entry["path"],
            "bytes": entry["bytes"],
            "description": describe(entry["path"]),
        }
        for entry in manifest.get("files", [])
    ]
    files.sort(key=lambda item: item["path"])
    return {
        "export_id": export_id,
        "filename": filename,
        "total_bytes": len(archive),
        "schema_version": SCHEMA_VERSION,
        "options": manifest.get("options", {}),
        "files": files,
        "collectors_failed": [
            {"name": c["name"], "error": c.get("error")}
            for c in manifest.get("collectors", [])
            if c.get("status") == "failed"
        ],
        "expires_in_seconds": PREVIEW_TTL_SECONDS,
    }


@router.get("/debug-export/download/{export_id}")
async def debug_export_download(request: Request, export_id: str) -> Response:
    """Hand out the archive that the preview already built."""
    if not _is_private_client(_client_address(request)):
        raise ApiError(
            status_code=403,
            code="debug_export_local_only",
            detail="Debug package is only available from the local network.",
        )
    cached = _load_preview(export_id)
    if cached is None:
        raise ApiError(
            status_code=404,
            code="debug_export_preview_expired",
            detail="The preview has expired. Please rebuild the package.",
        )
    archive, filename = cached
    _drop_preview()
    return _zip_response(archive, filename)


@router.get("/debug-export/options")
def debug_export_options(request: Request) -> dict[str, Any]:
    """What the dialog may offer: the tiers this caller is allowed to pick."""
    return {
        "schema_version": SCHEMA_VERSION,
        "elevated": _has_admin_session(request),
        "presets": ["minimal", "recommended", "full"],
        "blocks": [
            {"key": "system", "always_on": True},
            {"key": "logs", "always_on": False},
            {"key": "settings", "always_on": False},
            {"key": "network", "always_on": False},
            {
                "key": "media",
                "always_on": False,
                "levels": ["off", "counts", "filenames"],
            },
            {"key": "history", "always_on": False, "requires_session": True},
            {"key": "client", "always_on": False},
            {"key": "database", "always_on": False, "requires_session": True},
            {"key": "sound_test", "always_on": False, "requires_session": True},
        ],
    }
