"""Backward-compatible re-export from schemas.py.

All event models have been moved to schemas.py to follow the
Framework convention (models/schemas.py). This file remains for
backward compatibility and will be removed in a future cleanup.
"""

from __future__ import annotations

from .schemas import (  # noqa: F401
    RFIDStatusEvent,
    TagRemovedEvent,
    TagScannedEvent,
    TagScannedLearningEvent,
)
