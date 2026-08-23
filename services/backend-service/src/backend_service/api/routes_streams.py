"""REST API endpoints for audio streams."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.core.uploads import read_image_upload
from backend_service.models.database import Stream, StreamFolder
from backend_service.models.schemas import (
    StreamCreate,
    StreamResponse,
    StreamUpdate,
)

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[StreamResponse])
def list_streams(
    folder_id: int | None = Query(None, description="Filter by folder ID. Use 0 for root-level streams (no folder)."),
    db: Session = Depends(get_db),
) -> list[StreamResponse]:
    """List all streams, optionally filtered by folder."""
    logger.info("api_list_streams", folder_id=folder_id)
    query = db.query(Stream)
    if folder_id == 0:
        query = query.filter(Stream.folder_id.is_(None))
    elif folder_id is not None:
        folder = db.query(StreamFolder).filter(StreamFolder.id == folder_id).first()
        if not folder:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")
        query = query.filter(Stream.folder_id == folder_id)
    return [StreamResponse.model_validate(s) for s in query.all()]


@router.get("/{stream_id}", response_model=StreamResponse)
def get_stream(
    stream_id: int, db: Session = Depends(get_db)
) -> StreamResponse:
    """Get stream by ID."""
    logger.info("api_get_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise ApiError(status_code=404, code="stream_not_found", detail=f"Stream {stream_id} not found")
    return StreamResponse.model_validate(stream)


@router.post("", response_model=StreamResponse, status_code=201)
def create_stream(
    stream_data: StreamCreate,
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Create a new stream."""
    logger.info("api_create_stream", title=stream_data.title)
    if stream_data.folder_id is not None:
        folder = db.query(StreamFolder).filter(StreamFolder.id == stream_data.folder_id).first()
        if not folder:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {stream_data.folder_id} not found")
    stream = Stream(
        title=stream_data.title,
        artist=stream_data.artist,
        source_uri=stream_data.source_uri,
        folder_id=stream_data.folder_id,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    logger.info("api_stream_created", stream_id=stream.id, title=stream.title)
    return stream


@router.put("/{stream_id}", response_model=StreamResponse)
def update_stream(
    stream_id: int,
    stream_data: StreamUpdate,
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Update an existing stream."""
    logger.info("api_update_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise ApiError(status_code=404, code="stream_not_found", detail=f"Stream {stream_id} not found")
    if stream_data.title is not None:
        stream.title = stream_data.title
    if stream_data.artist is not None:
        stream.artist = stream_data.artist
    if stream_data.source_uri is not None:
        stream.source_uri = stream_data.source_uri
    if "folder_id" in stream_data.model_fields_set:
        if stream_data.folder_id is not None:
            folder = db.query(StreamFolder).filter(StreamFolder.id == stream_data.folder_id).first()
            if not folder:
                raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {stream_data.folder_id} not found")
        stream.folder_id = stream_data.folder_id
    db.commit()
    db.refresh(stream)
    return StreamResponse.model_validate(stream)


@router.delete("/{stream_id}", status_code=204)
def delete_stream(
    stream_id: int, db: Session = Depends(get_db)
) -> None:
    """Delete a stream."""
    logger.info("api_delete_stream", stream_id=stream_id)
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise ApiError(status_code=404, code="stream_not_found", detail=f"Stream {stream_id} not found")
    cover_path = COVERS_DIR / f"stream_{stream_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()
    db.delete(stream)
    db.commit()
    logger.info("api_delete_stream_completed", stream_id=stream_id)


@router.post("/{stream_id}/cover", response_model=StreamResponse)
async def upload_stream_cover(
    stream_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Upload cover art for a stream."""
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise ApiError(status_code=404, code="stream_not_found", detail=f"Stream {stream_id} not found")
    content = await read_image_upload(file)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVERS_DIR / f"stream_{stream_id}.jpg"
    cover_path.write_bytes(content)
    stream.cover_art_url = f"/static/covers/stream_{stream_id}.jpg"
    db.commit()
    db.refresh(stream)
    logger.info("stream_cover_uploaded", stream_id=stream_id)
    return StreamResponse.model_validate(stream)


@router.delete("/{stream_id}/cover", response_model=StreamResponse)
def delete_stream_cover(
    stream_id: int,
    db: Session = Depends(get_db),
) -> StreamResponse:
    """Remove cover art from a stream."""
    stream = db.query(Stream).filter(Stream.id == stream_id).first()
    if not stream:
        raise ApiError(status_code=404, code="stream_not_found", detail=f"Stream {stream_id} not found")
    cover_path = COVERS_DIR / f"stream_{stream_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()
    stream.cover_art_url = None
    db.commit()
    db.refresh(stream)
    logger.info("stream_cover_deleted", stream_id=stream_id)
    return StreamResponse.model_validate(stream)
