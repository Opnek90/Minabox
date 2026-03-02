"""Abstract interface for RFID reader implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal


class RFIDReader(ABC):
    """Abstract base class for RFID reader hardware.

    Implementations must provide methods for initialization, tag reading,
    and cleanup. This abstraction allows supporting different reader types
    (PN532, RC522, etc.) with a unified interface.
    """

    @abstractmethod
    def __init__(
        self,
        interface: Literal["i2c", "spi", "uart"],
        **kwargs: object,
    ) -> None:
        """Initialize the reader with the specified interface.

        Parameters
        ----------
        interface:
            Hardware interface type (i2c, spi, or uart).
        kwargs:
            Additional interface-specific configuration.
        """

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the reader hardware.

        Raises
        ------
        ReaderNotFoundError
            If the reader hardware is not detected.
        ReaderInitError
            If initialization fails.
        """

    @abstractmethod
    def read_tag_uid(self) -> str | None:
        """Attempt to read a tag UID.

        Returns
        -------
        str | None
            Tag UID as hex string (e.g., "04A224BC19") if a tag is present,
            None if no tag is detected.

        Raises
        ------
        ProtocolError
            If communication with the reader fails.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Release hardware resources and perform cleanup."""

    @property
    @abstractmethod
    def reader_id(self) -> str:
        """Return a unique identifier for this reader instance."""
