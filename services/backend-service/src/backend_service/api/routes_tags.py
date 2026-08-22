"""REST API endpoints for RFID tags."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend_service.core.api_errors import ApiError
from backend_service.core.db_manager import get_db
from backend_service.models.database import Tag
from backend_service.models.schemas import TagCreate, TagResponse, TagUpdate

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db)) -> list[TagResponse]:
    """List all RFID tags."""
    logger.info("api_list_tags")
    tags: list[Tag] = db.query(Tag).all()
    return [TagResponse.model_validate(tag) for tag in tags]


@router.get("/{tag_id}", response_model=TagResponse)
def get_tag(tag_id: str, db: Session = Depends(get_db)) -> TagResponse:
    """Get tag by RFID tag ID."""
    logger.info("api_get_tag", tag_id=tag_id)
    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        logger.warning("api_tag_not_found", tag_id=tag_id)
        raise ApiError(status_code=404, code="tag_not_found", detail=f"Tag {tag_id} not found in database")
    return TagResponse.model_validate(tag)


@router.post("", response_model=TagResponse, status_code=201)
def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db),
) -> TagResponse:
    """Create new RFID tag mapping (learning mode)."""
    logger.info("api_create_tag", tag_id=tag_data.tag_id)

    existing_tag = db.query(Tag).filter(Tag.tag_id == tag_data.tag_id).first()
    if existing_tag:
        logger.warning("api_tag_already_exists", tag_id=tag_data.tag_id)
        raise ApiError(status_code=400, code="tag_already_exists", detail=f"Tag {tag_data.tag_id} already exists")

    tag = Tag(
        tag_id=tag_data.tag_id,
        name=tag_data.name,
        content_type=tag_data.content_type.value if tag_data.content_type else None,
        content_id=tag_data.content_id,
        disabled=tag_data.disabled,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    logger.info("api_tag_created", tag_id=tag_data.tag_id, db_id=tag.id, disabled=tag.disabled)
    return TagResponse.model_validate(tag)


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    request: Request,
    tag_data: TagUpdate,
    db: Session = Depends(get_db),
) -> TagResponse:
    """Update existing RFID tag mapping.

    Passing content_id=null and content_type=null explicitly clears the
    content assignment (unassigns the tag).
    """
    logger.info("api_update_tag", tag_id=tag_id)

    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        raise ApiError(status_code=404, code="tag_not_found", detail=f"Tag {tag_id} not found")

    # Parse raw body once to detect explicit null vs omitted fields
    try:
        raw_body: dict = await request.json()
    except Exception:
        raw_body = {}

    if tag_data.name is not None:
        tag.name = tag_data.name

    # content_type: update if provided; clear if explicitly null in body
    if tag_data.content_type is not None:
        tag.content_type = tag_data.content_type.value
    elif "content_type" in raw_body and raw_body["content_type"] is None:
        tag.content_type = None

    # content_id: update if provided; clear if explicitly null in body
    if tag_data.content_id is not None:
        tag.content_id = tag_data.content_id
    elif "content_id" in raw_body and raw_body["content_id"] is None:
        tag.content_id = None

    if tag_data.disabled is not None:
        tag.disabled = tag_data.disabled
        logger.info(
            "api_tag_disabled_changed",
            tag_id=tag_id,
            disabled=tag_data.disabled,
        )

    db.commit()
    db.refresh(tag)

    logger.info("api_update_tag_completed", tag_id=tag_id, content_id=tag.content_id)
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: str, db: Session = Depends(get_db)) -> None:
    """Delete RFID tag mapping."""
    logger.info("api_delete_tag", tag_id=tag_id)

    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        raise ApiError(status_code=404, code="tag_not_found", detail=f"Tag {tag_id} not found")

    db.delete(tag)
    db.commit()

    logger.info("api_tag_deleted", tag_id=tag_id)
