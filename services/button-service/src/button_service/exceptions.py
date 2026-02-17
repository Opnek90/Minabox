"""Exception hierarchy for the button service.

All custom exceptions inherit from MinaboxButtonError to allow catching
service-specific errors separately from standard Python exceptions.
"""


class MinaboxButtonError(Exception):
    """Base exception for all button service errors."""
    pass


class HardwareError(MinaboxButtonError):
    """Hardware communication or initialization failed."""
    pass


class GPIOInitError(HardwareError):
    """GPIO pin could not be initialized."""
    pass


class ButtonReadError(HardwareError):
    """Button or encoder read operation failed."""
    pass


class RotaryEncoderError(HardwareError):
    """Rotary encoder hardware error."""
    pass


class ConfigurationError(MinaboxButtonError):
    """Configuration-related errors."""
    pass


class InvalidButtonConfigError(ConfigurationError):
    """Button configuration is invalid or unsupported."""
    pass


class InvalidButtonTypeError(ConfigurationError):
    """Button type is not supported."""
    pass


class StateError(MinaboxButtonError):
    """State machine or event processing errors."""
    pass


class UnknownEventTypeError(StateError):
    """Event type is not recognized."""
    pass


class MappingError(MinaboxButtonError):
    """Error mapping button events to actions."""
    pass
