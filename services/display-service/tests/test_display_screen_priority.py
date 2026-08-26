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
from display_test_doubles import FakePanel

from display_service.config_schema import DisplayServiceConfig
from display_service.main import (
    SCREEN_HUD,
    SCREEN_IDLE,
    SCREEN_NOTICE,
    SCREEN_PLAYING,
    SCREEN_TEST,
    DisplayService,
)
from display_service.render.quota_over import render as render_quota
from display_service.render.tag_blocked import render as render_blocked
from display_service.render.unknown_tag import render as render_unknown

STATUS = "minabox/box1/audio/status"
UNKNOWN = "minabox/box1/rfid/unknown-tag"
BLOCKED = "minabox/box1/rfid/tag-blocked"
QUOTA = "minabox/box1/led/usage-denied"
SCANNED = "minabox/box1/rfid/tag-scanned"
REMOVED = "minabox/box1/rfid/tag-removed"


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
        enabled=True
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
        service._notice = ("unknown_tag", "")
        service._notice_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_NOTICE

    @pytest.mark.asyncio
    async def test_the_volume_overlay_beats_an_unknown_figure(
        self, service: DisplayService
    ):
        """Both are gestures, but the knob is the one under a hand right now."""
        service._notice = ("unknown_tag", "")
        service._notice_until = 200.0
        service._hud_view = service.state_manager.get_volume_view()
        service._hud_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_HUD

    @pytest.mark.asyncio
    async def test_the_test_pattern_beats_everything(self, service: DisplayService):
        """It was asked for, and answering a different question is useless."""
        _playing(service)
        service._notice = ("unknown_tag", "")
        service._notice_until = 200.0
        service._hud_view = service.state_manager.get_volume_view()
        service._hud_until = 200.0
        service._test_pattern_until = 200.0
        assert service._current_screen(now=100.0) == SCREEN_TEST

    @pytest.mark.asyncio
    async def test_an_expired_notice_stops_winning(
        self, service: DisplayService
    ):
        service._notice = ("unknown_tag", "")
        service._notice_until = 50.0
        assert service._current_screen(now=100.0) == SCREEN_IDLE


# ---------------------------------------------------------------------------
# The unknown figure
# ---------------------------------------------------------------------------


class TestNotices:
    """The three ways a figure ends in nothing happening."""

    @pytest.mark.asyncio
    async def test_a_blocked_figure_says_so_and_names_it(
        self, panel, service: DisplayService, fast_loop
    ):
        """"Wer bist du?" would be a lie: the box knows this one perfectly
        well, it is just not allowed to play it."""
        _configured(service)
        service._handle_mqtt_message(
            BLOCKED, json.dumps({"tag_id": "04A1", "name": "Bibi"}).encode()
        )

        await _run(service)

        assert panel.frames[-1].tobytes() == render_blocked("Bibi").tobytes()
        assert panel.frames[-1].tobytes() != render_unknown().tobytes()

    @pytest.mark.asyncio
    async def test_a_blocked_figure_without_a_name_still_works(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        service._handle_mqtt_message(BLOCKED, b'{"tag_id": "04A1"}')

        await _run(service)

        assert panel.frames[-1].tobytes() == render_blocked("").tobytes()

    @pytest.mark.asyncio
    async def test_the_daily_limit_gets_its_own_picture(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        service._handle_mqtt_message(QUOTA, b'{"event": "usage_denied"}')

        await _run(service)

        assert panel.frames[-1].tobytes() == render_quota().tobytes()

    @pytest.mark.asyncio
    async def test_the_three_look_different_from_one_another(self):
        frames = {
            render_unknown().tobytes(),
            render_blocked("Bibi").tobytes(),
            render_quota().tobytes(),
        }
        assert len(frames) == 3


class TestWaveOnFigures:
    @pytest.mark.asyncio
    async def test_a_figure_arriving_makes_him_wave(self, service: DisplayService):
        from display_service.render import knuffel

        service._handle_mqtt_message(SCANNED, b'{"tag_id": "04A1"}')
        assert service._idle_animation is not None
        assert service._idle_animation.pose().mood in knuffel.WAVING

    @pytest.mark.asyncio
    async def test_a_figure_leaving_makes_him_wave_too(self, service: DisplayService):
        """The greeting on arrival is usually cut short by playback taking the
        panel; on removal it plays out, which is where it is seen."""
        from display_service.render import knuffel

        service._handle_mqtt_message(REMOVED, b'{"tag_id": "04A1"}')
        assert service._idle_animation.pose().mood in knuffel.WAVING

    @pytest.mark.asyncio
    async def test_waving_does_not_leave_a_deadline_in_the_past(
        self, service: DisplayService
    ):
        """Abandoning a walk mid-way is exactly how the loop ends up spinning."""
        now = asyncio.get_running_loop().time()
        animation = service._idle(now)
        for _ in range(500):
            now = animation.next_due()
            animation.advance(now)
        animation.wave_now(now)
        assert animation.next_due() > now


class TestUnknownTag:
    @pytest.mark.asyncio
    async def test_the_message_raises_the_screen(self, service: DisplayService):
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now) == SCREEN_NOTICE

    @pytest.mark.asyncio
    async def test_it_does_not_stay(self, service: DisplayService):
        """It reports an event, not a state."""
        service._handle_mqtt_message(UNKNOWN, b'{"tag_id": "04A1B2"}')
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now + 3.0) == SCREEN_NOTICE
        assert service._current_screen(now + 10.0) == SCREEN_IDLE

    @pytest.mark.asyncio
    async def test_a_malformed_message_still_shows_it(self, service: DisplayService):
        """Nothing in the payload is read; the topic is the whole message."""
        service._handle_mqtt_message(UNKNOWN, b"not json")
        now = asyncio.get_running_loop().time()
        assert service._current_screen(now) == SCREEN_NOTICE

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


