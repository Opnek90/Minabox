"""Tests for environment-variable parsing in config.py."""

from __future__ import annotations

from pathlib import Path

from media_downloader_service.config import load_config


def test_defaults_when_unset(monkeypatch):
    env_vars = (
        "AUDIO_TRACKS_DIR",
        "AUDIO_BASE_DIR",
        "AUDIO_QUALITY",
        "MAX_FILESIZE_MB",
        "LOG_LEVEL",
    )
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    config = load_config()
    assert config.audio_tracks_dir == Path("/mnt/audio/tracks/downloads")
    assert config.audio_base_dir == Path("/mnt/audio")
    assert config.audio_quality == "192"
    assert config.max_filesize_mb == 200
    assert config.log_level == "INFO"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AUDIO_BASE_DIR", "/custom/audio")
    monkeypatch.setenv("MAX_FILESIZE_MB", "50")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    config = load_config()
    assert config.audio_base_dir == Path("/custom/audio")
    assert config.max_filesize_mb == 50
    assert config.log_level == "debug"
