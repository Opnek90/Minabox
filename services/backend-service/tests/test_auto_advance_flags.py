"""Regression test: a deliberate stop must not swallow the *next* track end.

Every deliberate stop (user stop, tag removed, sleep timer, daily limit, loop
guard) sets `deliberate_stop` and clears `playback_intent_active` together. The
auto-advance branch checked the intent first, so the `deliberate_stop` branch --
the only place that reset the flag -- never ran. The flag stayed set, and the
next track that ended on its own was mistaken for a deliberate stop: no next
track, no repeat, no configured end behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_service.core.handlers.audio_handler import AudioHandler


class RecordingButtonHandler:
    def __init__(self) -> None:
        self.next_calls = 0

    async def _handle_next(self) -> None:
        self.next_calls += 1


class RecordingTimerHandler:
    """Only the two calls the audio handler makes on the play/stop edges."""

    def __init__(self) -> None:
        self.started = 0
        self.cancelled = 0

    def start_limit_warning(self) -> None:
        self.started += 1

    def cancel_limit_warning(self) -> None:
        self.cancelled += 1


class FakeDispatcher:
    def __init__(self) -> None:
        self.audio_status_cache: dict = {}
        self._last_audio_status: dict = {}
        self.stream_reconnect_task = None
        self.stream_reconnect_attempts = 0
        self.playback_intent_active = True
        self.deliberate_stop = False
        self.websocket_manager = None
        self.button_handler = RecordingButtonHandler()
        # The spoken warning before the listening time is over hangs off the
        # same play/stop transitions this file is about.
        self.timer_handler = RecordingTimerHandler()

    def mark_deliberate_stop(self) -> None:
        self.deliberate_stop = True


@pytest.fixture(autouse=True)
def _no_daily_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    (tmp_path / "general_settings.json").write_text(
        json.dumps({"daily_limit_enabled": False}), encoding="utf-8"
    )


async def _play_then_stop(handler: AudioHandler) -> None:
    await handler.handle_audio_status("t", {"state": "playing", "track_id": "1"})
    await handler.handle_audio_status("t", {"state": "stopped", "track_id": "1"})


@pytest.mark.asyncio
async def test_track_ending_on_its_own_advances() -> None:
    dispatcher = FakeDispatcher()
    handler = AudioHandler(dispatcher)

    await _play_then_stop(handler)

    assert dispatcher.button_handler.next_calls == 1


@pytest.mark.asyncio
async def test_deliberate_stop_does_not_advance() -> None:
    dispatcher = FakeDispatcher()
    handler = AudioHandler(dispatcher)

    await handler.handle_audio_status("t", {"state": "playing", "track_id": "1"})
    dispatcher.mark_deliberate_stop()
    dispatcher.playback_intent_active = False
    await handler.handle_audio_status("t", {"state": "stopped", "track_id": "1"})

    assert dispatcher.button_handler.next_calls == 0


@pytest.mark.asyncio
async def test_flag_does_not_survive_into_the_next_session() -> None:
    dispatcher = FakeDispatcher()
    handler = AudioHandler(dispatcher)

    # A deliberate stop, exactly as every caller performs it.
    await handler.handle_audio_status("t", {"state": "playing", "track_id": "1"})
    dispatcher.mark_deliberate_stop()
    dispatcher.playback_intent_active = False
    await handler.handle_audio_status("t", {"state": "stopped", "track_id": "1"})
    assert dispatcher.deliberate_stop is False

    # New card: this track runs out by itself and must advance.
    dispatcher.playback_intent_active = True
    await _play_then_stop(handler)

    assert dispatcher.button_handler.next_calls == 1
