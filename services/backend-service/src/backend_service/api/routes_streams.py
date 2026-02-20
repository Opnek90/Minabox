"""REST API endpoints for audio streams."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Stream
from backend_service.models.schemas import (
    StreamCreate,
    StreamResponse,
    StreamUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[StreamResponse])
async def list_streams(db: Session = Depends(get_db)) -> list[StreamResponse]:
    """List all streams."""
    logger.info("api_list_streams")
    streams = db.query(Stream).all()
    return [StreamResponse.model_validate(s) for s in streams]


@router.get("/{stream_id}", response_model=StreamResponse)
async def get_stream(
    stream_id: int, db: Session = Depends(get_db)
) -> StreamResponse:
    """Get stream by ID."""
    logger.info("api_get_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "STREAM_NOT_FOUND",
                    "message": f"Stream {stream_id} not found",
                    "details": {"stream_id": stream_id},
                }
            },
        )
    return StreamResponse.model_validate(stream)


@router.post("", response_model=StreamResponse, status_code=201)
async def create_stream(
    stream_data: StreamCreate,
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Create a new stream."""
    logger.info("api_create_stream", title=stream_data.title)
    stream = Stream(
        title=stream_data.title,
        artist=stream_data.artist,
        source_uri=stream_data.source_uri,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    logger.info("api_stream_created", stream_id=stream.id, title=stream.title)
    return stream


@router.put("/{stream_id}", response_model=StreamResponse)
async def update_stream(
    stream_id: int,
    stream_data: StreamUpdate,
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Update an existing stream."""
    logger.info("api_update_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "STREAM_NOT_FOUND",
                    "message": f"Stream {stream_id} not found",
                    "details": {"stream_id": stream_id},
                }
            },
        )
    if stream_data.title is not None:
        stream.title = stream_data.title
    if stream_data.artist is not None:
        stream.artist = stream_data.artist
    if stream_data.source_uri is not None:
        stream.source_uri = stream_data.source_uri
    db.commit()
    db.refresh(stream)
    return StreamResponse.model_validate(stream)


@router.delete("/{stream_id}", status_code=204)
async def delete_stream(
    stream_id: int, db: Session = Depends(get_db)
) -> None:
    """Delete a stream."""
    logger.info("api_delete_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "STREAM_NOT_FOUND",
                    "message": f"Stream {stream_id} not found",
                    "details": {"stream_id": stream_id},
                }
            },
        )
    db.delete(stream)
    db.commit()
    logger.info("api_delete_stream_completed", stream_id=stream_id)
