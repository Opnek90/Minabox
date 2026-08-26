"""Dimming, and the panel giving up for the night.

This device stands in a child's bedroom. At full contrast at eight in the
evening it is a light source, and a single command changes that. The awkward
part is not the dimming but the window: every useful night wraps past midnight.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import time

import pytest
from display_test_doubles import FakePanel

from display_service.config_schema import BrightnessConfig, DisplayServiceConfig
from display_service.core.night import is_night
from display_service.main import SCREEN_IDLE, SCREEN_PLAYING, DisplayService


class TestIsNight:
    @pytest.mark.parametrize(
        "now,expected",
        [
            (time(19, 59), False),
            (time(20, 0), True),
            (time(23, 59), True),
            (time(0, 0), True),
            (time(3, 30), True),
            (time(6, 59), True),
            (time(7, 0), False),
            (time(12, 0), False),
        ],
    )
    def test_a_window_that_wraps_past_midnight(self, now, expected):
        """The ordinary case, and the one an interval check gets wrong."""
        assert is_night(now, "20:00", "07:00") is expected

    @pytest.mark.parametrize(
        "now,expected",
        [
            (time(12, 59), False),
            (time(13, 0), True),
            (time(14, 0), True),
            (time(15, 0), False),
        ],
    )
    def test_a_window_inside_one_day(self, now, expected):
        assert is_night(now, "13:00", "15:00") is expected

    def test_equal_ends_are_no_night_at_all(self):
        """Reading it the other way would darken a box for a setting that
        looks like it does nothing."""
        assert is_night(time(3, 0), "20:00", "20:00") is False

    @pytest.mark.parametrize("bad", ["", "24:00", "abends", "7:00:00", None])
    def test_nonsense_is_not_night(self, bad):
        assert is_night(time(3, 0), bad, "07:00") is False
        assert is_night(time(3, 0), "20:00", bad) is False


class TestBrightnessConfig:
    def test_the_defaults_are_a_working_night(self):
        b = BrightnessConfig()
        assert (b.day, b.night) == (255, 40)
        assert b.off_at_night is False

    @pytest.mark.parametrize("bad", ["24:00", "7:60", "sieben", "0700", ""])
    def test_a_time_that_is_not_a_time_is_rejected(self, bad):
        with pytest.raises(ValueError):
            BrightnessConfig(night_from=bad)

    @pytest.mark.parametrize("bad", [-1, 256])
    def test_contrast_stays_in_range(self, bad):
        with pytest.raises(ValueError):
            BrightnessConfig(day=bad)

    def test_a_config_without_it_still_has_one(self):
        assert DisplayServiceConfig().brightness.day == 255


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
        ("set_contrast", fake.set_contrast),
        ("set_visible", fake.set_visible),
    ):
        monkeypatch.setattr(f"display_service.main.{name}", fn)
    return fake


def _at(monkeypatch, hour: int, minute: int = 0) -> None:
    """Freeze the wall clock the night check reads - not the event loop's."""

    class _Now:
        @staticmethod
        def now():
            class _T:
                @staticmethod
                def time():
                    return time(hour, minute)

            return _T()

    monkeypatch.setattr("display_service.main.datetime", _Now)


def _configured(service: DisplayService, **brightness) -> DisplayService:
    service._display_config = DisplayServiceConfig(
        enabled=True, brightness=BrightnessConfig(**brightness)
    )
    return service


class TestApplyingIt:
    @pytest.mark.asyncio
    async def test_by_day_the_panel_is_bright(self, panel, service, monkeypatch):
        _configured(service)
        _at(monkeypatch, 12)
        assert service._apply_brightness(SCREEN_IDLE) is True
        assert ("contrast", 255) in panel.calls

    @pytest.mark.asyncio
    async def test_at_night_it_is_dimmed(self, panel, service, monkeypatch):
        _configured(service)
        _at(monkeypatch, 22)
        service._apply_brightness(SCREEN_IDLE)
        assert ("contrast", 40) in panel.calls

    @pytest.mark.asyncio
    async def test_the_command_is_not_repeated(self, panel, service, monkeypatch):
        """Two bytes is cheap, but the bus belongs to the RFID reader."""
        _configured(service)
        _at(monkeypatch, 22)
        for _ in range(10):
            service._apply_brightness(SCREEN_IDLE)
        assert [c for c in panel.calls if c[0] == "contrast"] == [("contrast", 40)]

    @pytest.mark.asyncio
    async def test_off_at_night_switches_the_panel_off_while_idle(
        self, panel, service, monkeypatch
    ):
        _configured(service, off_at_night=True)
        _at(monkeypatch, 22)
        assert service._apply_brightness(SCREEN_IDLE) is False
        assert ("visible", False) in panel.calls

    @pytest.mark.asyncio
    async def test_something_playing_takes_the_panel_back(
        self, panel, service, monkeypatch
    ):
        """A dark panel while music plays looks like a broken box."""
        _configured(service, off_at_night=True)
        _at(monkeypatch, 22)
        service._apply_brightness(SCREEN_IDLE)
        assert service._apply_brightness(SCREEN_PLAYING) is True
        assert ("visible", True) in panel.calls

    @pytest.mark.asyncio
    async def test_without_off_at_night_it_only_dims(self, panel, service, monkeypatch):
        _configured(service)
        _at(monkeypatch, 22)
        assert service._apply_brightness(SCREEN_IDLE) is True
        assert not [c for c in panel.calls if c[0] == "visible"]

    @pytest.mark.asyncio
    async def test_knuffel_sleeps_at_night(self, panel, service, monkeypatch):
        from display_service.render import knuffel

        _configured(service)
        now = asyncio.get_running_loop().time()
        service._idle(now)
        _at(monkeypatch, 22)
        service._apply_brightness(SCREEN_IDLE)
        assert service._idle_animation.pose().mood == knuffel.ASLEEP

    @pytest.mark.asyncio
    async def test_and_wakes_in_the_morning(self, panel, service, monkeypatch):
        from display_service.render import knuffel

        _configured(service)
        now = asyncio.get_running_loop().time()
        service._idle(now)
        _at(monkeypatch, 22)
        service._apply_brightness(SCREEN_IDLE)
        _at(monkeypatch, 9)
        service._apply_brightness(SCREEN_IDLE)
        assert service._idle_animation.pose().mood != knuffel.ASLEEP

    @pytest.mark.asyncio
    async def test_a_dark_panel_is_not_drawn_on(self, panel, service, monkeypatch):
        """The loop stops before rendering, so the frame buffer keeps what was
        there for when it wakes."""
        _configured(service, off_at_night=True)
        _at(monkeypatch, 22)
        monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
        monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)

        task = asyncio.create_task(service._render_loop())
        await asyncio.sleep(0.06)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert "show_image" not in panel.names
