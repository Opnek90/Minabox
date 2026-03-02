"""PN532 RFID reader implementation using pn532pi library."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from ...exceptions import ProtocolError, ReaderInitError, ReaderNotFoundError
from .reader_interface import RFIDReader

if TYPE_CHECKING:
    from pn532pi import Pn532

logger = structlog.get_logger(__name__)


class PN532Reader(RFIDReader):
    """PN532 NFC/RFID reader implementation.

    Uses the pn532pi library for Raspberry Pi hardware communication.
    Supports I2C, SPI, and UART interfaces.
    """

    def __init__(
        self,
        interface: Literal["i2c", "spi", "uart"],
        **kwargs: object,
    ) -> None:
        """Initialize PN532 reader.

        Parameters
        ----------
        interface:
            Hardware interface type.
        kwargs:
            Interface-specific options:
            - i2c_bus: I2C bus number (default: 1)
            - spi_device: SPI device (default: 0)
            - uart_port: UART port (default: "/dev/ttyS0")

        Raises
        ------
        ReaderInitError
            If pn532pi library is not installed.
        """
        self._interface = interface
        self._kwargs = kwargs
        self._reader: Pn532 | None = None
        self._reader_id = f"pn532_{interface}"

        try:
            from pn532pi import Pn532, Pn532I2c, Pn532Spi, Pn532Hsu
        except ImportError as exc:
            msg = (
                "pn532pi library not installed. "
                "Install with: pip install pn532pi"
            )
            logger.error("pn532_import_failed", error=str(exc))
            raise ReaderInitError(msg) from exc

        # Create interface-specific communication object
        if interface == "i2c":
            i2c_bus = kwargs.get("i2c_bus", 1)
            self._comm = Pn532I2c(i2c_bus)
        elif interface == "spi":
            spi_device = kwargs.get("spi_device", 0)
            self._comm = Pn532Spi(spi_device)
        elif interface == "uart":
            uart_port = kwargs.get("uart_port", "/dev/ttyS0")
            self._comm = Pn532Hsu(uart_port)
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
        """Initialize the PN532 reader hardware."""
        if self._reader is None:
            msg = "Reader not constructed"
            raise ReaderInitError(msg)

        try:
            self._reader.begin()
            # Get firmware version to verify communication
            version = self._reader.getFirmwareVersion()
            if version is None:
                msg = "Failed to communicate with PN532"
                logger.error("pn532_init_no_response")
                raise ReaderNotFoundError(msg)

            # WICHTIG: Aktiviert den Normalbetrieb (schaltet das RF-Feld ein)
            self._reader.SAMConfig()
            
            # WICHTIG: Verhindert endloses Blockieren in der Leseschleife. 
            # 0x02 = max. 2 Versuche, danach gibt die Lesefunktion False zurück.
            self._reader.setPassiveActivationRetries(0x02)

            logger.info(
                "pn532_initialized",
                firmware_version=f"{version:08x}",
                reader_id=self._reader_id,
            )
        except Exception as exc:
            logger.error(
                "pn532_init_failed",
                error=str(exc),
                reader_id=self._reader_id,
            )
            raise ReaderInitError(f"PN532 initialization failed: {exc}") from exc

    def read_tag_uid(self) -> str | None:
        """Read tag UID from PN532.

        Returns
        -------
        str | None
            Tag UID as uppercase hex string without separators,
            or None if no tag is present.

        Raises
        ------
        ProtocolError
            If communication with the reader fails.
        """
        if self._reader is None:
            msg = "Reader not initialized"
            raise ProtocolError(msg)

        try:
            # readPassiveTargetID returns (success, uid_bytes)
            # cardbaudrate=0x00 steht für PN532_MIFARE_ISO14443A
            success, uid = self._reader.readPassiveTargetID(cardbaudrate=0x00)
            if not success or uid is None:
                return None

            # Convert byte array to hex string
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
            # pn532pi doesn't have explicit cleanup, but we clear the reference
            self._reader = None

    @property
    def reader_id(self) -> str:
        """Return reader identifier."""
        return self._reader_id
