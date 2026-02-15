"""Data models for the Backend Service.

This package contains Pydantic schemas for API requests/responses.
Database models (SQLAlchemy) are in a separate module.
"""

from backend_service.models.schemas import (
    AudioConfig,
    # Audio Control
    AudioPlayCommand,
    AudioStatusResponse,
    AudioVolumeCommand,
    # Config
    ButtonConfig,
    # Error
    ErrorResponse,
    # System
    HealthCheckResponse,
    LEDConfig,
    # Playlists
    PlaylistBase,
    PlaylistCreate,
    PlaylistDetailResponse,
    PlaylistResponse,
    PlaylistUpdate,
    RFIDConfig,
    # RFID
    RFIDLearningModeCommand,
    RFIDScanEvent,
    ServiceStatus,
    SystemStatusResponse,
    # Tags
    TagBase,
    TagCreate,
    TagResponse,
    TagUpdate,
    # Tracks
    TrackBase,
    TrackCreate,
    TrackResponse,
    # WebSocket
    WebSocketMessage,
)

__all__ = [
    # Tags
    "TagBase",
    "TagCreate",
    "TagUpdate",
    "TagResponse",
    # Playlists
    "PlaylistBase",
    "PlaylistCreate",
    "PlaylistUpdate",
    "PlaylistResponse",
    "PlaylistDetailResponse",
    # Tracks
    "TrackBase",
    "TrackCreate",
    "TrackResponse",
    # Audio Control
    "AudioPlayCommand",
    "AudioVolumeCommand",
    "AudioStatusResponse",
    # RFID
    "RFIDLearningModeCommand",
    "RFIDScanEvent",
    # Config
    "ButtonConfig",
    "LEDConfig",
    "AudioConfig",
    "RFIDConfig",
    # System
    "HealthCheckResponse",
    "SystemStatusResponse",
    "ServiceStatus",
    # WebSocket
    "WebSocketMessage",
    # Error
    "ErrorResponse",
]
