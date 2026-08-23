"""Exception hierarchy for the RFID service."""

from __future__ import annotations

from shared_lib.exceptions import MinaboxError


class MinaboxRFIDError(MinaboxError):
    """Base exception for all RFID service errors."""


class HardwareError(MinaboxRFIDError):
    """Hardware communication or initialization failed."""


class ReaderNotFoundError(HardwareError):
    """RFID reader hardware not detected or accessible."""


class ReaderInitError(HardwareError):
    """Reader initialization failed."""


class ProtocolError(HardwareError):
    """Unexpected or invalid response from the reader."""
