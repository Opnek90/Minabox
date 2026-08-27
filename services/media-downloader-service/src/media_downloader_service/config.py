"""Configuration for the Media Downloader Service."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


class MediaDownloaderConfig(BaseModel):
    """Service configuration loaded from environment variables."""

    audio_tracks_dir: Path = Field(
        default=Path("/mnt/audio/tracks/downloads"),
        description="Default target directory for MP3 files, used when the caller omits output_dir",
    )
    audio_base_dir: Path = Field(
        default=Path("/mnt/audio"),
        description="Shared audio volume mount point; output_dir must resolve inside it",
    )
    audio_quality: str = Field(
        default="192",
        description="MP3 bitrate in kbps",
    )
    max_filesize_mb: int = Field(
        default=200,
        description="Maximum size of a downloaded file, in megabytes",
    )
    log_level: str = Field(default="INFO")


def load_config() -> MediaDownloaderConfig:
    """Load config from environment variables."""
    return MediaDownloaderConfig(
        audio_tracks_dir=Path(
            os.environ.get("AUDIO_TRACKS_DIR", "/mnt/audio/tracks/downloads")
        ),
        audio_base_dir=Path(os.environ.get("AUDIO_BASE_DIR", "/mnt/audio")),
        audio_quality=os.environ.get("AUDIO_QUALITY", "192"),
        max_filesize_mb=int(os.environ.get("MAX_FILESIZE_MB", "200")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
