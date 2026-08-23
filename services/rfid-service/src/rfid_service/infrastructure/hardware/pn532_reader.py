"""PN532 RFID reader implementation using the pn532pi library."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import structlog

from ...exceptions import ProtocolError, ReaderInitError, ReaderNotFoundError
from .reader_interface import RFIDReader

if TYPE_CHECKING:
    from ...config_schema import PN532Config

logger = structlog.get_logger(__name__)

#: Baud rate constant of the pn532pi library for MIFARE / ISO14443A tags.
PN532_MIFARE_ISO14443A = 0x00


class PN532Reader(RFIDReader):
    """PN532 NFC/RFID reader implementation.

    Uses the pn532pi library for Raspberry Pi hardware communication.
    Supports I2C, SPI, and UART interfaces.
    """

    def __init__(
        self,
        interface: Literal["i2c", "spi", "uart"],
        **kwargs: Any,
    ) -> None:
        """Initialize the PN532 reader.

        Parameters
        ----------
        interface:
            Hardware interface type.
        kwargs:
            ``config``: a :class:`PN532Config` with the bus/port settings and
            the passive activation retry count.

        Raises
        ------
        ReaderInitError
            If the pn532pi library is not installed or the interface is unknown.
        """
        from ...config_schema import PN532Config

        config: PN532Config = kwargs.get("config") or PN532Config()

        self._interface = interface
        self._config = config
        self._reader: Any | None = None
        self._reader_id = f"pn532_{interface}"

        try:
            from pn532pi import Pn532, Pn532Hsu, Pn532I2c, Pn532Spi
        except ImportError as exc:
            msg = "pn532pi library not installed. Install with: pip install pn532pi"
            logger.error("pn532_import_failed", error=str(exc))
            raise ReaderInitError(msg) from exc

        # Create the interface-specific communication object.
        if interface == "i2c":
            self._comm: Any = Pn532I2c(config.i2c_bus)
        elif interface == "spi":
            self._comm = Pn532Spi(config.spi_device)
        elif interface == "uart":
            self._comm = Pn532Hsu(config.uart_port)
        else:
            msg = f"Unsupported interface: {interface}"
            raise ReaderInitError(msg)

        self._reader = Pn532(self._comm)
        logger.info(
            "pn532_reader_created",
            interface=interface,
            reader_id=self._reader_id,
        )

    def initialize(self) -> None:
        """Initialize the PN532 reader hardware.

        Raises
        ------
        ReaderNotFoundError
            If the reader does not answer the firmware version request.
        ReaderInitError
            If any other step of the initialisation fails.
        """
        if self._reader is None:
            msg = "Reader not constructed"
            raise ReaderInitError(msg)

        try:
            self._reader.begin()
            # Reading the firmware version proves the bus wiring works.
            version = self._reader.getFirmwareVersion()
        except Exception as exc:
            logger.error(
                "pn532_init_failed",
                error=str(exc),
                reader_id=self._reader_id,
            )
            raise ReaderInitError(f"PN532 initialization failed: {exc}") from exc

        # Raised outside the try block so it stays a ReaderNotFoundError instead
        # of being caught and re-wrapped as a generic ReaderInitError.
        if version is None:
            logger.error("pn532_init_no_response", reader_id=self._reader_id)
            raise ReaderNotFoundError("Failed to communicate with PN532")

        try:
            # Switches the chip into normal operation and turns on the RF field.
            self._reader.SAMConfig()

            # Bounds how long a read blocks: after this many activation attempts
            # the read call returns "no tag" instead of waiting indefinitely.
            self._reader.setPassiveActivationRetries(
                self._config.passive_activation_retries
            )
        except Exception as exc:
            logger.error(
                "pn532_configure_failed",
                error=str(exc),
                reader_id=self._reader_id,
            )
            raise ReaderInitError(f"PN532 configuration failed: {exc}") from exc

        logger.info(
            "pn532_initialized",
            firmware_version=f"{version:08x}",
            passive_activation_retries=self._config.passive_activation_retries,
            reader_id=self._reader_id,
        )

    def read_tag_uid(self) -> str | None:
        """Read a tag UID from the PN532.

        This call blocks for the duration of the hardware transaction, so the
        scan loop runs it in a worker thread.

        Returns
        -------
        str | None
            Tag UID as an uppercase hex string without separators, or None if
            no tag is present.

        Raises
        ------
        ProtocolError
            If communication with the reader fails.
        """
        if self._reader is None:
            msg = "Reader not initialized"
            raise ProtocolError(msg)

        try:
            # readPassiveTargetID returns (success, uid_bytes).
            success, uid = self._reader.readPassiveTargetID(
                cardbaudrate=PN532_MIFARE_ISO14443A
            )
            if not success or uid is None:
                return None

            uid_hex = "".join(f"{byte:02X}" for byte in uid)
            logger.debug("pn532_tag_read", uid=uid_hex, reader_id=self._reader_id)
            return uid_hex

        except Exception as exc:
            logger.error(
                "pn532_read_failed",
                error=str(exc),
                reader_id=self._reader_id,
            )
            raise ProtocolError(f"PN532 read failed: {exc}") from exc

    def cleanup(self) -> None:
        """Release PN532 hardware resources."""
        if self._reader is not None:
            logger.info("pn532_cleanup", reader_id=self._reader_id)
            # pn532pi has no explicit teardown; dropping the reference is all
            # we can do.
            self._reader = None

    @property
    def reader_id(self) -> str:
        """Return the reader identifier."""
        return self._reader_id
