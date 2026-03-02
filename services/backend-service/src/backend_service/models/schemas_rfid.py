from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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


__all__ = [
    "RFIDLearningModeCommand",
    "RFIDScanEvent",
    "RFIDModeResponse",
]

