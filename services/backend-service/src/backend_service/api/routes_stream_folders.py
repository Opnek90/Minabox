"""REST API endpoints for stream folders."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.models.database import Stream, StreamFolder
from backend_service.models.schemas import (
    StreamFolderCreate,
    StreamFolderResponse,
    StreamFolderUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[StreamFolderResponse])
def list_folders(db: Session = Depends(get_db)) -> list[StreamFolderResponse]:
    """Return all stream folders."""
    logger.info("api_list_stream_folders")
    folders = db.query(StreamFolder).order_by(StreamFolder.name).all()
    return [StreamFolderResponse.model_validate(f) for f in folders]


@router.get("/{folder_id}", response_model=StreamFolderResponse)
def get_folder(folder_id: int, db: Session = Depends(get_db)) -> StreamFolderResponse:
    """Return a single folder by ID."""
    folder = db.query(StreamFolder).filter(StreamFolder.id == folder_id).first()
    if not folder:
        raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")
    return StreamFolderResponse.model_validate(folder)


@router.post("", response_model=StreamFolderResponse, status_code=201)
def create_folder(
    folder_data: StreamFolderCreate, db: Session = Depends(get_db)
) -> StreamFolderResponse:
    """Create a new stream folder."""
    if folder_data.parent_id is not None:
        parent = db.query(StreamFolder).filter(StreamFolder.id == folder_data.parent_id).first()
        if not parent:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Parent folder {folder_data.parent_id} not found")
    folder = StreamFolder(name=folder_data.name, parent_id=folder_data.parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    logger.info("api_stream_folder_created", folder_id=folder.id, name=folder.name, parent_id=folder.parent_id)
    return StreamFolderResponse.model_validate(folder)


@router.put("/{folder_id}", response_model=StreamFolderResponse)
def update_folder(
    folder_id: int, folder_data: StreamFolderUpdate, db: Session = Depends(get_db)
) -> StreamFolderResponse:
    """Rename a folder or move it under a different parent."""
    folder = db.query(StreamFolder).filter(StreamFolder.id == folder_id).first()
    if not folder:
        raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")
    if folder_data.name is not None:
        folder.name = folder_data.name
    if "parent_id" in folder_data.model_fields_set:
        if folder_data.parent_id == folder_id:
            raise ApiError(status_code=400, code="invalid_parent", detail="A folder cannot be its own parent.")
        if folder_data.parent_id is not None:
            parent = db.query(StreamFolder).filter(StreamFolder.id == folder_data.parent_id).first()
            if not parent:
                raise ApiError(status_code=404, code="folder_not_found", detail=f"Parent folder {folder_data.parent_id} not found")
        folder.parent_id = folder_data.parent_id
    db.commit()
    db.refresh(folder)
    logger.info("api_stream_folder_updated", folder_id=folder.id, name=folder.name)
    return StreamFolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a folder. Contained streams are moved to root (folder_id set to null).
    Child folders are also moved to root.
    """
    folder = db.query(StreamFolder).filter(StreamFolder.id == folder_id).first()
    if not folder:
        raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")
    # Move all streams in this folder to root
    db.query(Stream).filter(Stream.folder_id == folder_id).update({"folder_id": None})
    # Move all child folders to root
    db.query(StreamFolder).filter(StreamFolder.parent_id == folder_id).update({"parent_id": None})
    db.delete(folder)
    db.commit()
    logger.info("api_stream_folder_deleted", folder_id=folder_id)
