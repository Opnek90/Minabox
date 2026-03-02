"""Mock RFID reader for testing without hardware."""

from __future__ import annotations

from typing import Literal

import structlog

from .reader_interface import RFIDReader

logger = structlog.get_logger(__name__)


class MockReader(RFIDReader):
    """Mock RFID reader for development and testing.

    Returns predefined tag UIDs in sequence or simulates empty reads.
    """

    def __init__(
        self,
        interface: Literal["i2c", "spi", "uart"],
        **kwargs: object,
    ) -> None:
        """Initialize mock reader.

        Parameters
        ----------
        interface:
            Hardware interface type (ignored in mock).
        kwargs:
            Optional keyword arguments:
            - mock_tags: List of tag UIDs to return in sequence
            - reader_id: Custom reader identifier
        """
        self._interface = interface
        self._mock_tags: list[str] = list(kwargs.get("mock_tags", []))
        self._reader_id: str = str(kwargs.get("reader_id", "mock_reader"))
        self._current_index = 0
        self._initialized = False

        logger.info(
            "mock_reader_created",
            reader_id=self._reader_id,
            mock_tags_count=len(self._mock_tags),
        )

    def initialize(self) -> None:
        """Initialize the mock reader (no-op)."""
        self._initialized = True
        logger.info("mock_reader_initialized", reader_id=self._reader_id)

    def read_tag_uid(self) -> str | None:
        """Return the next mock tag UID or None.

        Cycles through the mock_tags list. If the list is empty,
        always returns None.
        """
        if not self._initialized:
            logger.warning("mock_reader_not_initialized", reader_id=self._reader_id)
            return None

        if not self._mock_tags:
            return None

        uid = self._mock_tags[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._mock_tags)

        logger.debug("mock_tag_read", uid=uid, reader_id=self._reader_id)
        return uid

    def cleanup(self) -> None:
        """Clean up mock reader (no-op)."""
        self._initialized = False
        logger.info("mock_reader_cleanup", reader_id=self._reader_id)

    @property
    def reader_id(self) -> str:
        """Return mock reader identifier."""
        return self._reader_id
