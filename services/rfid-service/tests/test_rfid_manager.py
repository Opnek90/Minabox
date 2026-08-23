"""Tests for the RFID manager state machine.

These pin down the behaviour that decides whether a box plays music reliably:
a single dropped read must not look like a removed tag, a tag resting on the
reader must not re-trigger, and hardware that is missing at boot must be
reported rather than take the service down.
"""

from __future__ import annotations

import asyncio

import pytest
from rfid_test_doubles import FakeMQTT, ScriptedReader, make_config

from rfid_service.core.rfid_manager import (
    ERROR_READ_FAILED,
    ERROR_READER_INIT_FAILED,
    ERROR_READER_NOT_FOUND,
    RFIDManager,
)
from rfid_service.exceptions import ProtocolError, ReaderNotFoundError

pytestmark = pytest.mark.asyncio


async def run_script(
    script: list,
    mqtt: FakeMQTT,
    **config_overrides,
) -> tuple[RFIDManager, ScriptedReader]:
    """Run the scan loop over a script and stop once it is exhausted."""
    config = make_config(**config_overrides)
    manager: RFIDManager | None = None

    reader = ScriptedReader(script, on_exhausted=lambda: manager.request_stop())
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=10)
    return manager, reader


# ----------------------------------------------------------------------
# Tag presence and the removal debounce
# ----------------------------------------------------------------------


async def test_tag_placed_publishes_scanned_and_presence(mqtt: FakeMQTT) -> None:
    await run_script(["AABB", "AABB"], mqtt)

    assert mqtt.payloads_for("tag-scanned")[0]["tag_id"] == "AABB"
    presence = mqtt.payloads_for("presence")[-1]
    assert presence["tag_present"] is True
    assert presence["tag_id"] == "AABB"


async def test_resting_tag_does_not_retrigger(mqtt: FakeMQTT) -> None:
    """A tag left on the reader must produce exactly one tag-scanned."""
    await run_script(["AABB"] * 10, mqtt)

    assert len(mqtt.payloads_for("tag-scanned")) == 1
    assert mqtt.payloads_for("tag-removed") == []


async def test_single_dropped_read_does_not_remove_tag(mqtt: FakeMQTT) -> None:
    """The regression this debounce exists for.

    RFID hardware drops single reads when a tag shifts slightly. Without the
    debounce that dropped read published tag-removed, the backend stopped
    playback, and duplicate suppression then swallowed the re-scan for the
    length of the suppression window -- a two second silence and a restarted
    track for a tag that never left the reader.
    """
    await run_script(
        ["AABB", "AABB", None, "AABB", "AABB", None, None, "AABB"],
        mqtt,
        removal_debounce_reads=3,
    )

    assert mqtt.payloads_for("tag-removed") == []
    assert len(mqtt.payloads_for("tag-scanned")) == 1


async def test_removal_published_after_debounce_is_satisfied(mqtt: FakeMQTT) -> None:
    await run_script(
        ["AABB", None, None, None, None],
        mqtt,
        removal_debounce_reads=3,
    )

    removed = mqtt.payloads_for("tag-removed")
    assert len(removed) == 1
    assert removed[0]["tag_id"] == "AABB"
    assert mqtt.payloads_for("presence")[-1]["tag_present"] is False


async def test_debounce_of_one_removes_immediately(mqtt: FakeMQTT) -> None:
    """removal_debounce_reads = 1 keeps the old, undebounced behaviour."""
    await run_script(["AABB", None, None], mqtt, removal_debounce_reads=1)

    assert len(mqtt.payloads_for("tag-removed")) == 1


async def test_different_tag_replaces_previous_one(mqtt: FakeMQTT) -> None:
    await run_script(["AABB", "AABB", "CCDD", "CCDD"], mqtt)

    scanned = [p["tag_id"] for p in mqtt.payloads_for("tag-scanned")]
    assert scanned == ["AABB", "CCDD"]


# ----------------------------------------------------------------------
# Duplicate suppression
# ----------------------------------------------------------------------


async def test_quick_replace_is_suppressed(mqtt: FakeMQTT) -> None:
    """A tag lifted and replaced inside the window must not re-trigger."""
    await run_script(
        ["AABB", None, None, None, "AABB", "AABB"],
        mqtt,
        removal_debounce_reads=1,
        duplicate_suppression_ms=60000,
    )

    assert len(mqtt.payloads_for("tag-scanned")) == 1


