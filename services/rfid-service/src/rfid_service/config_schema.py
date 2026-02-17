from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt


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
    """Top-level RFID configuration loaded from config/service.json."""

    reader: ReaderConfig = Field(
        description="Hardware reader configuration.",
    )


class EnvConfig(BaseModel):
    """Environment-based configuration shared across Minabox services."""

    mqtt_broker: str = Field(
        min_length=1,
        description="Hostname of the MQTT broker (e.g. 'mqtt').",
    )
    mqtt_port: PositiveInt = Field(
        description="Port of the MQTT broker (e.g. 1883).",
    )
    minabox_device_id: str = Field(
        min_length=1,
        description="Device ID used in MQTT topics (e.g. 'box1').",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        description="Global log level for this service.",
    )


class AppConfig(BaseModel):
    """Combined configuration for the RFID service.

    This is what the rest of the service should depend on.
    """

    env: EnvConfig
    rfid: RFIDServiceConfig
