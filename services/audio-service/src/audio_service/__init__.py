"""Minabox Audio Service - VLC-based audio player with MQTT control.

This service provides audio playback functionality controlled via MQTT,
using VLC as the underlying audio backend.
"""

__version__ = "0.1.0"
__author__ = "Minabox Project"

from .config_manager import ConfigManager
from .config_schema import AppConfig, AudioConfig, EnvConfig
from .exceptions import (
    AudioError,
    ConfigUpdateError,
    MinaboxAudioError,
    MQTTError,
    PlaybackError,
    VLCError,
)

__all__ = [
    "ConfigManager",
    "AppConfig",
    "EnvConfig",
    "AudioConfig",
    "MinaboxAudioError",
    "AudioError",
    "PlaybackError",
    "VLCError",
    "MQTTError",
    "ConfigUpdateError",
]
