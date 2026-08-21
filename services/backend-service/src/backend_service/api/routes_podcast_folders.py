"""REST API endpoints for podcast folders."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Podcast, PodcastFolder
from backend_service.models.schemas import (
    PodcastFolderCreate,
    PodcastFolderResponse,
    PodcastFolderUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[PodcastFolderResponse])
def list_folders(db: Session = Depends(get_db)) -> list[PodcastFolderResponse]:
    """Return all podcast folders."""
    logger.info("api_list_podcast_folders")
    folders = db.query(PodcastFolder).order_by(PodcastFolder.name).all()
    return [PodcastFolderResponse.model_validate(f) for f in folders]


@router.get("/{folder_id}", response_model=PodcastFolderResponse)
def get_folder(folder_id: int, db: Session = Depends(get_db)) -> PodcastFolderResponse:
    """Return a single folder by ID."""
    folder = db.query(PodcastFolder).filter(PodcastFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
        )
    return PodcastFolderResponse.model_validate(folder)


@router.post("", response_model=PodcastFolderResponse, status_code=201)
def create_folder(
    folder_data: PodcastFolderCreate, db: Session = Depends(get_db)
) -> PodcastFolderResponse:
    """Create a new podcast folder."""
    if folder_data.parent_id is not None:
        parent = db.query(PodcastFolder).filter(PodcastFolder.id == folder_data.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Parent folder {folder_data.parent_id} not found", "details": {"folder_id": folder_data.parent_id}}},
            )
    folder = PodcastFolder(name=folder_data.name, parent_id=folder_data.parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    logger.info("api_podcast_folder_created", folder_id=folder.id, name=folder.name, parent_id=folder.parent_id)
    return PodcastFolderResponse.model_validate(folder)


@router.put("/{folder_id}", response_model=PodcastFolderResponse)
def update_folder(
    folder_id: int, folder_data: PodcastFolderUpdate, db: Session = Depends(get_db)
) -> PodcastFolderResponse:
    """Rename a folder or move it under a different parent."""
    folder = db.query(PodcastFolder).filter(PodcastFolder.id == folder_id).first()
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
            parent = db.query(PodcastFolder).filter(PodcastFolder.id == folder_data.parent_id).first()
            if not parent:
                raise HTTPException(
                    status_code=404,
                    detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Parent folder {folder_data.parent_id} not found", "details": {"folder_id": folder_data.parent_id}}},
                )
        folder.parent_id = folder_data.parent_id
    db.commit()
    db.refresh(folder)
    logger.info("api_podcast_folder_updated", folder_id=folder.id, name=folder.name)
    return PodcastFolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a folder. Contained podcasts are moved to root (folder_id set to null).
    Child folders are also moved to root.
    """
    folder = db.query(PodcastFolder).filter(PodcastFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
        )
    # Move all podcasts in this folder to root
    db.query(Podcast).filter(Podcast.folder_id == folder_id).update({"folder_id": None})
    # Move all child folders to root
    db.query(PodcastFolder).filter(PodcastFolder.parent_id == folder_id).update({"parent_id": None})
    db.delete(folder)
    db.commit()
    logger.info("api_podcast_folder_deleted", folder_id=folder_id)
