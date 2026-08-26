"""Which screen owns the panel, and what an unknown figure does.

Priority used to be implicit in a chain of early returns in the render loop.
It is the only thing that decides what a person actually sees, so it is now one
method with one order, and this is where that order is written down.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
from display_test_doubles import FakePanel, element

from display_service.config_schema import DisplayServiceConfig
from display_service.main import (
    SCREEN_HUD,
    SCREEN_IDLE,
    SCREEN_PLAYING,
    SCREEN_TEST,
    SCREEN_UNKNOWN,
    DisplayService,
)
from display_service.render.unknown_tag import render as render_unknown

STATUS = "minabox/box1/audio/status"
UNKNOWN = "minabox/box1/rfid/unknown-tag"


@pytest.fixture
def panel(monkeypatch) -> FakePanel:
    fake = FakePanel(available=True)
    for name, fn in (
        ("is_available", fake.is_available),
        ("display_init", fake.init),
        ("display_shutdown", fake.shutdown),
        ("clear", fake.clear),
        ("show_image", fake.show_image),
        ("show_lines", fake.show_lines),
    ):
        monkeypatch.setattr(f"display_service.main.{name}", fn)
    return fake


@pytest.fixture
def fast_loop(monkeypatch):
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)


def _configured(service: DisplayService) -> DisplayService:
    service._display_config = DisplayServiceConfig(
        enabled=True, elements=[element("clock", area=0)]
    )
    return service


def _playing(service: DisplayService, state: str = "playing") -> None:
    service._handle_mqtt_message(
        STATUS,
        json.dumps(
            {"state": state, "track_id": "t1", "position_ms": 0, "duration_ms": 60_000}
        ).encode(),
    )


async def _run(service: DisplayService, seconds: float = 0.06) -> None:
    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(seconds)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# The order
# ---------------------------------------------------------------------------


class TestPriority:
    @pytest.mark.asyncio
    async def test_nothing_playing_is_the_idle_screen(self, service: DisplayService):
        assert service._current_screen(now=100.0) == SCREEN_IDLE

    @pytest.mark.asyncio
    async def test_playing_beats_idle(self, service: DisplayService):
        _playing(service)
        assert service._current_screen(now=100.0) == SCREEN_PLAYING

    @pytest.mark.asyncio
    async def test_an_unknown_figure_beats_playing(self, service: DisplayService):
        """It reports something that just happened and needs answering."""
        _playing(service)
        service._unknown_tag_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_UNKNOWN

    @pytest.mark.asyncio
    async def test_the_volume_overlay_beats_an_unknown_figure(
        self, service: DisplayService
    ):
        """Both are gestures, but the knob is the one under a hand right now."""
        service._unknown_tag_until = 200.0
        service._hud_view = service.state_manager.get_volume_view()
        service._hud_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_HUD

    @pytest.mark.asyncio
    async def test_the_test_pattern_beats_everything(self, service: DisplayService):
        """It was asked for, and answering a different question is useless."""
        _playing(service)
        service._unknown_tag_until = 200.0
        service._hud_view = service.state_manager.get_volume_view()
        service._hud_until = 200.0
        service._test_pattern_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_TEST

    @pytest.mark.asyncio
    async def test_an_expired_unknown_figure_stops_winning(
        self, service: DisplayService
    ):
        service._unknown_tag_until = 50.0
        assert service._current_screen(now=100.0) == SCREEN_IDLE


# ---------------------------------------------------------------------------
# The unknown figure
# ---------------------------------------------------------------------------


class TestUnknownTag:
    @pytest.mark.asyncio
    async def test_the_message_raises_the_screen(self, service: DisplayService):
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now) == SCREEN_UNKNOWN

    @pytest.mark.asyncio
    async def test_it_does_not_stay(self, service: DisplayService):
        """It reports an event, not a state."""
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now + 3.0) == SCREEN_UNKNOWN
        assert service._current_screen(now + 10.0) == SCREEN_IDLE

    @pytest.mark.asyncio
    async def test_a_malformed_message_still_shows_it(self, service: DisplayService):
        """Nothing in the payload is read; the topic is the whole message."""
        service._handle_mqtt_message(UNKNOWN, b"not json")
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now) == SCREEN_UNKNOWN

    @pytest.mark.asyncio
    async def test_it_does_not_disturb_the_cached_audio_state(
        self, service: DisplayService
    ):
        _playing(service)
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')
        assert service.state_manager.is_playing()

    @pytest.mark.asyncio
    async def test_it_reaches_the_panel(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')

        await _run(service)

        assert panel.frames, "nothing was drawn"
        assert panel.frames[-1].tobytes() == render_unknown().tobytes()


# ---------------------------------------------------------------------------
# The idle screen
# ---------------------------------------------------------------------------


class TestIdleScreen:
    @pytest.mark.asyncio
    async def test_knuffel_is_drawn_when_nothing_plays(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        _playing(service, state="stopped")

        await _run(service)

        assert panel.frames, "nothing was drawn"
        # Lit pixels somewhere, and not the unknown-figure screen.
        assert panel.frames[-1].getbbox() is not None
        assert panel.frames[-1].tobytes() != render_unknown().tobytes()

    @pytest.mark.asyncio
    async def test_he_does_not_ask_for_a_frame_every_tick(
        self, panel, service: DisplayService, fast_loop
    ):
        """Between a breath and a blink there is nothing to send, and every
        frame holds the I2C bus the RFID reader shares."""
        _configured(service)
        _playing(service, state="stopped")

        await _run(service, seconds=0.3)

        # A breath is 1.2 s apart, so a third of a second is at most one frame.
        assert len(panel.frames) == 1
