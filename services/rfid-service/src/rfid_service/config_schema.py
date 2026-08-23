"""Configuration schema for the RFID service.

Every tunable value the service uses at runtime is declared here and read from
``config/rfid.json`` (reader and behaviour) or from the environment (broker,
device id, log level). Nothing is hard-coded in the business logic, so a box can
be re-tuned by editing the JSON file and restarting the container.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from shared_lib.config import EnvConfigBase


class PN532Config(BaseModel):
    """Interface-specific settings for the PN532 reader."""

    i2c_bus: int = Field(
        default=1,
        ge=0,
        le=1,
        description="I2C bus number the reader is wired to (Raspberry Pi: 1).",
    )
    spi_device: int = Field(
        default=0,
        ge=0,
        le=1,
        description="SPI chip-select line, used when interface is 'spi'.",
    )
    uart_port: str = Field(
        default="/dev/ttyS0",
        min_length=1,
        description="Serial device, used when interface is 'uart'.",
    )
    passive_activation_retries: int = Field(
        default=2,
        ge=0,
        le=255,
        description=(
            "How often the PN532 retries to activate a passive target before "
            "reporting 'no tag'. Keep this low: the call blocks for the whole "
            "attempt, so a high value stalls the scan loop."
        ),
    )


class MockReaderConfig(BaseModel):
    """Behaviour of the mock reader used for development and tests."""

    tags: list[str] = Field(
        default_factory=lambda: ["04A224BC19", "DEADBEEF01"],
        description="Tag UIDs the mock reader reports, in order.",
    )
    hold_reads: int = Field(
        default=10,
        ge=1,
        description=(
            "Number of consecutive reads that report the same tag, simulating a "
            "tag resting on the reader."
        ),
    )
    gap_reads: int = Field(
        default=10,
        ge=0,
        description=(
            "Number of consecutive empty reads between two tags, simulating the "
            "reader being free."
        ),
    )


class ReaderConfig(BaseModel):
    """Configuration for the physical RFID reader and the scan loop."""

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
    removal_debounce_reads: int = Field(
        default=3,
        ge=1,
        le=50,
        description=(
            "Number of consecutive empty reads required before a tag counts as "
            "removed. Protects against the single dropped read that RFID "
            "hardware produces when a tag shifts slightly; 1 disables the "
            "debounce."
        ),
    )
    error_retry_delay_ms: int = Field(
        default=5000,
        ge=100,
        le=300000,
        description="Pause after a hardware read error before scanning resumes.",
    )
    init_retry_delay_ms: int = Field(
        default=2000,
        ge=100,
        le=300000,
        description="First delay between reader initialisation attempts.",
    )
    init_retry_max_delay_ms: int = Field(
        default=60000,
        ge=100,
        le=3600000,
        description="Upper bound for the initialisation retry backoff.",
    )
    init_max_attempts: int = Field(
        default=0,
        ge=0,
        description=(
            "Maximum reader initialisation attempts; 0 means retry forever. "
            "The service stays up and reports state 'error' while the reader "
            "is unreachable."
        ),
    )
    reinit_after_read_errors: int = Field(
        default=5,
        ge=0,
        description=(
            "Consecutive read errors after which the reader is re-initialised. "
            "0 disables the re-initialisation."
        ),
    )
    pn532: PN532Config = Field(
        default_factory=PN532Config,
        description="Settings specific to the PN532 reader.",
    )
    mock: MockReaderConfig = Field(
        default_factory=MockReaderConfig,
        description="Settings specific to the mock reader.",
    )


class ModeConfig(BaseModel):
    """Operating-mode behaviour."""

    learning_timeout_s: int = Field(
        default=300,
        ge=0,
        le=86400,
        description=(
            "Seconds of inactivity after which learning mode falls back to "
            "normal mode. Protects a box whose WebUI tab was closed without "
            "leaving learning mode; 0 disables the timeout."
        ),
    )


class ServiceConfig(BaseModel):
    """Process-level behaviour."""

    shutdown_timeout_s: float = Field(
        default=5.0,
        gt=0.0,
        le=120.0,
        description="Time granted to each background task to finish on shutdown.",
    )


class RFIDServiceConfig(BaseModel):
    """Top-level RFID configuration loaded from config/rfid.json."""

    reader: ReaderConfig = Field(
        description="Hardware reader configuration.",
    )
    modes: ModeConfig = Field(
        default_factory=ModeConfig,
        description="Operating-mode behaviour.",
    )
    service: ServiceConfig = Field(
        default_factory=ServiceConfig,
        description="Process-level behaviour.",
    )


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the RFID service (extends shared base)."""

    api_port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="REST API port for the RFID service.",
    )


class AppConfig(BaseModel):
    """Combined configuration for the RFID service."""

    env: EnvConfig
    rfid: RFIDServiceConfig

    @property
    def mqtt_topic_prefix(self) -> str:
        """Get MQTT topic prefix for this device."""
        return f"minabox/{self.env.minabox_device_id}"

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Build a namespaced MQTT topic.

        Args:
            domain: Service domain (e.g. 'rfid', 'system', 'config').
            action: Action / sub-topic (e.g. 'tag-scanned', 'service-started').

        Returns:
            Full topic string: minabox/<device-id>/<domain>/<action>
        """
        return f"{self.mqtt_topic_prefix}/{domain}/{action}"
