"""Core RFID manager handling scanning, modes, and event publishing."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Literal

import structlog

from .exceptions import HardwareError
from .models import RFIDStatusEvent, TagRemovedEvent, TagScannedEvent, TagScannedLearningEvent

if TYPE_CHECKING:
    from .config_schema import ServiceConfig
    from .hardware import RFIDReader
    from .mqtt_client import MQTTClient

logger = structlog.get_logger(__name__)


class RFIDManager:
    """Manages RFID scanning, operating modes, and event publishing.

    Responsibilities:
    - Continuous tag scanning loop
    - Mode switching (normal, learning)
    - Duplicate suppression
    - Tag removal detection
    - MQTT event publishing
    """

    def __init__(
        self,
        config: ServiceConfig,
        reader: RFIDReader,
        mqtt_client: MQTTClient,
    ) -> None:
        """Initialize RFID manager.

        Parameters
        ----------
        config:
            Service configuration.
        reader:
            Initialized RFID reader instance.
        mqtt_client:
            Connected MQTT client.
        """
        self._config = config
        self._reader = reader
        self._mqtt = mqtt_client

        self._mode: Literal["normal", "learning"] = "normal"
        self._current_tag: str | None = None
        self._last_scan_time: dict[str, float] = {}  # tag_id -> timestamp
        self._running = False

        logger.info(
            "rfid_manager_initialized",
            reader_id=reader.reader_id,
            scan_interval_ms=config.reader.scan_interval_ms,
            duplicate_suppression_ms=config.reader.duplicate_suppression_ms,
        )

    async def start(self) -> None:
        """Start the RFID manager and publish initial status."""
        self._running = True
        await self._publish_status("normal")
        logger.info("rfid_manager_started", mode=self._mode)

    async def stop(self) -> None:
        """Stop the RFID manager."""
        self._running = False
        await self._publish_status("idle")
        logger.info("rfid_manager_stopped")

    async def scan_loop(self) -> None:
        """Main scanning loop (runs continuously until stopped)."""
        scan_interval_sec = self._config.reader.scan_interval_ms / 1000.0

        while self._running:
            try:
                tag_uid = self._reader.read_tag_uid()

                if tag_uid:
                    await self._handle_tag_detected(tag_uid)
                else:
                    await self._handle_no_tag()

            except HardwareError as exc:
                logger.error(
                    "scan_hardware_error",
                    error=str(exc),
                    reader_id=self._reader.reader_id,
                )
                await self._publish_status("error", error="read_timeout")
                await asyncio.sleep(5)  # Wait before retrying

            await asyncio.sleep(scan_interval_sec)

    async def set_mode(self, mode: Literal["normal", "learning"]) -> None:
        """Switch between normal and learning mode.

        Parameters
        ----------
        mode:
            Target mode ('normal' or 'learning').
        """
        if self._mode == mode:
            return

        old_mode = self._mode
        self._mode = mode
        await self._publish_status(mode)

        logger.info(
            "mode_changed",
            old_mode=old_mode,
            new_mode=mode,
        )

    async def _handle_tag_detected(self, tag_uid: str) -> None:
        """Handle a detected tag (with duplicate suppression).

        Parameters
        ----------
        tag_uid:
            Tag UID as hex string.
        """
        now = time.time()
        suppression_window = self._config.reader.duplicate_suppression_ms / 1000.0

        # Check duplicate suppression
        if tag_uid in self._last_scan_time:
            time_since_last = now - self._last_scan_time[tag_uid]
            if time_since_last < suppression_window:
                logger.debug(
                    "tag_scan_suppressed",
                    tag_id=tag_uid,
                    time_since_last_ms=int(time_since_last * 1000),
                )
                return

        # Update scan time and current tag
        self._last_scan_time[tag_uid] = now
        self._current_tag = tag_uid

        # Publish event based on mode
        if self._mode == "learning":
            await self._publish_tag_scanned_learning(tag_uid)
        else:
            await self._publish_tag_scanned(tag_uid)

    async def _handle_no_tag(self) -> None:
        """Handle no tag detected (check for tag removal)."""
        if self._current_tag is not None:
            removed_tag = self._current_tag
            self._current_tag = None
            await self._publish_tag_removed(removed_tag)

    async def _publish_tag_scanned(self, tag_uid: str) -> None:
        """Publish tag-scanned event (normal mode)."""
        event = TagScannedEvent(
            tag_id=tag_uid,
            reader_id=self._reader.reader_id,
        )
        await self._mqtt.publish(
            "rfid/tag-scanned",
            event.model_dump_json(),
            retain=False,
            qos=1,
        )
        logger.info("tag_scanned", tag_id=tag_uid, mode="normal")

    async def _publish_tag_scanned_learning(self, tag_uid: str) -> None:
        """Publish tag-scanned-learning event (learning mode)."""
        event = TagScannedLearningEvent(
            tag_id=tag_uid,
            reader_id=self._reader.reader_id,
        )
        await self._mqtt.publish(
            "rfid/tag-scanned-learning",
            event.model_dump_json(),
            retain=False,
            qos=1,
        )
        logger.info("tag_scanned", tag_id=tag_uid, mode="learning")

    async def _publish_tag_removed(self, tag_uid: str) -> None:
        """Publish tag-removed event."""
        event = TagRemovedEvent(
            tag_id=tag_uid,
            reader_id=self._reader.reader_id,
        )
        await self._mqtt.publish(
            "rfid/tag-removed",
            event.model_dump_json(),
            retain=False,
            qos=1,
        )
        logger.info("tag_removed", tag_id=tag_uid)

    async def _publish_status(
        self,
        state: Literal["idle", "normal", "learning", "error"],
        *,
        error: str | None = None,
    ) -> None:
        """Publish service status (retained message)."""
        event = RFIDStatusEvent(
            state=state,
            reader_id=self._reader.reader_id,
            error=error,
        )
        await self._mqtt.publish(
            "rfid/status",
            event.model_dump_json(),
            retain=True,  # Status should be retained
            qos=1,
        )
        logger.info("status_published", state=state, error=error)
