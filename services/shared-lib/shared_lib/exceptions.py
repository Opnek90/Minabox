"""Shared exception base for all Minabox services.

Services should define their own base (e.g. MinaboxLEDError) inheriting from
MinaboxError, and keep service-specific exceptions in their own exceptions.py.
"""

from __future__ import annotations


class MinaboxError(Exception):
    """Base exception for all Minabox service errors.

    Use this in shared code. Each service can define a service-specific base
    (e.g. MinaboxLEDError(MinaboxError)) and use it for domain exceptions.
    """


class ConfigError(MinaboxError):
    """Raised when configuration cannot be loaded or validated.

    Services can use this directly or subclass (e.g. ConfigUpdateError).
    """


class ConfigLoadError(ConfigError):
    """Raised when configuration file loading fails (read/parse/validate)."""
