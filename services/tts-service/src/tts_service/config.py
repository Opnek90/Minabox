"""Configuration for the TTS Service.

Everything comes from the environment; there is no config file. The service
holds no user decision of its own - which announcements are spoken at all, and
in which language, is decided in the backend (``core/announcements.py``) and
travels with every request.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class TTSConfig(BaseModel):
    """Service configuration loaded from environment variables."""

    piper_binary: Path = Field(
        default=Path("/opt/piper/piper"),
        description="The Piper executable bundled in this image",
    )
    espeak_data_dir: Path = Field(
        default=Path("/opt/piper/espeak-ng-data"),
        description="Phoneme data Piper needs; ships in the same tarball",
    )
    voices_dir: Path = Field(
        default=Path("/opt/piper/voices"),
        description="Where the bundled .onnx voices live",
    )
    cache_dir: Path = Field(
        default=Path("/announcements"),
        description=(
            "Shared volume the audio service reads the finished clips from. "
            "Mounted at the same path in both containers, so the path in the "
            "answer is the path the audio service can open."
        ),
    )
    #: Upper bound for the cache. A phrase is a second or two of 16-bit mono
    #: WAV - a few hundred kilobytes at most - so this is generous for a box
    #: whose card collection is measured in dozens.
    cache_max_files: int = Field(default=500)
    cache_max_bytes: int = Field(default=64 * 1024 * 1024)
    #: Measured on a Raspberry Pi 4: 1.5 - 2.3 s for a phrase once the process
    #: is running, and about 7 s for the first one, which pays for loading the
    #: model. Ten seconds is not a budget, it is the point past which Piper is
    #: not slow but stuck.
    synthesis_timeout_sec: float = Field(default=10.0)
    max_text_length: int = Field(default=280)
    log_level: str = Field(default="INFO")


def load_config() -> TTSConfig:
    """Read the configuration from the environment."""
    return TTSConfig(
        piper_binary=Path(os.environ.get("PIPER_BINARY", "/opt/piper/piper")),
        espeak_data_dir=Path(
            os.environ.get("PIPER_ESPEAK_DATA", "/opt/piper/espeak-ng-data")
        ),
        voices_dir=Path(os.environ.get("PIPER_VOICES_DIR", "/opt/piper/voices")),
        cache_dir=Path(os.environ.get("TTS_CACHE_DIR", "/announcements")),
        cache_max_files=int(os.environ.get("TTS_CACHE_MAX_FILES", "500")),
        cache_max_bytes=int(
            os.environ.get("TTS_CACHE_MAX_BYTES", str(64 * 1024 * 1024))
        ),
        synthesis_timeout_sec=float(os.environ.get("TTS_TIMEOUT_SEC", "10")),
        max_text_length=int(os.environ.get("TTS_MAX_TEXT_LENGTH", "280")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
