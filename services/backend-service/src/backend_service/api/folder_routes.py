"""One folder router, used by tracks, streams and podcasts.

The three used to be separate files of 94 lines that differed only in which
model they name - a diff of the track and stream versions with the words
swapped comes back empty. Three copies means a fix lands in one of them and
quietly misses the other two.

Folders are a flat convenience for the media library, not a hierarchy with
rules: deleting one keeps everything it held and moves it to the root, which is
the behaviour a parent expects from a music box rather than from a file manager.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.models.schemas import FolderCreate, FolderResponse, FolderUpdate

logger = structlog.get_logger(__name__)


def create_folder_router(
    *,
    folder_model: Any,
    item_model: Any,
    log_name: str,
) -> APIRouter:
    """Build the CRUD router for one media type's folders.

    The schemas are the same for all three - a folder is a name and a parent,
    whatever it holds - so they are named directly here rather than passed in.
    FastAPI reads the annotations off the function object, and a name bound to
    a parameter would arrive as a query parameter rather than a body.

    Args:
        folder_model: SQLAlchemy folder model (e.g. ``TrackFolder``).
        item_model: What lives in those folders (e.g. ``Track``).
        log_name: Name used in the structured log events, e.g. ``track``.
    """
    router = APIRouter()

    def _get_or_404(db: Session, folder_id: int) -> Any:
        folder = db.query(folder_model).filter(folder_model.id == folder_id).first()
        if not folder:
            raise ApiError(
                status_code=404,
                code="folder_not_found",
                detail=f"Folder {folder_id} not found",
            )
        return folder

    @router.get("", response_model=list[FolderResponse])
    def list_folders(db: Session = Depends(get_db)) -> list[FolderResponse]:
        """Return all folders, by name."""
        folders = db.query(folder_model).order_by(folder_model.name).all()
        return [FolderResponse.model_validate(f) for f in folders]

    @router.get("/{folder_id}", response_model=FolderResponse)
    def get_folder(folder_id: int, db: Session = Depends(get_db)) -> FolderResponse:
        """Return a single folder by ID."""
        return FolderResponse.model_validate(_get_or_404(db, folder_id))

    @router.post("", response_model=FolderResponse, status_code=201)
    def create_folder(
        folder_data: FolderCreate, db: Session = Depends(get_db)
    ) -> FolderResponse:
        """Create a folder, optionally below another one."""
        if folder_data.parent_id is not None:
            _get_or_404(db, folder_data.parent_id)
        folder = folder_model(name=folder_data.name, parent_id=folder_data.parent_id)
        db.add(folder)
        db.commit()
        db.refresh(folder)
        logger.info(
            f"api_{log_name}_folder_created", folder_id=folder.id, name=folder.name
        )
        return FolderResponse.model_validate(folder)

    @router.put("/{folder_id}", response_model=FolderResponse)
    def update_folder(
        folder_id: int,
        folder_data: FolderUpdate,
        db: Session = Depends(get_db),
    ) -> FolderResponse:
        """Rename a folder or move it below a different parent."""
        folder = _get_or_404(db, folder_id)
        if folder_data.name is not None:
            folder.name = folder_data.name
        if "parent_id" in folder_data.model_fields_set:
            if folder_data.parent_id == folder_id:
                raise ApiError(
                    status_code=400,
                    code="invalid_parent",
                    detail="A folder cannot be its own parent.",
                )
            if folder_data.parent_id is not None:
                _get_or_404(db, folder_data.parent_id)
            folder.parent_id = folder_data.parent_id
        db.commit()
        db.refresh(folder)
        logger.info(
            f"api_{log_name}_folder_updated", folder_id=folder.id, name=folder.name
        )
        return FolderResponse.model_validate(folder)

    @router.delete("/{folder_id}", status_code=204)
    def delete_folder(folder_id: int, db: Session = Depends(get_db)) -> None:
        """Delete a folder. Its contents and child folders move to the root."""
        folder = _get_or_404(db, folder_id)
        db.query(item_model).filter(item_model.folder_id == folder_id).update(
            {"folder_id": None}
        )
        db.query(folder_model).filter(folder_model.parent_id == folder_id).update(
            {"parent_id": None}
        )
        db.delete(folder)
        db.commit()
        logger.info(f"api_{log_name}_folder_deleted", folder_id=folder_id)

    return router


__all__ = ["create_folder_router"]
