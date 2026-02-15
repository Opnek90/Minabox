"""Exception hierarchy for Backend Service."""


class MinaboxError(Exception):
    """Base exception for all Minabox errors."""

    pass


class ServiceCommunicationError(MinaboxError):
    """Service communication failed."""

    pass


class MQTTConnectionError(ServiceCommunicationError):
    """MQTT broker not reachable."""

    pass


class MQTTPublishError(ServiceCommunicationError):
    """Failed to publish MQTT message."""

    pass


class DatabaseError(MinaboxError):
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


class ValidationError(MinaboxError):
    """Data validation error."""

    pass


class ConfigValidationError(ValidationError):
    """Configuration validation failed."""

    pass


class FileUploadError(MinaboxError):
    """File upload failed."""

    pass


class MetadataExtractionError(MinaboxError):
    """Audio metadata extraction failed (non-critical)."""

    pass


class SessionError(MinaboxError):
    """Playback session error."""

    pass


class NoActiveSessionError(SessionError):
    """No active playback session."""

    pass
