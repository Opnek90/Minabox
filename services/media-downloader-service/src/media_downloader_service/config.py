"""Configuration for the Media Downloader Service."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


class MediaDownloaderConfig(BaseModel):
    """Service configuration loaded from environment variables."""

    audio_tracks_dir: Path = Field(
        default=Path("/mnt/audio/tracks/downloads"),
        description="Target directory for downloaded MP3 files",
    )
    audio_quality: str = Field(
        default="192",
        description="MP3 bitrate in kbps",
    )
    service_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")


def load_config() -> MediaDownloaderConfig:
    """Load config from environment variables."""
    return MediaDownloaderConfig(
        audio_tracks_dir=Path(
            os.environ.get("AUDIO_TRACKS_DIR", "/mnt/audio/tracks/downloads")
        ),
        audio_quality=os.environ.get("AUDIO_QUALITY", "192"),
        service_port=int(os.environ.get("SERVICE_PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
