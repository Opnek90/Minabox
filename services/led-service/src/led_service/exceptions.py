"""Exception hierarchy for the LED service.

All custom exceptions inherit from MinaboxLEDError to allow catching
service-specific errors separately from standard Python exceptions.
"""

from __future__ import annotations

from shared_lib.exceptions import MinaboxError


class MinaboxLEDError(MinaboxError):
    """Base exception for all LED service errors."""


class HardwareError(MinaboxLEDError):
    """Hardware communication or initialization failed."""


class GPIOControlError(HardwareError):
    """GPIO pin control operation failed."""


class ConfigurationError(MinaboxLEDError):
    """Configuration-related errors."""


class InvalidPatternError(ConfigurationError):
    """LED pattern configuration is invalid or unsupported."""


class StateError(MinaboxLEDError):
    """State management errors."""
