"""Pydantic schemas for RFID-related endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class TagBase(BaseModel):
    """Base schema for RFID tags."""

    name: Optional[str] = None
    content_type: str
    content_id: int
    disabled: bool = False


class TagCreate(TagBase):
    """Schema for creating a new tag."""

    tag_id: str


class TagUpdate(BaseModel):
    """Schema for updating an existing tag."""

    name: Optional[str] = None
    content_type: Optional[str] = None
    content_id: Optional[int] = None
    disabled: Optional[bool] = None


class TagResponse(TagBase):
    """Schema for returning a tag."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tag_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_scanned_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Scan History (issue #72)
# ---------------------------------------------------------------------------


class TagScanEventResponse(BaseModel):
    """Schema for a single scan history entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tag_id: str  # exposed as tag_id for frontend consistency (maps from tag_uid)
    tag_name: Optional[str] = None
    media_title: Optional[str] = None
    media_type: Optional[str] = None
    action: Literal["play", "blocked", "unassigned"]
    scanned_at: datetime

    @classmethod
    def from_orm_event(cls, event: object) -> "TagScanEventResponse":
        """Map DB column tag_uid -> response field tag_id."""
        return cls(
            id=event.id,  # type: ignore[attr-defined]
            tag_id=event.tag_uid,  # type: ignore[attr-defined]
            tag_name=event.tag_name,  # type: ignore[attr-defined]
            media_title=event.media_title,  # type: ignore[attr-defined]
            media_type=event.media_type,  # type: ignore[attr-defined]
            action=event.action,  # type: ignore[attr-defined]
            scanned_at=event.scanned_at,  # type: ignore[attr-defined]
        )
