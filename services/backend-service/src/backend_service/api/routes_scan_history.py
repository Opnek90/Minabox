"""Scan-history API endpoints (issue #72)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query

import backend_service.core.db_manager as _db_module
from backend_service.core.api_errors import ApiError
from backend_service.models.database import TagScanEvent
from backend_service.models.schemas_rfid import TagScanEventResponse

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=list[TagScanEventResponse])
async def list_scan_history(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tag_id: str | None = Query(default=None, description="Filter by raw tag UID"),
) -> list[TagScanEventResponse]:
    """Return scan-history events, newest first."""
    if not _db_module.db_manager:
        raise ApiError(status_code=503, code="database_unavailable", detail="Database not available")

    session = _db_module.db_manager.get_session()
    try:
        q = session.query(TagScanEvent)
        if tag_id:
            q = q.filter(TagScanEvent.tag_uid == tag_id)
        events = (
            q.order_by(TagScanEvent.scanned_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [TagScanEventResponse.from_orm_event(e) for e in events]
    finally:
        session.close()


@router.delete("/", status_code=204)
async def clear_scan_history() -> None:
    """Delete all scan-history events."""
    if not _db_module.db_manager:
        raise ApiError(status_code=503, code="database_unavailable", detail="Database not available")

    session = _db_module.db_manager.get_session()
    try:
        session.query(TagScanEvent).delete()
        session.commit()
        logger.info("scan_history_cleared")
    except Exception as exc:
        session.rollback()
        logger.error("scan_history_clear_failed", error=str(exc))
        raise ApiError(status_code=500, code="scan_history_clear_failed", detail="Failed to clear scan history") from exc
    finally:
        session.close()
