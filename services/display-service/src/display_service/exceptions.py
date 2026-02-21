"""Exceptions for the display service."""

from __future__ import annotations


class MinaboxDisplayError(Exception):
    """Base exception for display service errors."""


class ConfigError(MinaboxDisplayError):
    """Raised when configuration cannot be loaded or validated."""


class DisplayHardwareError(MinaboxDisplayError):
    """Raised when OLED hardware is unavailable or fails."""
