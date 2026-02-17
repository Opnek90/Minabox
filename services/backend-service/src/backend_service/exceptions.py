"""Exception hierarchy for the Backend Service.

All custom exceptions inherit from MinaboxBackendError to allow
catching service-specific errors separately from standard Python exceptions.
"""


from __future__ import annotations

class MinaboxBackendError(Exception):
    """Base exception for all backend service errors."""

    pass


class ServiceCommunicationError(MinaboxBackendError):
    """Service communication failed."""

    pass


class MQTTConnectionError(ServiceCommunicationError):
    """MQTT broker not reachable."""

    pass


class MQTTPublishError(ServiceCommunicationError):
    """Failed to publish MQTT message."""

    pass


class DatabaseError(MinaboxBackendError):
    """Database-related error."""

    pass


class TagNotFoundError(DatabaseError):
    """RFID tag not found in database."""

    pass


class ContentNotFoundError(DatabaseError):
    """Referenced content (playlist/track) not found."""

    pass


class PlaylistNotFoundError(DatabaseError):
    """Playlist not found in database."""

    pass


class TrackNotFoundError(DatabaseError):
    """Track not found in database."""

    pass


class ValidationError(MinaboxBackendError):
    """Data validation error."""

    pass


class ConfigValidationError(ValidationError):
    """Configuration validation failed."""

    pass


class FileUploadError(MinaboxBackendError):
    """File upload failed."""

    pass


class MetadataExtractionError(MinaboxBackendError):
    """Audio metadata extraction failed (non-critical)."""

    pass


class SessionError(MinaboxBackendError):
    """Playback session error."""

    pass


class NoActiveSessionError(SessionError):
    """No active playback session."""

    pass
