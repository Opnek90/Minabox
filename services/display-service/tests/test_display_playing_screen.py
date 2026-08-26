"""The playing screen end to end: where its numbers come from, and when it
reaches the panel.

The remaining time is counted here rather than asked for. position_ms is
deliberately excluded from the audio service's status fingerprint so a playing
track does not publish every two seconds, so the panel has exactly one anchor
per track and counts on from it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
from display_test_doubles import FakePanel, element

from display_service.config_schema import DisplayServiceConfig
from display_service.core.state_manager import StateManager
from display_service.main import DisplayService
from display_service.render.playing import render as render_playing

STATUS = "minabox/box1/audio/status"
M = 60_000


class _Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> _Clock:
    """A clock handed to the StateManager, never patched onto the time module.

    ``monkeypatch.setattr("...state_manager.time.monotonic", ...)`` patches the
    time module itself, and asyncio takes its event loop clock from there: a
    frozen one stops every await in the process, so the render loop tests hang
    rather than fail.
    """
    return _Clock()


@pytest.fixture
def playing_service(service: DisplayService, clock: _Clock) -> DisplayService:
    service.state_manager = StateManager("box1", clock=clock)
    return service


def _audio(sm: StateManager, **fields) -> None:
    payload = {
        "state": "playing",
        "track_id": "t1",
        "position_ms": 0,
        "duration_ms": 10 * M,
        **fields,
    }
    sm.update_audio(STATUS, json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# Counting the remainder
# ---------------------------------------------------------------------------


def test_the_remaining_time_counts_down_without_a_new_message(clock):
    sm = StateManager("box1", clock=clock)
    _audio(sm)
    assert sm.get_playing_view().remaining_ms == 10 * M

    clock.advance(120)
    assert sm.get_playing_view().remaining_ms == pytest.approx(8 * M, abs=100)


def test_a_paused_track_does_not_count_down(clock):
    sm = StateManager("box1", clock=clock)
    _audio(sm, state="paused", position_ms=2 * M)
    before = sm.get_playing_view().remaining_ms
    clock.advance(300)
    assert sm.get_playing_view().remaining_ms == before


def test_a_seek_re_anchors_the_count(clock):
    """Seeking republishes the status, which is the only correction available -
    hence the audio service waiting for VLC to confirm the jump first."""
    sm = StateManager("box1", clock=clock)
    _audio(sm)
    clock.advance(60)
    _audio(sm, position_ms=9 * M)
    assert sm.get_playing_view().remaining_ms == pytest.approx(1 * M, abs=100)


def test_a_track_without_a_length_has_no_remaining_time(clock):
    sm = StateManager("box1", clock=clock)
    _audio(sm, duration_ms=None)
    view = sm.get_playing_view()
    assert view.remaining_ms is None
    assert view.duration_ms is None


def test_a_stopped_player_reporting_minus_one_is_not_a_position(clock):
    sm = StateManager("box1", clock=clock)
    _audio(sm, position_ms=-1)
    assert sm.get_audio()["position_ms"] == 0


def test_playing_and_paused_count_as_playing_but_stopped_does_not(clock):
    sm = StateManager("box1", clock=clock)
    _audio(sm)
    assert sm.is_playing()
    _audio(sm, state="paused")
    assert sm.is_playing()
    _audio(sm, state="stopped")
    assert not sm.is_playing()


def test_mute_reaches_the_playing_screen(clock):
    """The widget grid carries a permanent mute icon and this screen replaces
    it, so the icon has to come along - playback is when it matters."""
    sm = StateManager("box1", clock=clock)
    _audio(sm, muted=True)
    assert sm.get_playing_view().muted


# ---------------------------------------------------------------------------
# The title
# ---------------------------------------------------------------------------


def test_the_title_is_the_current_entry_in_the_queue():
    data = {
        "queue": [
            {"title": "Vorher", "is_current": False},
            {"title": "Ein Lama in Yokohama", "is_current": True},
            {"title": "Danach", "is_current": False},
        ]
    }
    assert DisplayService._current_title(data) == "Ein Lama in Yokohama"


def test_an_empty_queue_is_not_an_error():
    assert DisplayService._current_title({"queue": []}) == ""
    assert DisplayService._current_title({}) == ""


def test_a_queue_entry_without_a_title_does_not_crash():
    data = {"queue": [{"is_current": True}]}
    assert DisplayService._current_title(data) == ""


@pytest.mark.asyncio
async def test_a_track_change_asks_for_a_fresh_session(service: DisplayService):
    """Fifteen seconds is fine for repeat and shuffle; a stale title is not."""
    service._handle_mqtt_message(
        STATUS, json.dumps({"state": "playing", "track_id": "t1"}).encode()
    )
    service._session_refresh.clear()

    service._handle_mqtt_message(
        STATUS, json.dumps({"state": "playing", "track_id": "t2"}).encode()
    )
    assert service._session_refresh.is_set()


@pytest.mark.asyncio
async def test_the_same_track_does_not(service: DisplayService):
    service._handle_mqtt_message(
        STATUS, json.dumps({"state": "playing", "track_id": "t1"}).encode()
    )
    service._session_refresh.clear()
    same = {"state": "playing", "track_id": "t1", "volume": 30}
    service._handle_mqtt_message(STATUS, json.dumps(same).encode())
    assert not service._session_refresh.is_set()


# ---------------------------------------------------------------------------
# What reaches the panel
# ---------------------------------------------------------------------------


@pytest.fixture
def panel(monkeypatch) -> FakePanel:
    fake = FakePanel(available=True)
    monkeypatch.setattr("display_service.main.is_available", fake.is_available)
    monkeypatch.setattr("display_service.main.display_init", fake.init)
    monkeypatch.setattr("display_service.main.display_shutdown", fake.shutdown)
    monkeypatch.setattr("display_service.main.clear", fake.clear)
    monkeypatch.setattr("display_service.main.show_image", fake.show_image)
    monkeypatch.setattr("display_service.main.show_lines", fake.show_lines)
    return fake


async def _run_briefly(service: DisplayService, seconds: float = 0.06) -> None:
    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(seconds)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.fixture
def fast_loop(monkeypatch):
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)


@pytest.mark.asyncio
async def test_the_playing_screen_replaces_the_grid_while_playing(
    panel, service: DisplayService, fast_loop
):
    service._display_config = DisplayServiceConfig(
        enabled=True, elements=[element("clock", area=0)]
    )
    _audio(service.state_manager)

    await _run_briefly(service)

    assert "show_image" in panel.names
    assert panel.frames[-1].tobytes() == render_playing(
        service.state_manager.get_playing_view()
    ).tobytes()


@pytest.mark.asyncio
async def test_the_idle_screen_comes_back_when_playback_stops(
    panel, playing_service: DisplayService, fast_loop, clock
):
    service = playing_service
    service._display_config = DisplayServiceConfig(
        enabled=True, elements=[element("clock", area=0)]
    )
    _audio(service.state_manager, state="stopped")

    await _run_briefly(service)

    assert "show_image" in panel.names
    # Knuffel, not a track: the playing screen would carry a progress bar.
    drawn = panel.frames[-1]
    assert drawn.tobytes() != render_playing(
        service.state_manager.get_playing_view()
    ).tobytes()


@pytest.mark.asyncio
async def test_it_does_not_push_a_frame_on_every_tick(
    panel, service: DisplayService, fast_loop
):
    """A full frame holds the shared I2C bus for 92 ms. The bar is quantised to
    the pixel step it is drawn in, so ticks in between change nothing."""
    service._display_config = DisplayServiceConfig(
        enabled=True, elements=[element("clock", area=0)]
    )
    _audio(service.state_manager, duration_ms=60 * 60 * 1000)  # an hour

    await _run_briefly(service, seconds=0.15)

    assert panel.names.count("show_image") == 1


@pytest.mark.asyncio
async def test_the_bar_is_redrawn_as_the_track_advances(
    panel, playing_service: DisplayService, fast_loop, clock
):
    service = playing_service
    """The counterpart to the test above: quantising must not freeze the bar."""
    service._display_config = DisplayServiceConfig(
        enabled=True, elements=[element("clock", area=0)]
    )
    _audio(service.state_manager, duration_ms=2 * M)

    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(0.05)
    drawn_first = panel.names.count("show_image")

    clock.advance(20)  # a sixth of the track: far more than one pixel step
    await asyncio.sleep(0.05)

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert drawn_first == 1
    assert panel.names.count("show_image") == 2
