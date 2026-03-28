"""REST API endpoints for track folders."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Track, TrackFolder
from backend_service.models.schemas import (
    TrackFolderCreate,
    TrackFolderResponse,
    TrackFolderUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[TrackFolderResponse])
async def list_folders(db: Session = Depends(get_db)) -> list[TrackFolderResponse]:
    """Return all track folders."""
    logger.info("api_list_track_folders")
    folders = db.query(TrackFolder).order_by(TrackFolder.name).all()
    return [TrackFolderResponse.model_validate(f) for f in folders]


@router.get("/{folder_id}", response_model=TrackFolderResponse)
async def get_folder(folder_id: int, db: Session = Depends(get_db)) -> TrackFolderResponse:
    """Return a single folder by ID."""
    folder = db.query(TrackFolder).filter(TrackFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
        )
    return TrackFolderResponse.model_validate(folder)


@router.post("", response_model=TrackFolderResponse, status_code=201)
async def create_folder(
    folder_data: TrackFolderCreate, db: Session = Depends(get_db)
) -> TrackFolderResponse:
    """Create a new track folder."""
    if folder_data.parent_id is not None:
        parent = db.query(TrackFolder).filter(TrackFolder.id == folder_data.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Parent folder {folder_data.parent_id} not found", "details": {"folder_id": folder_data.parent_id}}},
            )
    folder = TrackFolder(name=folder_data.name, parent_id=folder_data.parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    logger.info("api_track_folder_created", folder_id=folder.id, name=folder.name, parent_id=folder.parent_id)
    return TrackFolderResponse.model_validate(folder)


@router.put("/{folder_id}", response_model=TrackFolderResponse)
async def update_folder(
    folder_id: int, folder_data: TrackFolderUpdate, db: Session = Depends(get_db)
) -> TrackFolderResponse:
    """Rename a folder or move it under a different parent."""
    folder = db.query(TrackFolder).filter(TrackFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
        )
    if folder_data.name is not None:
        folder.name = folder_data.name
    if "parent_id" in folder_data.model_fields_set:
        if folder_data.parent_id == folder_id:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_PARENT", "message": "A folder cannot be its own parent."}},
            )
        if folder_data.parent_id is not None:
            parent = db.query(TrackFolder).filter(TrackFolder.id == folder_data.parent_id).first()
            if not parent:
                raise HTTPException(
                    status_code=404,
                    detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Parent folder {folder_data.parent_id} not found", "details": {"folder_id": folder_data.parent_id}}},
                )
        folder.parent_id = folder_data.parent_id
    db.commit()
    db.refresh(folder)
    logger.info("api_track_folder_updated", folder_id=folder.id, name=folder.name)
    return TrackFolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a folder. Contained tracks are moved to root (folder_id set to null).
    Child folders are also moved to root.
    """
    folder = db.query(TrackFolder).filter(TrackFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
        )
    # Move all tracks in this folder to root
    db.query(Track).filter(Track.folder_id == folder_id).update({"folder_id": None})
    # Move all child folders to root
    db.query(TrackFolder).filter(TrackFolder.parent_id == folder_id).update({"parent_id": None})
    db.delete(folder)
    db.commit()
    logger.info("api_track_folder_deleted", folder_id=folder_id)
