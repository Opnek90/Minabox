"""Tests for the shared fade-out used by sleep timer, daily limit and loop guard.

Two bugs are pinned down here:

1. `_bedtime_fade_coroutine` aborted as soon as no sleep timer was running.
   The daily-limit fade has no sleep timer, so it waited one interval and then
   stopped hard - it never faded anything.
2. A fade ended at (or near) zero and left the volume there. After a sleep
   timer the box was mute the next morning and looked broken.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend_service.core.handlers.timer_handler import TimerHandler


class FakeMQTTClient:
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict]] = []

    async def publish_audio_command(self, command: str, payload: dict) -> None:
        self.commands.append((command, payload))

    def volumes(self) -> list[int]:
        return [p["volume"] for c, p in self.commands if c == "set-volume"]


class FakeDispatcher:
    def __init__(self, volume: int = 40) -> None:
        self.mqtt_client = FakeMQTTClient()
        self.audio_status_cache = {"volume": volume}
        self.playback_intent_active = True
        self.deliberate_stop = False
        self.websocket_manager = None

    def mark_deliberate_stop(self) -> None:
        self.deliberate_stop = True


@pytest.fixture
def fade_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    def write(enabled: bool = True, **values: object) -> None:
        (tmp_path / "general_settings.json").write_text(
            json.dumps({"bedtime_fade_enabled": enabled, **values}), encoding="utf-8"
        )

    return write


@pytest.fixture
def instant_sleep(monkeypatch: pytest.MonkeyPatch):
    """Run the fade without waiting out its real intervals.

    `th.asyncio` is the asyncio module itself, so the real sleep has to be
    captured before patching - otherwise the replacement calls itself.
    """
    from backend_service.core.handlers import timer_handler as th

    real_sleep = asyncio.sleep

    async def fake_sleep(_seconds: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(th.asyncio, "sleep", fake_sleep)
    return real_sleep


@pytest.mark.asyncio
async def test_fade_actually_steps_the_volume_down(fade_settings, instant_sleep) -> None:
    fade_settings(
        bedtime_fade_duration_minutes=2,
        bedtime_fade_interval_seconds=30,
        bedtime_fade_step_percent=10,
    )
    dispatcher = FakeDispatcher(volume=40)
    handler = TimerHandler(dispatcher)

    await handler.fade_out_and_stop("daily_limit")

    # No sleep timer is involved here - the fade must still run.
    assert dispatcher.mqtt_client.volumes()[:4] == [30, 20, 10, 0]
    assert ("stop", {}) in dispatcher.mqtt_client.commands
    assert dispatcher.deliberate_stop is True


@pytest.mark.asyncio
async def test_volume_is_restored_after_the_fade(fade_settings, instant_sleep) -> None:
    fade_settings(
        bedtime_fade_duration_minutes=2,
        bedtime_fade_interval_seconds=30,
        bedtime_fade_step_percent=10,
    )
    dispatcher = FakeDispatcher(volume=40)
    handler = TimerHandler(dispatcher)

    await handler.fade_out_and_stop("loop_guard")

    commands = dispatcher.mqtt_client.commands
    stop_index = commands.index(("stop", {}))
    # The box must not be left mute: the last thing that happens is putting the
    # volume back, after the stop so nothing becomes audible again.
    assert commands[stop_index + 1] == ("set-volume", {"volume": 40})
    assert handler.volume_before_fade is None


@pytest.mark.asyncio
async def test_fade_gives_up_once_playback_has_ended(fade_settings, instant_sleep) -> None:
    """The content can run out mid-fade; the fade must not keep going then."""
    fade_settings(
        bedtime_fade_duration_minutes=10,
        bedtime_fade_interval_seconds=30,
        bedtime_fade_step_percent=1,
    )
    dispatcher = FakeDispatcher(volume=40)
    handler = TimerHandler(dispatcher)

    real_sleep = instant_sleep

    async def end_playback_after_two_steps() -> None:
        while len(dispatcher.mqtt_client.volumes()) < 2:
            await real_sleep(0)
        dispatcher.playback_intent_active = False

    await asyncio.gather(handler.fade_out_and_stop("loop_guard"), end_playback_after_two_steps())

    # Without the guard this would have stepped all the way down (20 steps).
    assert len(dispatcher.mqtt_client.volumes()) < 20
    assert ("stop", {}) in dispatcher.mqtt_client.commands


@pytest.mark.asyncio
async def test_disabled_fade_still_stops_immediately(fade_settings) -> None:
    fade_settings(enabled=False)
    dispatcher = FakeDispatcher(volume=40)
    handler = TimerHandler(dispatcher)

    await handler.fade_out_and_stop("loop_guard")

    assert dispatcher.mqtt_client.volumes() == []
    assert dispatcher.mqtt_client.commands == [("stop", {})]
