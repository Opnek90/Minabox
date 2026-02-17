"""Data models for RFID service events and messages."""

from __future__ import annotations

from .schemas import (
    RFIDStatusEvent,
    TagRemovedEvent,
    TagScannedEvent,
    TagScannedLearningEvent,
)

__all__ = [
    "TagScannedEvent",
    "TagScannedLearningEvent",
    "TagRemovedEvent",
    "RFIDStatusEvent",
]
