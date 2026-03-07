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

    api_port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="REST API port for the RFID service (issue #17/#28).",
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
        """Build a namespaced MQTT topic (issue #28).

        Args:
            domain: Service domain (e.g. 'rfid', 'system', 'config').
            action: Action / sub-topic (e.g. 'tag-scanned', 'service-started').

        Returns:
            Full topic string: minabox/<device-id>/<domain>/<action>
        """
        return f"{self.mqtt_topic_prefix}/{domain}/{action}"
