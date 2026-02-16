"""Exception hierarchy for the Audio Service.

All custom exceptions inherit from MinaboxError to allow
centralized error handling and logging.
"""


class MinaboxError(Exception):
    """Base exception for all Minabox Audio Service errors."""

    pass


class AudioError(MinaboxError):
    """Base exception for audio-related errors."""

    pass


class PlaybackError(AudioError):
    """Raised when audio playback fails."""

    pass


class VLCError(AudioError):
    """Raised when VLC backend encounters an error."""

    pass


class FileNotFoundError(AudioError):
    """Raised when audio source file is not found."""

    pass


class StreamUnreachableError(AudioError):
    """Raised when audio stream is unreachable."""

    pass


class OutputDeviceError(AudioError):
    """Raised when audio output device is unavailable or fails."""

    pass


class MQTTError(MinaboxError):
    """Base exception for MQTT-related errors."""

    pass


class MQTTConnectionError(MQTTError):
    """Raised when MQTT broker connection fails."""

    pass


class MQTTPublishError(MQTTError):
    """Raised when MQTT message publishing fails."""

    pass


class ConfigUpdateError(MinaboxError):
    """Raised when configuration update fails."""

    pass


class StateError(MinaboxError):
    """Raised when state management encounters an error."""

    pass
