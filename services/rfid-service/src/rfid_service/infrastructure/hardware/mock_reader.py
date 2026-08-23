"""Mock RFID reader for running the service without hardware."""

from __future__ import annotations

from typing import Any, Literal

import structlog

from .reader_interface import RFIDReader

logger = structlog.get_logger(__name__)


class MockReader(RFIDReader):
    """Mock RFID reader for development and testing.

    Simulates a realistic tag rhythm instead of a new tag on every read: each
    configured tag is reported for ``hold_reads`` consecutive reads (the tag
    resting on the reader), followed by ``gap_reads`` empty reads (the reader
    being free) before the next tag appears.
    """

    def __init__(
        self,
        interface: Literal["i2c", "spi", "uart"],
        **kwargs: Any,
    ) -> None:
        """Initialize the mock reader.

        Parameters
        ----------
        interface:
            Hardware interface type (ignored by the mock).
        kwargs:
            ``config``: a :class:`MockReaderConfig` with the tag list and the
            hold/gap read counts. ``reader_id``: custom reader identifier.
        """
        from ...config_schema import MockReaderConfig

        config: MockReaderConfig = kwargs.get("config") or MockReaderConfig()

        self._interface = interface
        self._config = config
        self._tags: list[str] = list(config.tags)
        self._reader_id: str = str(kwargs.get("reader_id", f"mock_{interface}"))

        self._tag_index = 0
        self._read_count = 0
        self._initialized = False

        logger.info(
            "mock_reader_created",
            reader_id=self._reader_id,
            mock_tags_count=len(self._tags),
            hold_reads=config.hold_reads,
            gap_reads=config.gap_reads,
        )

    def initialize(self) -> None:
        """Initialize the mock reader (no-op)."""
        self._initialized = True
        logger.info("mock_reader_initialized", reader_id=self._reader_id)

    def read_tag_uid(self) -> str | None:
        """Return the simulated reader state for this read.

        Returns the current tag while inside its hold window, None while inside
        the gap window, and advances to the next tag afterwards. Always returns
        None when no tags are configured.
        """
        if not self._initialized:
            logger.warning("mock_reader_not_initialized", reader_id=self._reader_id)
            return None

        if not self._tags:
            return None

        hold = self._config.hold_reads
        gap = self._config.gap_reads
        # Captured before advancing, so the value returned belongs to the cycle
        # this read is part of and not to the next one.
        position = self._read_count
        tag_index = self._tag_index

        self._read_count += 1
        if self._read_count >= hold + gap:
            self._read_count = 0
            self._tag_index = (self._tag_index + 1) % len(self._tags)

        if position >= hold:
            return None

        uid = self._tags[tag_index]
        logger.debug("mock_tag_read", uid=uid, reader_id=self._reader_id)
        return uid

    def cleanup(self) -> None:
        """Clean up the mock reader (no-op)."""
        self._initialized = False
        logger.info("mock_reader_cleanup", reader_id=self._reader_id)

    @property
    def reader_id(self) -> str:
        """Return the mock reader identifier."""
        return self._reader_id
