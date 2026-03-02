from __future__ import annotations

from enum import Enum


class ContentType(str, Enum):
    """Content type for RFID tag mapping."""

    PLAYLIST = "playlist"
    TRACK = "track"
    STREAM = "stream"
    PODCAST = "podcast"


class SourceType(str, Enum):
    """Source type for audio tracks (file = local, remote = NAS/DLNA/CIFS/NFS/SMB)."""

    FILE = "file"
    REMOTE = "remote"


class AudioState(str, Enum):
    """Audio playback state."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


class ServiceState(str, Enum):
    """Service health state."""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class RFIDMode(str, Enum):
    """RFID reader mode."""

    NORMAL = "normal"
    LEARNING = "learning"


__all__ = [
    "ContentType",
    "SourceType",
    "AudioState",
    "ServiceState",
    "RFIDMode",
]

