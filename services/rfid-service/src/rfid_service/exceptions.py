"""Exception hierarchy for the RFID service."""

from __future__ import annotations


class MinaboxRFIDError(Exception):
    """Base exception for all RFID service errors."""


class HardwareError(MinaboxRFIDError):
    """Hardware communication or initialization failed."""


class ReaderNotFoundError(HardwareError):
    """RFID reader hardware not detected or accessible."""


class ReaderInitError(HardwareError):
    """Reader initialization failed."""


class ReadTimeoutError(HardwareError):
    """Reading a tag timed out after multiple retries."""


class ProtocolError(HardwareError):
    """Unexpected or invalid response from the reader."""


class ConfigError(MinaboxRFIDError):
    """Configuration loading or validation failed."""
