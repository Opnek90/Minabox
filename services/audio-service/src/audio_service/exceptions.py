"""Exception hierarchy for the Audio Service.

All custom exceptions inherit from MinaboxAudioError to allow
catching service-specific errors separately from standard Python exceptions.
"""

from __future__ import annotations

from shared_lib.exceptions import MinaboxError


class MinaboxAudioError(MinaboxError):
    """Base exception for all audio service errors."""

    pass


class AudioError(MinaboxAudioError):
    """Base exception for audio-related errors."""

    pass


class PlaybackError(AudioError):
    """Raised when audio playback fails."""

    pass


class VLCError(AudioError):
    """Raised when VLC backend encounters an error."""

    pass


class AudioFileNotFoundError(AudioError):
    """Raised when an audio source file is not found.

    Deliberately not named FileNotFoundError: that would shadow the builtin in
    every module importing it, and both routes.py and pulse_detector.py rely on
    catching the real builtin when a command is missing.
    """

    pass


class StreamUnreachableError(AudioError):
    """Raised when audio stream is unreachable."""

    pass


class OutputDeviceError(AudioError):
    """Raised when audio output device is unavailable or fails."""

    pass


class MQTTError(MinaboxAudioError):
    """Base exception for MQTT-related errors."""

    pass


class MQTTConnectionError(MQTTError):
    """Raised when MQTT broker connection fails."""

    pass


class MQTTPublishError(MQTTError):
    """Raised when MQTT message publishing fails."""

    pass


class ConfigUpdateError(MinaboxAudioError):
    """Raised when configuration update fails."""

    pass


class StateError(MinaboxAudioError):
    """Raised when state management encounters an error."""

    pass
