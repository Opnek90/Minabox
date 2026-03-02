from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt

from shared_lib.config import EnvConfigBase


class ReaderConfig(BaseModel):
    """Configuration for the physical RFID reader."""

    reader_type: Literal["pn532", "mock"] = Field(
        description="Type of RFID reader implementation to use.",
    )
    interface: Literal["i2c", "spi", "uart"] = Field(
        description="Hardware interface used to communicate with the reader.",
    )
    scan_interval_ms: int = Field(
        default=200,
        ge=20,
        le=5000,
        description="Interval between scan attempts in milliseconds.",
    )
    duplicate_suppression_ms: int = Field(
        default=2000,
        ge=0,
        le=60000,
        description=(
            "Time window in milliseconds during which repeated scans of the "
            "same tag ID are suppressed."
        ),
    )


class RFIDServiceConfig(BaseModel):
    """Top-level RFID configuration loaded from config/rfid.json."""

    reader: ReaderConfig = Field(
        description="Hardware reader configuration.",
    )


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the RFID service (extends shared base)."""


class AppConfig(BaseModel):
    """Combined configuration for the RFID service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    rfid: RFIDServiceConfig
