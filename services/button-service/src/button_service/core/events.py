from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


EventType = Literal[
    "short_press",
    "long_press",
    "double_press",
    "rotate_cw",
    "rotate_ccw",
    "press",  # encoder switch
]


@dataclass(frozen=True, slots=True)
class RawButtonEvent:
    """Normalized raw input event produced by hardware layer.

    This event is *before* mapping to logical actions.
    """

    source_id: str
    event_type: EventType
    timestamp: datetime

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

