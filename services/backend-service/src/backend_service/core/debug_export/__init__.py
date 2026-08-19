"""Debug export: collect a diagnosable snapshot of the box into one archive.

Public entry point is :func:`create_export`. See docs/DebugExport.md for the
package layout, the privacy tiers and the security rules this implements.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from backend_service.core.debug_export import collectors  # noqa: F401  (registers them)
from backend_service.core.debug_export.framework import (
    DEFAULT_MAX_TOTAL_BYTES,
    REGISTRY,
    SCHEMA_VERSION,
    ExportContext,
    ExportOptions,
    build_archive,
    run_collectors,
)
from backend_service.core.debug_export.redaction import SecretTripwire

logger = structlog.get_logger(__name__)


async def create_export(
    *,
    options: ExportOptions,
    device_id: str,
    data_path: Path | str = "/data",
    client_payload: dict[str, Any] | None = None,
    versions: dict[str, Any] | None = None,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> tuple[bytes, dict[str, Any]]:
    """Run the selected collectors and build the archive.

    The salt is fresh per export: pseudonyms stay comparable inside one archive
    and cannot be matched across two.
    """
    context = ExportContext(
        options=options,
        salt=secrets.token_hex(16),
        data_path=Path(data_path),
        device_id=device_id,
        client_payload=client_payload or {},
        started_at=datetime.now(UTC),
    )
    tripwire = SecretTripwire.from_device(data_path)
    outcomes = await run_collectors(context)
    archive, manifest = build_archive(
        context,
        outcomes,
        tripwire,
        versions=versions,
        max_total_bytes=max_total_bytes,
    )
    logger.info(
        "debug_export_created",
        device_id=device_id,
        bytes=len(archive),
        collectors_ok=sum(1 for o in outcomes if o.status == "ok"),
        collectors_failed=sum(1 for o in outcomes if o.status == "failed"),
    )
    return archive, manifest


__all__ = [
    "REGISTRY",
    "SCHEMA_VERSION",
    "ExportOptions",
    "create_export",
]
