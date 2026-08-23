"""Factory for creating RFID reader instances based on configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
        Reader configuration from ``config/rfid.json``.

    Returns
    -------
    RFIDReader
        Configured reader instance. The instance is constructed only; the
        caller is responsible for calling :meth:`RFIDReader.initialize`.

    Raises
    ------
    ConfigError
        If reader_type is unsupported or the reader library is missing.

    Examples
    --------
    Adding a new reader type (e.g. RC522):

    1. Create rc522_reader.py implementing RFIDReader
    2. Add a branch below that constructs it from its own config section
    3. Update config_schema.py: Literal["pn532", "rc522", "mock"]
    """
    reader_type = config.reader_type
    interface = config.interface

    logger.info(
        "creating_reader",
        reader_type=reader_type,
        interface=interface,
    )

    if reader_type == "mock":
        # The mock reader needs no hardware libraries.
        return MockReader(
            interface=interface,
            reader_id=f"mock_{interface}",
            config=config.mock,
        )

    if reader_type == "pn532":
        # Imported lazily so a system without PN532 hardware can still run the
        # service with the mock reader.
        try:
            from .pn532_reader import PN532Reader
        except ImportError as exc:
            msg = (
                f"Cannot load {reader_type} reader. Install with: pip install pn532pi"
            )
            logger.error(
                "reader_import_failed", reader_type=reader_type, error=str(exc)
            )
            raise ConfigError(msg) from exc

        return PN532Reader(interface=interface, config=config.pn532)

    msg = f"Unsupported reader_type: {reader_type}"
    logger.error("unsupported_reader_type", reader_type=reader_type)
    raise ConfigError(msg)
