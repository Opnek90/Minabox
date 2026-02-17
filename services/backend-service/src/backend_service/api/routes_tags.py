"""REST API endpoints for RFID tags."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Tag
from backend_service.models.schemas import TagCreate, TagResponse, TagUpdate

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[TagResponse])
async def list_tags(db: Session = Depends(get_db)) -> list[TagResponse]:
    """List all RFID tags.

    Returns:
        List of all tags
    """
    logger.info("api_list_tags")
    tags: list[Tag] = db.query(Tag).all()
    return [TagResponse.model_validate(tag) for tag in tags]


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: str, db: Session = Depends(get_db)) -> TagResponse:
    """Get tag by RFID tag ID.

    Args:
        tag_id: RFID tag UID (e.g., 04A224BC19)

    Returns:
        Tag details

    Raises:
        HTTPException: 404 if tag not found
    """
    logger.info("api_get_tag", tag_id=tag_id)
    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()

    if not tag:
        logger.warning("api_tag_not_found", tag_id=tag_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TAG_NOT_FOUND",
                    "message": f"Tag {tag_id} not found in database",
                    "details": {"tag_id": tag_id},
                }
            },
        )

    return TagResponse.model_validate(tag)


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db),
) -> TagResponse:
    """Create new RFID tag mapping (learning mode).

    Args:
        tag_data: Tag data

    Returns:
        Created tag

    Raises:
        HTTPException: 400 if tag already exists
    """
    logger.info("api_create_tag", tag_id=tag_data.tag_id)

    # Check if tag already exists
    existing_tag = db.query(Tag).filter(Tag.tag_id == tag_data.tag_id).first()
    if existing_tag:
        logger.warning("api_tag_already_exists", tag_id=tag_data.tag_id)
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "TAG_ALREADY_EXISTS",
                    "message": f"Tag {tag_data.tag_id} already exists",
                    "details": {"tag_id": tag_data.tag_id},
                }
            },
        )

    # Create tag
    tag = Tag(
        tag_id=tag_data.tag_id,
        name=tag_data.name,
        content_type=tag_data.content_type.value,
        content_id=tag_data.content_id,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    logger.info("api_tag_created", tag_id=tag_data.tag_id, db_id=tag.id)
    return TagResponse.model_validate(tag)


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    tag_data: TagUpdate,
    db: Session = Depends(get_db),
) -> TagResponse:
    """Update existing RFID tag mapping.

    Args:
        tag_id: RFID tag UID
        tag_data: Updated tag data

    Returns:
        Updated tag

    Raises:
        HTTPException: 404 if tag not found
    """
    logger.info("api_update_tag", tag_id=tag_id)

    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TAG_NOT_FOUND",
                    "message": f"Tag {tag_id} not found",
                    "details": {"tag_id": tag_id},
                }
            },
        )

    # Update fields
    if tag_data.name is not None:
        tag.name = tag_data.name
    if tag_data.content_type is not None:
        tag.content_type = tag_data.content_type.value
    if tag_data.content_id is not None:
        tag.content_id = tag_data.content_id

    db.commit()
    db.refresh(tag)

    logger.info("api_tag_updated", tag_id=tag_id)
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: str, db: Session = Depends(get_db)) -> None:
    """Delete RFID tag mapping.

    Args:
        tag_id: RFID tag UID

    Raises:
        HTTPException: 404 if tag not found
    """
    logger.info("api_delete_tag", tag_id=tag_id)

    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TAG_NOT_FOUND",
                    "message": f"Tag {tag_id} not found",
                    "details": {"tag_id": tag_id},
                }
            },
        )

    db.delete(tag)
    db.commit()

    logger.info("api_tag_deleted", tag_id=tag_id)
