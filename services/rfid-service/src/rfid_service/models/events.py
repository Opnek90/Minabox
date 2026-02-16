"""Event models for RFID service MQTT messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class TagScannedEvent(BaseModel):
    """Event published when a tag is scanned in normal mode."""

    tag_id: str = Field(
        description="RFID tag UID in uppercase hex format (e.g., '04A224BC19').",
    )
    reader_id: str = Field(
        description="Identifier of the reader that detected the tag.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tag_id": "04A224BC19",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:00Z",
            }
        }


class TagScannedLearningEvent(BaseModel):
    """Event published when a tag is scanned in learning mode."""

    tag_id: str = Field(
        description="RFID tag UID in uppercase hex format.",
    )
    reader_id: str = Field(
        description="Identifier of the reader that detected the tag.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tag_id": "DEADBEEF01",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:05Z",
            }
        }


class TagRemovedEvent(BaseModel):
    """Event published when a tag is removed from the reader."""

    tag_id: str = Field(
        description="RFID tag UID that was removed.",
    )
    reader_id: str = Field(
        description="Identifier of the reader.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tag_id": "04A224BC19",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:10Z",
            }
        }


class RFIDStatusEvent(BaseModel):
    """Status update for the RFID service (retained message)."""

    state: Literal["idle", "normal", "learning", "error"] = Field(
        description="Current operational state of the service.",
    )
    reader_id: str = Field(
        description="Identifier of the active reader.",
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error code if state is 'error': "
            "reader_not_found, reader_init_failed, read_timeout, protocol_error."
        ),
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the status.",
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "state": "normal",
                    "reader_id": "pn532_i2c",
                    "error": None,
                    "timestamp": "2026-02-16T22:48:00Z",
                },
                {
                    "state": "error",
                    "reader_id": "pn532_i2c",
                    "error": "reader_not_found",
                    "timestamp": "2026-02-16T22:48:00Z",
                },
            ]
        }
