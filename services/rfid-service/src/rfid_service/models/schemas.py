"""Pydantic schemas / event models for RFID service MQTT messages.

This module defines the data structures for all MQTT events published
by the RFID service, following the Framework convention of models/schemas.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TagScannedEvent(BaseModel):
    """Event published when a tag is scanned in normal mode."""

    tag_id: str = Field(
        description="RFID tag UID in uppercase hex format (e.g., '04A224BC19').",
    )
    reader_id: str = Field(
        description="Identifier of the reader that detected the tag.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_id": "04A224BC19",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:00Z",
            }
        }
    )


class TagScannedLearningEvent(BaseModel):
    """Event published when a tag is scanned in learning mode."""

    tag_id: str = Field(
        description="RFID tag UID in uppercase hex format.",
    )
    reader_id: str = Field(
        description="Identifier of the reader that detected the tag.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_id": "DEADBEEF01",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:05Z",
            }
        }
    )


class TagRemovedEvent(BaseModel):
    """Event published when a tag is removed from the reader."""

    tag_id: str = Field(
        description="RFID tag UID that was removed.",
    )
    reader_id: str = Field(
        description="Identifier of the reader.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of the event.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_id": "04A224BC19",
                "reader_id": "pn532_i2c",
                "timestamp": "2026-02-16T22:48:10Z",
            }
        }
    )


class TagPresenceEvent(BaseModel):
    """Retained presence state of the RFID reader (tag on / off).

    Published with retain=True whenever the tag presence changes and on
    service startup. Subscribers (e.g. LED-service) can use this to recover
    the correct RFID state after a re-initialization without waiting for the
    next state-change event.
    """

    tag_present: bool = Field(
        description="True if a tag is currently on the reader, False otherwise.",
    )
    tag_id: str | None = Field(
        default=None,
        description="UID of the present tag, or null when no tag is on the reader.",
    )
    reader_id: str = Field(
        description="Identifier of the reader.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of the last presence change.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tag_present": True,
                    "tag_id": "04A224BC19",
                    "reader_id": "pn532_i2c",
                    "timestamp": "2026-02-16T22:48:00Z",
                },
                {
                    "tag_present": False,
                    "tag_id": None,
                    "reader_id": "pn532_i2c",
                    "timestamp": "2026-02-16T22:48:10Z",
                },
            ]
        }
    )


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
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 timestamp of the status.",
    )

    model_config = ConfigDict(
        json_schema_extra={
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
    )