class TestIdleMarks:
    """What the widget grid used to carry in a corner, and took with it."""

    @staticmethod
    def _marks_area(img):
        """Only where the marks themselves sit.

        A wider box was useless: Knuffel keeps clear of the strip, but his
        waving hand still reaches into the top right, so the area was never
        empty and the test passed with the marks removed.
        """
        from display_service.render import marks

        left = 128 - marks.GAP - marks.SIZE
        pixels = img.load()
        return sum(
            1
            for x in range(left, 128 - marks.GAP + 1)
            for y in range(2, 2 + marks.SIZE)
            if pixels[x, y]
        )

    @pytest.mark.asyncio
    async def test_nothing_is_marked_in_the_ordinary_case(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        _playing(service, state="stopped")

        await _run(service)

        assert self._marks_area(panel.frames[-1]) == 0

    @pytest.mark.asyncio
    async def test_a_recent_error_is_marked(
        self, panel, service: DisplayService, fast_loop
    ):
        """It went with the grid: the flag is still kept and was shown nowhere."""
        _configured(service)
        _playing(service, state="stopped")
        service.state_manager.set_error()

        await _run(service)

        assert self._marks_area(panel.frames[-1]) > 0

    @pytest.mark.asyncio
    async def test_a_running_sleep_timer_is_marked(
        self, panel, service: DisplayService, fast_loop
    ):
        _configured(service)
        _playing(service, state="stopped")
        service.state_manager.update_sleep_timer(True, 600_000)

        await _run(service)

        assert self._marks_area(panel.frames[-1]) > 0

    @pytest.mark.asyncio
    async def test_knuffel_keeps_out_from_under_them(
        self, service: DisplayService
    ):
        """Two lit shapes on a one-bit panel simply merge, so he stays clear
        rather than walking underneath."""
        from display_service.core.idle_animation import BOUNDS
        from display_service.render.idle import strip_width

        now = asyncio.get_running_loop().time()
        animation = service._idle(now)
        reserved = strip_width(("error", "sleep_timer"))
        assert reserved > 0
        animation.set_reserved(reserved, now)
        limit = BOUNDS[2] - reserved

        # He walks out rather than jumping, so give him the walk first.
        for _ in range(200):
            now = animation.next_due()
            animation.advance(now)
            if animation.pose().x <= limit:
                break
        else:
            pytest.fail("never left the strip")

        for _ in range(3_000):
            now = animation.next_due()
            animation.advance(now)
            assert animation.pose().x <= limit

    @pytest.mark.asyncio
    async def test_the_service_reserves_the_strip_when_it_draws_them(
        self, service: DisplayService
    ):
        """Drawing the marks and keeping him out from under them are two
        separate things, and only the first one is visible in a frame."""
        from display_service.main import SCREEN_IDLE
        from display_service.render.idle import strip_width

        now = asyncio.get_running_loop().time()
        assert service._idle(now).reserved == 0

        service.state_manager.set_error()
        service._screen_frame(SCREEN_IDLE, now)
        assert service._idle(now).reserved == strip_width(("error",))