async def test_replace_after_window_triggers_again(
    mqtt: FakeMQTT, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(removal_debounce_reads=1, duplicate_suppression_ms=1000)
    reader = ScriptedReader()
    manager = RFIDManager(config, lambda: reader, mqtt)

    clock = [1000.0]
    monkeypatch.setattr(
        "rfid_service.core.rfid_manager.time.monotonic", lambda: clock[0]
    )

    await manager._handle_tag_detected("AABB")
    await manager._handle_no_tag()
    clock[0] += 5.0
    await manager._handle_tag_detected("AABB")

    assert len(mqtt.payloads_for("tag-scanned")) == 2


async def test_scan_history_is_pruned(
    mqtt: FakeMQTT, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Old suppression entries must not accumulate for the process lifetime."""
    config = make_config(duplicate_suppression_ms=1000, removal_debounce_reads=1)
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    clock = [1000.0]
    monkeypatch.setattr(
        "rfid_service.core.rfid_manager.time.monotonic", lambda: clock[0]
    )

    for index in range(20):
        await manager._handle_tag_detected(f"TAG{index:02X}")
        await manager._handle_no_tag()
        clock[0] += 0.1

    clock[0] += 10.0
    manager._prune_scan_history()

    assert manager._last_scan_time == {}


# ----------------------------------------------------------------------
# Modes
# ----------------------------------------------------------------------


async def test_learning_mode_uses_its_own_topic(mqtt: FakeMQTT) -> None:
    config = make_config()
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    await manager.set_mode("learning")
    await manager._handle_tag_detected("AABB")

    assert len(mqtt.payloads_for("tag-scanned-learning")) == 1
    assert mqtt.payloads_for("tag-scanned") == []


async def test_invalid_mode_is_ignored(mqtt: FakeMQTT) -> None:
    manager = RFIDManager(make_config(), lambda: ScriptedReader(), mqtt)

    await manager.set_mode("nonsense")  # type: ignore[arg-type]

    assert manager.mode == "normal"


async def test_learning_mode_times_out(
    mqtt: FakeMQTT, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A WebUI tab closed without leaving learning mode must not strand the box."""
    config = make_config(learning_timeout_s=60)
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    clock = [1000.0]
    monkeypatch.setattr(
        "rfid_service.core.rfid_manager.time.monotonic", lambda: clock[0]
    )

    await manager.set_mode("learning")
    clock[0] += 59.0
    await manager._check_learning_timeout()
    assert manager.mode == "learning"

    clock[0] += 2.0
    await manager._check_learning_timeout()
    assert manager.mode == "normal"


async def test_learning_timeout_disabled_by_zero(
    mqtt: FakeMQTT, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(learning_timeout_s=0)
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    clock = [1000.0]
    monkeypatch.setattr(
        "rfid_service.core.rfid_manager.time.monotonic", lambda: clock[0]
    )

    await manager.set_mode("learning")
    clock[0] += 100000.0
    await manager._check_learning_timeout()

    assert manager.mode == "learning"


async def test_learning_scan_refreshes_the_timeout(
    mqtt: FakeMQTT, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(learning_timeout_s=60)
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    clock = [1000.0]
    monkeypatch.setattr(
        "rfid_service.core.rfid_manager.time.monotonic", lambda: clock[0]
    )

    await manager.set_mode("learning")
    clock[0] += 50.0
    await manager._handle_tag_detected("AABB")
    clock[0] += 50.0
    await manager._check_learning_timeout()

    assert manager.mode == "learning"


# ----------------------------------------------------------------------
# Reader supervision
# ----------------------------------------------------------------------


async def test_missing_reader_reports_error_and_keeps_service_alive(
    mqtt: FakeMQTT,
) -> None:
    """Hardware missing at boot must be observable, not fatal."""
    config = make_config(init_max_attempts=2)
    reader = ScriptedReader(
        init_failures=5, init_error=ReaderNotFoundError("no PN532")
    )
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=10)

    statuses = mqtt.payloads_for("status")
    assert statuses[0]["state"] == "error"
    assert statuses[0]["error"] == ERROR_READER_NOT_FOUND
    assert manager.status_snapshot()["reader_ready"] is False


async def test_reader_recovers_after_failed_attempts(mqtt: FakeMQTT) -> None:
    config = make_config()
    manager: RFIDManager | None = None
    reader = ScriptedReader(
        ["AABB"],
        init_failures=2,
        on_exhausted=lambda: manager.request_stop(),
    )
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=10)

    states = [p["state"] for p in mqtt.payloads_for("status")]
    assert states[0] == "error"
    assert "normal" in states
    assert reader.init_calls == 3


async def test_init_error_type_maps_to_error_code(mqtt: FakeMQTT) -> None:
    config = make_config(init_max_attempts=1)
    reader = ScriptedReader(init_failures=1, init_error=ProtocolError("bus glitch"))
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=10)

    assert mqtt.payloads_for("status")[0]["error"] == ERROR_READER_INIT_FAILED


async def test_read_errors_trigger_reinitialisation(mqtt: FakeMQTT) -> None:
    """A reader stuck in a fault state must be rebuilt, not polled forever."""
    config = make_config(reinit_after_read_errors=2, error_retry_delay_ms=100)
    manager: RFIDManager | None = None
    reader = ScriptedReader(
        [None, ProtocolError("read failed"), ProtocolError("read failed"), "AABB"],
        on_exhausted=lambda: manager.request_stop(),
    )
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=15)

    assert reader.cleanup_calls >= 1
    assert reader.init_calls >= 2
    assert ERROR_READ_FAILED in [
        p["error"] for p in mqtt.payloads_for("status") if p["error"]
    ]


