"""Environment-variable parsing in config.py."""

from __future__ import annotations

from pathlib import Path

from tts_service.config import load_config

ENV_VARS = (
    "PIPER_BINARY",
    "PIPER_ESPEAK_DATA",
    "PIPER_VOICES_DIR",
    "TTS_CACHE_DIR",
    "TTS_CACHE_MAX_FILES",
    "TTS_CACHE_MAX_BYTES",
    "TTS_TIMEOUT_SEC",
    "TTS_MAX_TEXT_LENGTH",
    "LOG_LEVEL",
)


def test_defaults_when_unset(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config = load_config()
    assert config.piper_binary == Path("/opt/piper/piper")
    assert config.voices_dir == Path("/opt/piper/voices")
    assert config.cache_dir == Path("/announcements")
    assert config.cache_max_files == 500
    assert config.log_level == "INFO"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("TTS_CACHE_DIR", "/tmp/clips")
    monkeypatch.setenv("TTS_CACHE_MAX_FILES", "12")
    monkeypatch.setenv("TTS_TIMEOUT_SEC", "2.5")
    config = load_config()
    assert config.cache_dir == Path("/tmp/clips")
    assert config.cache_max_files == 12
    assert config.synthesis_timeout_sec == 2.5
