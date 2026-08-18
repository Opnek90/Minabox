"""Regression tests for the temperature background loop.

Both cases here are bugs that shipped:

1. The interval sleep sat at the end of the loop body while the two guard
   clauses used `continue`. A Host-Helper that could not be reached turned the
   loop into a busy spin that pegged a CPU core on the Pi.
2. `MQTTClient.is_connected` is a property, but the loop called it. Crossing
   the temperature threshold raised TypeError outside the try block, which
   killed the background task - so the alert was never sent and never cleared.
"""

from __future__ import annotations

import asyncio

import pytest

from backend_service.core import temperature_logger as tl


class _StopLoop(Exception):
    """Raised by the fake sleep to end the loop under test deterministically."""


class FakeMQTTClient:
    """Mirrors the real client: is_connected is a property, publish is async."""

    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.published: list[tuple[str, dict]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))


class FakeDBManager:
    def __init__(self) -> None:
        self.sessions = 0

    def get_session(self):
        self.sessions += 1
        return FakeSession()


class FakeSession:
    def add(self, obj) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
    def execute(self, *a, **kw) -> None: ...


def _install_fake_sleep(monkeypatch, stop_after: int) -> list[float]:
    """Replace asyncio.sleep inside the module and stop the loop after N sleeps.

    The real sleep is captured up front - the fake must not call the patched
    name, or it would recurse into itself.
    """
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) >= stop_after:
            raise _StopLoop
        await real_sleep(0)

    monkeypatch.setattr(tl.asyncio, "sleep", fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_unreachable_host_helper_does_not_busy_loop(monkeypatch):
    """Every iteration must sleep, even when no sample could be taken."""
    calls = 0

    async def never_reachable():
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(tl, "_fetch_host_status", never_reachable)
    # 1 startup sleep + 3 interval sleeps, then stop.
    sleeps = _install_fake_sleep(monkeypatch, stop_after=4)

    with pytest.raises(_StopLoop):
        await tl.run_temperature_log_loop(
            FakeDBManager(), FakeMQTTClient(), "box1", lambda d, a: f"{d}/{a}", None
        )

    # Three iterations, three fetches - not an unbounded spin.
    assert calls == 3
    # First sleep is the startup delay, the rest are the configured interval.
    assert sleeps[0] == 30
    assert all(s == tl.LOG_INTERVAL_SECONDS for s in sleeps[1:])


@pytest.mark.asyncio
async def test_missing_temperature_field_does_not_busy_loop(monkeypatch):
    """A host-status payload without a temperature must also sleep."""
    calls = 0

    async def no_temperature():
        nonlocal calls
        calls += 1
        return {"hostname": "minabox"}

    monkeypatch.setattr(tl, "_fetch_host_status", no_temperature)
    _install_fake_sleep(monkeypatch, stop_after=3)

    with pytest.raises(_StopLoop):
        await tl.run_temperature_log_loop(
            FakeDBManager(), FakeMQTTClient(), "box1", lambda d, a: f"{d}/{a}", None
        )

    assert calls == 2


@pytest.mark.asyncio
async def test_overheating_publishes_and_loop_survives(monkeypatch):
    """Crossing the threshold must publish, not kill the task with TypeError."""
    monkeypatch.setattr(tl, "_read_temperature_warning_celsius", lambda: 80.0)
    monkeypatch.setattr(tl, "_log_temperature", lambda session, temp: None)

    async def hot():
        return {"temperature_celsius": 91.0}

    monkeypatch.setattr(tl, "_fetch_host_status", hot)
    _install_fake_sleep(monkeypatch, stop_after=2)

    mqtt = FakeMQTTClient(connected=True)
    broadcasts: list[dict] = []

    async def ws_broadcast(msg: dict) -> None:
        broadcasts.append(msg)

    with pytest.raises(_StopLoop):
        await tl.run_temperature_log_loop(
            FakeDBManager(), mqtt, "box1", lambda d, a: f"minabox/box1/{d}/{a}", ws_broadcast
        )

    assert mqtt.published, "overheating must be published over MQTT"
    topic, payload = mqtt.published[0]
    assert payload["code"] == "temperature_high"
    assert broadcasts and broadcasts[0]["type"] == "system_alert"
    assert tl.get_current_alert() is not None


@pytest.mark.asyncio
async def test_cooling_down_clears_the_alert(monkeypatch):
    """Dropping back below the threshold clears the alert again."""
    monkeypatch.setattr(tl, "_read_temperature_warning_celsius", lambda: 80.0)
    monkeypatch.setattr(tl, "_log_temperature", lambda session, temp: None)

    readings = iter([91.0, 55.0])

    async def changing():
        return {"temperature_celsius": next(readings)}

    monkeypatch.setattr(tl, "_fetch_host_status", changing)
    _install_fake_sleep(monkeypatch, stop_after=3)

    mqtt = FakeMQTTClient(connected=True)
    with pytest.raises(_StopLoop):
        await tl.run_temperature_log_loop(
            FakeDBManager(), mqtt, "box1", lambda d, a: f"minabox/box1/{d}/{a}", None
        )

    assert len(mqtt.published) == 2
    assert mqtt.published[1][1] == {"reason": "temperature_normal"}
    assert tl.get_current_alert() is None


@pytest.mark.asyncio
async def test_failing_sample_does_not_kill_the_loop(monkeypatch):
    """An unexpected error in one sample must be logged, not fatal."""
    calls = 0

    async def explodes():
        nonlocal calls
        calls += 1
        raise RuntimeError("host-helper returned nonsense")

    monkeypatch.setattr(tl, "_fetch_host_status", explodes)
    _install_fake_sleep(monkeypatch, stop_after=3)

    with pytest.raises(_StopLoop):
        await tl.run_temperature_log_loop(
            FakeDBManager(), FakeMQTTClient(), "box1", lambda d, a: f"{d}/{a}", None
        )

    assert calls == 2, "loop must keep sampling after an error"
