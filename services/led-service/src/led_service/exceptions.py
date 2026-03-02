"""Exception hierarchy for the LED service.

All custom exceptions inherit from MinaboxLEDError to allow catching
service-specific errors separately from standard Python exceptions.
"""

from __future__ import annotations

from shared_lib.exceptions import MinaboxError


class MinaboxLEDError(MinaboxError):
    """Base exception for all LED service errors."""
    pass


class HardwareError(MinaboxLEDError):
    """Hardware communication or initialization failed."""
    pass


class GPIOInitError(HardwareError):
    """GPIO pin could not be initialized."""
    pass


class GPIOControlError(HardwareError):
    """GPIO pin control operation failed."""
    pass


class ConfigurationError(MinaboxLEDError):
    """Configuration-related errors."""
    pass


class InvalidPatternError(ConfigurationError):
    """LED pattern configuration is invalid or unsupported."""
    pass


class StateError(MinaboxLEDError):
    """State management errors."""
    pass


class UnknownStateError(StateError):
    """Logical state is not recognized."""
    pass