async def test_unexpected_read_exception_keeps_loop_running(mqtt: FakeMQTT) -> None:
    """A non-hardware exception must not silently kill the scan loop."""
    config = make_config(reinit_after_read_errors=0, error_retry_delay_ms=100)
    manager: RFIDManager | None = None
    reader = ScriptedReader(
        [None, RuntimeError("something unforeseen"), "AABB", "AABB"],
        on_exhausted=lambda: manager.request_stop(),
    )
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=15)

    assert len(mqtt.payloads_for("tag-scanned")) == 1


# ----------------------------------------------------------------------
# Startup and shutdown state
# ----------------------------------------------------------------------


async def test_boot_with_tag_on_reader_reports_it(mqtt: FakeMQTT) -> None:
    await run_script(["AABB", "AABB"], mqtt)

    assert mqtt.payloads_for("tag-scanned")[0]["tag_id"] == "AABB"
    assert mqtt.payloads_for("presence")[0]["tag_present"] is True


async def test_boot_with_empty_reader_clears_presence(mqtt: FakeMQTT) -> None:
    await run_script([None, None], mqtt)

    assert mqtt.payloads_for("tag-removed")[0]["tag_id"] == ""
    assert mqtt.payloads_for("presence")[0]["tag_present"] is False


async def test_stop_clears_presence_and_reports_idle(mqtt: FakeMQTT) -> None:
    config = make_config()
    reader = ScriptedReader()
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await manager._handle_tag_detected("AABB")
    await manager.stop()

    assert mqtt.payloads_for("presence")[-1]["tag_present"] is False
    assert mqtt.payloads_for("status")[-1]["state"] == "idle"


# ----------------------------------------------------------------------
# MQTT contract
# ----------------------------------------------------------------------


async def test_retained_topics_are_remembered_for_replay(mqtt: FakeMQTT) -> None:
    """Retained state must survive a broker restart, which only remember= does."""
    config = make_config()
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    await manager.start()
    await manager._handle_tag_detected("AABB")
    await manager._publish_status("normal")

    for suffix in ("presence", "status"):
        for message in mqtt.messages_for(suffix):
            assert message["retain"] is True, suffix
            assert message["remember"] is True, suffix


async def test_tag_events_are_not_retained(mqtt: FakeMQTT) -> None:
    config = make_config()
    manager = RFIDManager(config, lambda: ScriptedReader(), mqtt)

    await manager.start()
    await manager._handle_tag_detected("AABB")
    await manager._handle_no_tag()

    for suffix in ("tag-scanned", "tag-removed"):
        for message in mqtt.messages_for(suffix):
            assert message["retain"] is False, suffix
            assert message["qos"] == 1, suffix


async def test_events_carry_the_active_reader_id(mqtt: FakeMQTT) -> None:
    config = make_config()
    manager: RFIDManager | None = None
    reader = ScriptedReader(["AABB"], reader_id="pn532_i2c",
                            on_exhausted=lambda: manager.request_stop())
    manager = RFIDManager(config, lambda: reader, mqtt)

    await manager.start()
    await asyncio.wait_for(manager.scan_loop(), timeout=10)

    assert mqtt.payloads_for("tag-scanned")[0]["reader_id"] == "pn532_i2c"


async def test_reader_id_falls_back_to_config_before_reader_exists(
    mqtt: FakeMQTT,
) -> None:
    manager = RFIDManager(make_config(), lambda: ScriptedReader(), mqtt)

    assert manager.reader_id == "mock_i2c"
