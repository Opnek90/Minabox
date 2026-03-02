"""Exceptions for the display service."""

from __future__ import annotations

from shared_lib.exceptions import MinaboxError


class MinaboxDisplayError(MinaboxError):
    """Base exception for display service errors."""


class DisplayHardwareError(MinaboxDisplayError):
    """Raised when OLED hardware is unavailable or fails."""
