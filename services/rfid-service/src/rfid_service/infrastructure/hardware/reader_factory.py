"""Factory for creating RFID reader instances based on configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from shared_lib.exceptions import ConfigError
from .mock_reader import MockReader
from .reader_interface import RFIDReader

if TYPE_CHECKING:
    from ...config_schema import ReaderConfig

logger = structlog.get_logger(__name__)


def create_reader(config: ReaderConfig) -> RFIDReader:
    """Create an RFID reader instance based on configuration.

    Parameters
    ----------
    config:
        Reader configuration from service.json.

    Returns
    -------
    RFIDReader
        Configured reader instance.

    Raises
    ------
    ConfigError
        If reader_type is unsupported or reader initialization fails.

    Examples
    --------
    Adding a new reader type (e.g., RC522):

    1. Create rc522_reader.py implementing RFIDReader
    2. Add import: from .rc522_reader import RC522Reader
    3. Add case in the if/elif chain below
    4. Update config_schema.py: Literal["pn532", "rc522", "mock"]
    """
    reader_type = config.reader_type
    interface = config.interface

    logger.info(
        "creating_reader",
        reader_type=reader_type,
        interface=interface,
    )

    if reader_type == "mock":
        # Mock reader doesn't need hardware libraries
        return MockReader(
            interface=interface,
            reader_id=f"mock_{interface}",
            mock_tags=["04A224BC19", "DEADBEEF01"],  # Default test tags
        )

    elif reader_type == "pn532":
        # PN532 reader - lazy import to avoid requiring the library
        # on systems that don't have PN532 hardware
        try:
            from .pn532_reader import PN532Reader
        except ImportError as exc:
            msg = (
                f"Cannot load {reader_type} reader. "
                "Install with: pip install pn532pi"
            )
            logger.error("reader_import_failed", reader_type=reader_type, error=str(exc))
            raise ConfigError(msg) from exc

        return PN532Reader(interface=interface)

    # Future: Add more reader types here
    # elif reader_type == "rc522":
    #     from .rc522_reader import RC522Reader
    #     return RC522Reader(interface=interface)

    else:
        msg = f"Unsupported reader_type: {reader_type}"
        logger.error("unsupported_reader_type", reader_type=reader_type)
        raise ConfigError(msg)
