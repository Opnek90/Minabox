from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas_enums import RFIDMode


class RFIDLearningModeCommand(BaseModel):
    """Schema for RFID learning mode command."""

    enabled: bool = Field(..., description="Enable/disable learning mode")


class RFIDScanEvent(BaseModel):
    """Schema for RFID scan event."""

    tag_id: str
    reader_id: str = "pn532_01"
    timestamp: datetime


class RFIDModeResponse(BaseModel):
    """Schema representing the current RFID reader mode."""

    mode: RFIDMode


# ---------------------------------------------------------------------------
# Scan History (issue #72)
# ---------------------------------------------------------------------------


class TagScanEventResponse(BaseModel):
    """Schema for a single scan history entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tag_id: str  # maps from DB column tag_uid
    tag_name: str | None = None
    media_title: str | None = None
    media_type: str | None = None
    action: Literal["play", "blocked", "unassigned"]
    scanned_at: datetime

    @classmethod
    def from_orm_event(cls, event: object) -> TagScanEventResponse:
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


__all__ = [
    "RFIDLearningModeCommand",
    "RFIDScanEvent",
    "RFIDModeResponse",
    "TagScanEventResponse",
]
