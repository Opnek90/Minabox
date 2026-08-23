"""Pydantic schemas for REST API and internal data validation.

This module re-exports schemas from smaller, domain-focused modules to keep
imports stable (`backend_service.models.schemas.*`) while improving structure.
"""

from __future__ import annotations

from .schemas_audio import AudioPlayCommand, AudioStatusResponse, AudioVolumeCommand
from .schemas_content import (
    FolderCreate,
    FolderResponse,
    FolderUpdate,
    PlaylistBase,
    PlaylistCreate,
    PlaylistDetailResponse,
    PlaylistResponse,
    PlaylistUpdate,
    PodcastBase,
    PodcastCreate,
    PodcastEpisodeResponse,
    PodcastFolderCreate,
    PodcastFolderResponse,
    PodcastFolderUpdate,
    PodcastResponse,
    PodcastUpdate,
    StreamBase,
    StreamCreate,
    StreamFolderCreate,
    StreamFolderResponse,
    StreamFolderUpdate,
    StreamResponse,
    StreamUpdate,
    TagBase,
    TagCreate,
    TagResponse,
    TagUpdate,
    TrackBase,
    TrackCreate,
    TrackFolderCreate,
    TrackFolderResponse,
    TrackFolderUpdate,
    TrackResponse,
    TrackUpdate,
)
from .schemas_enums import (
    AudioState,
    ContentType,
    RFIDMode,
    ServiceState,
    SourceType,
)
from .schemas_error import ErrorDetail, ErrorResponse
from .schemas_rfid import RFIDLearningModeCommand, RFIDModeResponse, RFIDScanEvent
from .schemas_system import HealthCheckResponse, ServiceStatus, SystemStatusResponse
from .schemas_ws import WebSocketMessage

__all__ = [
    # Enums
    "ContentType",
    "SourceType",
    "AudioState",
    "ServiceState",
    "RFIDMode",
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
    # Streams
    "StreamBase",
    "StreamCreate",
    "StreamUpdate",
    "StreamResponse",
    # Podcasts
    "PodcastBase",
    "PodcastCreate",
    "PodcastUpdate",
    "PodcastResponse",
    "PodcastEpisodeResponse",
    # Folders (one shape for tracks, streams and podcasts)
    "FolderCreate",
    "FolderUpdate",
    "FolderResponse",
    # Track Folders
    "TrackFolderCreate",
    "TrackFolderUpdate",
    "TrackFolderResponse",
    # Stream Folders
    "StreamFolderCreate",
    "StreamFolderUpdate",
    "StreamFolderResponse",
    # Podcast Folders
    "PodcastFolderCreate",
    "PodcastFolderUpdate",
    "PodcastFolderResponse",
    # Tracks
    "TrackBase",
    "TrackCreate",
    "TrackUpdate",
    "TrackResponse",
    # Audio control & status
    "AudioPlayCommand",
    "AudioVolumeCommand",
    "AudioStatusResponse",
    # RFID
    "RFIDLearningModeCommand",
    "RFIDScanEvent",
    "RFIDModeResponse",
    # System & health
    "HealthCheckResponse",
    "ServiceStatus",
    "SystemStatusResponse",
    # WebSocket
    "WebSocketMessage",
    # Error
    "ErrorDetail",
    "ErrorResponse",
]
