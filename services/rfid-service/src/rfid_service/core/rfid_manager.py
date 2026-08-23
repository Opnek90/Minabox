"""Core RFID manager handling scanning, modes, and event publishing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

import structlog

from ..exceptions import HardwareError, ReaderNotFoundError
from ..infrastructure.hardware import RFIDReader
from ..infrastructure.mqtt_client import MQTTClient
from ..models import (
    RFIDStatusEvent,
    TagPresenceEvent,
    TagRemovedEvent,
    TagScannedEvent,
    TagScannedLearningEvent,
)

if TYPE_CHECKING:
    from ..config_schema import AppConfig

logger = structlog.get_logger(__name__)

Mode = Literal["normal", "learning"]

#: Error codes reported in the status payload, mapped from the exception type.
ERROR_READER_NOT_FOUND = "reader_not_found"
ERROR_READER_INIT_FAILED = "reader_init_failed"
ERROR_READ_FAILED = "read_timeout"


class RFIDManager:
    """Manages RFID scanning, operating modes, and event publishing.

    Event semantics:
    - tag-scanned: A tag was newly placed on the reader (transition from no tag
      or different tag to this tag). No repeat events while the same tag stays on.
    - tag-removed: The reader reported no tag for ``removal_debounce_reads``
      consecutive reads. The debounce matters because RFID hardware drops single
      reads when a tag shifts slightly, and an undebounced removal would stop
      playback for a tag that never actually left the reader.
    - presence: Retained topic always reflecting the current tag presence.
      Updated on every tag-scanned, tag-removed and at startup. Allows
      subscribers to recover state after re-initialization.

    Responsibilities:
    - Reader construction, initialisation and re-initialisation after faults
    - Continuous tag scanning loop
    - Mode switching (normal, learning) including the learning-mode timeout
    - Duplicate suppression (same tag re-scanned after quick remove/re-place)
    - Tag presence tracking (no repeat tag-scanned while tag remains on reader)
    - MQTT event publishing

    All timings and thresholds come from ``config/rfid.json``; nothing is
    hard-coded here.
    """

    def __init__(
        self,
        config: AppConfig,
        reader_factory: Callable[[], RFIDReader],
        mqtt_client: MQTTClient,
    ) -> None:
        """Initialize the RFID manager.

        Args:
            config: Application configuration.
            reader_factory: Callable returning a fresh, uninitialised reader.
                Taking a factory rather than an instance lets the manager
                rebuild the reader after a hardware fault.
            mqtt_client: MQTT client (need not be connected yet).
        """
        self._config = config
        self._reader_config = config.rfid.reader
        self._reader_factory = reader_factory
        self._mqtt = mqtt_client
        self._device_id = config.env.minabox_device_id
        self._topic_prefix = f"minabox/{self._device_id}/rfid"

        self._reader: RFIDReader | None = None
        # Used for events published before the reader exists (e.g. an error
        # status while the hardware is still unreachable).
        self._fallback_reader_id = (
            f"{self._reader_config.reader_type}_{self._reader_config.interface}"
        )

        self._mode: Mode = "normal"
        self._current_tag: str | None = None
        self._last_scan_time: dict[str, float] = {}
        self._missing_reads = 0
        self._consecutive_read_errors = 0
        self._init_attempts = 0
        self._running = False
        self._initial_state_published = False
        self._last_learning_activity = 0.0

        # Observability, surfaced through /health.
        self._last_scan_at: float | None = None
        self._last_error: str | None = None
        self._scan_loop_alive = False

        logger.info(
            "rfid_manager_initialized",
            reader_type=self._reader_config.reader_type,
            interface=self._reader_config.interface,
            scan_interval_ms=self._reader_config.scan_interval_ms,
            duplicate_suppression_ms=self._reader_config.duplicate_suppression_ms,
            removal_debounce_reads=self._reader_config.removal_debounce_reads,
            learning_timeout_s=config.rfid.modes.learning_timeout_s,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def reader_id(self) -> str:
        """Identifier of the active reader, or the configured one if not up yet."""
        if self._reader is not None:
            return self._reader.reader_id
        return self._fallback_reader_id

    @property
    def mode(self) -> Mode:
        """Current operating mode."""
        return self._mode

    def status_snapshot(self) -> dict[str, Any]:
        """Return the manager state for the /health endpoint."""
        return {
            "reader_id": self.reader_id,
            "reader_ready": self._reader is not None,
            "scan_loop_alive": self._scan_loop_alive,
            "mode": self._mode,
            "tag_present": self._current_tag is not None,
            "tag_id": self._current_tag,
            "last_scan_age_s": (
                None
                if self._last_scan_at is None
                else round(time.monotonic() - self._last_scan_at, 3)
            ),
            "last_error": self._last_error,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Mark the manager as running.

        The reader is not touched here: initialisation happens inside
        :meth:`scan_loop`, so unreachable hardware never blocks service startup
        and is reported over MQTT instead.
        """
        self._running = True
        logger.info("rfid_manager_started", mode=self._mode)

    def request_stop(self) -> None:
        """Ask the scan loop to finish without waiting for it."""
        self._running = False

    async def stop(self) -> None:
        """Stop the manager and release the reader.

        Presence is cleared explicitly: once this process is gone nobody can
        correct a retained ``tag_present: true``, and a subscriber that believes
        a tag is still on the reader keeps acting on it.
        """
        self._running = False
        if self._current_tag is not None:
            self._current_tag = None
            await self._publish_presence(tag_present=False, tag_id=None)
        await self._publish_status("idle")
        self._release_reader()
        logger.info("rfid_manager_stopped")

    async def scan_loop(self) -> None:
        """Main scanning loop: supervises the reader and publishes tag events.

        Runs until :meth:`stop` is called or the task is cancelled. Every error
        that is not a cancellation is handled inside the loop, because a scan
        loop that dies silently leaves a service that looks healthy but has
        stopped reacting to tags.
        """
        scan_interval_s = self._reader_config.scan_interval_ms / 1000.0
        error_retry_delay_s = self._reader_config.error_retry_delay_ms / 1000.0

        self._scan_loop_alive = True
        try:
            while self._running:
                if self._reader is None:
                    delay = await self._try_initialize_reader()
                    if not self._running:
                        break
                    if delay is not None:
                        await asyncio.sleep(delay)
                        continue

                try:
                    tag_uid = await asyncio.to_thread(self._read_tag_uid)
                except HardwareError as exc:
                    await self._handle_read_error(exc)
                    await asyncio.sleep(error_retry_delay_s)
                    continue
                except Exception as exc:  # noqa: BLE001 - the loop must survive
                    logger.error(
                        "scan_unexpected_error",
                        error=str(exc),
                        reader_id=self.reader_id,
                        exc_info=True,
                    )
                    await self._handle_read_error(exc)
                    await asyncio.sleep(error_retry_delay_s)
                    continue

                self._last_scan_at = time.monotonic()
                self._consecutive_read_errors = 0

                if tag_uid:
                    await self._handle_tag_detected(tag_uid)
                else:
                    await self._handle_no_tag()

                await self._check_learning_timeout()
                self._prune_scan_history()

                await asyncio.sleep(scan_interval_s)
        except asyncio.CancelledError:
            raise
        finally:
            self._scan_loop_alive = False

    # ------------------------------------------------------------------
    # Reader supervision
    # ------------------------------------------------------------------

    def _read_tag_uid(self) -> str | None:
        """Read the reader in a worker thread; guards against a vanished reader."""
        reader = self._reader
        if reader is None:
            return None
        return reader.read_tag_uid()

    def _release_reader(self) -> None:
        """Drop the current reader, tolerating a failing cleanup."""
        reader, self._reader = self._reader, None
        if reader is None:
            return
        try:
            reader.cleanup()
        except Exception as exc:  # noqa: BLE001 - teardown must never propagate
            logger.debug("reader_cleanup_failed", error=str(exc))

    async def _try_initialize_reader(self) -> float | None:
        """Attempt to build and initialise the reader.

        Returns:
            None if the reader is ready, otherwise the number of seconds to
            wait before the next attempt.
        """
        max_attempts = self._reader_config.init_max_attempts
        if max_attempts and self._init_attempts >= max_attempts:
            # Give up retrying but keep the service alive so /health and the
            # error status stay observable.
            self._running = False
            logger.error(
                "reader_init_giving_up",
                attempts=self._init_attempts,
                reader_id=self.reader_id,
            )
            return None

        self._init_attempts += 1
        try:
            reader = await asyncio.to_thread(self._build_and_initialize_reader)
        except ReaderNotFoundError as exc:
            return await self._handle_init_failure(ERROR_READER_NOT_FOUND, exc)
        except Exception as exc:  # noqa: BLE001 - every failure is retryable
            return await self._handle_init_failure(ERROR_READER_INIT_FAILED, exc)

        self._reader = reader
        self._init_attempts = 0
        self._consecutive_read_errors = 0
        self._last_error = None
        logger.info("reader_ready", reader_id=reader.reader_id)

        await self._publish_status(self._mode)
        if not self._initial_state_published:
            await self._publish_initial_state()
            self._initial_state_published = True
        return None

    def _build_and_initialize_reader(self) -> RFIDReader:
        """Construct and initialise a reader (blocking; runs in a thread)."""
        reader = self._reader_factory()
        reader.initialize()
        return reader

    async def _handle_init_failure(self, error_code: str, exc: Exception) -> float:
        """Report a failed initialisation and return the backoff delay."""
        self._last_error = error_code
        logger.error(
            "reader_init_failed",
            error=str(exc),
            error_code=error_code,
            attempt=self._init_attempts,
            reader_id=self.reader_id,
        )
        await self._publish_status("error", error=error_code)
        return self._init_backoff_delay()

    def _init_backoff_delay(self) -> float:
        """Exponential backoff between initialisation attempts, from config."""
        base_ms: int = self._reader_config.init_retry_delay_ms
        max_ms: int = self._reader_config.init_retry_max_delay_ms
        # Exponent capped so an endlessly retrying service does not end up
        # computing absurdly large integers before min() discards them.
        exponent = min(max(self._init_attempts - 1, 0), 32)
        delay_ms = min(base_ms * (2**exponent), max_ms)
        return float(delay_ms) / 1000.0

    async def _handle_read_error(self, exc: Exception) -> None:
        """Report a read error and re-initialise the reader if faults persist."""
        self._consecutive_read_errors += 1
        self._last_error = ERROR_READ_FAILED
        logger.error(
            "scan_hardware_error",
            error=str(exc),
            reader_id=self.reader_id,
            consecutive_errors=self._consecutive_read_errors,
        )
        await self._publish_status("error", error=ERROR_READ_FAILED)

        threshold = self._reader_config.reinit_after_read_errors
        if threshold and self._consecutive_read_errors >= threshold:
            logger.warning(
                "reader_reinit_triggered",
                consecutive_errors=self._consecutive_read_errors,
                reader_id=self.reader_id,
            )
            self._release_reader()
            self._consecutive_read_errors = 0
            self._init_attempts = 0

    async def _publish_initial_state(self) -> None:
        """Publish the real-world tag state once the reader is up.

        A box that boots with a tag already on the reader must report that, and
        one that boots with an empty reader must say so too, otherwise
        subscribers keep a stale retained presence from a previous run.
        """
        try:
            tag_uid = await asyncio.to_thread(self._read_tag_uid)
        except Exception as exc:  # noqa: BLE001 - the scan loop retries anyway
            logger.warning("initial_scan_failed", error=str(exc))
            return

        if tag_uid:
            self._current_tag = tag_uid
            self._last_scan_time[tag_uid] = time.monotonic()
            self._missing_reads = 0
            await self._publish_tag_scanned(tag_uid)
            await self._publish_presence(tag_present=True, tag_id=tag_uid)
            logger.info("initial_tag_present", tag_id=tag_uid)
        else:
            # Empty tag_id: at boot there is no previously known tag. Subscribers
            # use this purely as a state signal.
            await self._publish_tag_removed("")
            await self._publish_presence(tag_present=False, tag_id=None)
            logger.info("initial_no_tag")

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------

    async def set_mode(self, mode: Mode) -> None:
        """Switch between normal and learning mode."""
        if mode not in ("normal", "learning"):
            logger.warning("invalid_mode_ignored", mode=mode)
            return

        self._last_learning_activity = time.monotonic()

        if self._mode == mode:
            return

        old_mode = self._mode
        self._mode = mode
        await self._publish_status(mode)

        logger.info("mode_changed", old_mode=old_mode, new_mode=mode)

    async def _check_learning_timeout(self) -> None:
        """Fall back to normal mode when learning mode has gone idle.

        A WebUI tab that is closed abruptly never sends the "back to normal"
        command, which would leave the box unable to start playback from a tag.
        """
        timeout_s = self._config.rfid.modes.learning_timeout_s
        if not timeout_s or self._mode != "learning":
            return

        idle_for = time.monotonic() - self._last_learning_activity
        if idle_for < timeout_s:
            return

        logger.info("learning_mode_timeout", idle_seconds=round(idle_for, 1))
        await self.set_mode("normal")

    # ------------------------------------------------------------------
    # Tag handling
    # ------------------------------------------------------------------

    async def _handle_tag_detected(self, tag_uid: str) -> None:
        """Handle a detected tag. Emit tag-scanned only when tag is newly placed."""
        now = time.monotonic()
        suppression_window = self._reader_config.duplicate_suppression_ms / 1000.0

        # Any successful read clears a pending removal: the tag never left.
        self._missing_reads = 0

        # Tag still on reader - do not publish tag-scanned again (same presence)
        if tag_uid == self._current_tag:
            self._last_scan_time[tag_uid] = now
            return

        if tag_uid in self._last_scan_time:
            time_since_last = now - self._last_scan_time[tag_uid]
            if time_since_last < suppression_window:
                logger.debug(
                    "tag_scan_suppressed",
                    tag_id=tag_uid,
                    time_since_last_ms=int(time_since_last * 1000),
                )
                return

        self._last_scan_time[tag_uid] = now
        self._current_tag = tag_uid

        if self._mode == "learning":
            self._last_learning_activity = now
            await self._publish_tag_scanned_learning(tag_uid)
        else:
            await self._publish_tag_scanned(tag_uid)

        await self._publish_presence(tag_present=True, tag_id=tag_uid)

    async def _handle_no_tag(self) -> None:
        """Publish tag-removed once the removal debounce is satisfied."""
        if self._current_tag is None:
            return

        self._missing_reads += 1
        if self._missing_reads < self._reader_config.removal_debounce_reads:
            logger.debug(
                "tag_removal_pending",
                tag_id=self._current_tag,
                missing_reads=self._missing_reads,
            )
            return

        removed_tag = self._current_tag
        self._current_tag = None
        self._missing_reads = 0
        await self._publish_tag_removed(removed_tag)
        await self._publish_presence(tag_present=False, tag_id=None)

    def _prune_scan_history(self) -> None:
        """Drop suppression entries that can no longer suppress anything.

        Without this the dict keeps every UID the box has ever seen.
        """
        suppression_window = self._reader_config.duplicate_suppression_ms / 1000.0
        cutoff = time.monotonic() - suppression_window
        stale = [
            uid
            for uid, seen_at in self._last_scan_time.items()
            if seen_at < cutoff and uid != self._current_tag
        ]
        for uid in stale:
            del self._last_scan_time[uid]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def _publish_tag_scanned(self, tag_uid: str) -> None:
        """Publish tag-scanned: tag was newly placed on reader (normal mode)."""
        event = TagScannedEvent(tag_id=tag_uid, reader_id=self.reader_id)
        await self._mqtt.publish(
            f"{self._topic_prefix}/tag-scanned",
            event.model_dump(),
            retain=False,
            qos=1,
        )
        logger.info("tag_scanned", tag_id=tag_uid, mode="normal")

    async def _publish_tag_scanned_learning(self, tag_uid: str) -> None:
        """Publish tag-scanned-learning event (learning mode)."""
        event = TagScannedLearningEvent(tag_id=tag_uid, reader_id=self.reader_id)
        await self._mqtt.publish(
            f"{self._topic_prefix}/tag-scanned-learning",
            event.model_dump(),
            retain=False,
            qos=1,
        )
        logger.info("tag_scanned", tag_id=tag_uid, mode="learning")

    async def _publish_tag_removed(self, tag_uid: str) -> None:
        """Publish tag-removed: the reader no longer detects the tag."""
        event = TagRemovedEvent(tag_id=tag_uid, reader_id=self.reader_id)
        await self._mqtt.publish(
            f"{self._topic_prefix}/tag-removed",
            event.model_dump(),
            retain=False,
            qos=1,
        )
        logger.info("tag_removed", tag_id=tag_uid)

    async def _publish_presence(self, *, tag_present: bool, tag_id: str | None) -> None:
        """Publish the retained presence topic.

        This retained message is the single source of truth for the current
        tag presence. Subscribers that reconnect or re-initialize (e.g.
        LED-service after a config reload) receive this immediately without
        waiting for the next state-change event.

        Published with remember=True so it is re-sent after a reconnect; a
        broker that restarted would otherwise lose the retained message and
        nobody would ever refresh it.

        Args:
            tag_present: Whether a tag is currently on the reader.
            tag_id: UID of the present tag, or None when no tag is present.
        """
        event = TagPresenceEvent(
            tag_present=tag_present,
            tag_id=tag_id,
            reader_id=self.reader_id,
        )
        await self._mqtt.publish(
            f"{self._topic_prefix}/presence",
            event.model_dump(),
            retain=True,
            qos=1,
            remember=True,
        )
        logger.debug("presence_published", tag_present=tag_present, tag_id=tag_id)

    async def _publish_status(
        self,
        state: Literal["idle", "normal", "learning", "error"],
        *,
        error: str | None = None,
    ) -> None:
        """Publish service status (retained, and replayed after a reconnect)."""
        event = RFIDStatusEvent(
            state=state,
            reader_id=self.reader_id,
            error=error,
        )
        await self._mqtt.publish(
            f"{self._topic_prefix}/status",
            event.model_dump(),
            retain=True,
            qos=1,
            remember=True,
        )
        logger.info("status_published", state=state, error=error)
