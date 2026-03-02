from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages."""

    type: str = Field(
        ...,
        description="Message type (e.g., audio_status, rfid_scanned)",
    )
    data: dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


__all__ = ["WebSocketMessage"]

