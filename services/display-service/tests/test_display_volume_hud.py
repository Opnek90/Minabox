"""When the volume overlay takes the panel, and when it gives it back.

The overlay is the one screen the box is used for constantly, so the rules
around it are worth pinning down: it must appear on a real change, it must not
appear because a retained status was replayed, and it must hand the panel back
to whatever was underneath.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
from display_test_doubles import FakePanel

from display_service.config_schema import DisplayServiceConfig
from display_service.main import DisplayService

STATUS = "minabox/box1/audio/status"


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


@pytest.fixture
def fast_hud(monkeypatch):
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)
    monkeypatch.setattr("display_service.main.HUD_SECONDS", 0.08)


def _configured(service: DisplayService) -> DisplayService:
    service._display_config = DisplayServiceConfig(
        enabled=True
    )
    return service


def _status(service: DisplayService, volume: int, **fields) -> None:
    # Stopped on purpose: the screen underneath the overlay is then the widget
    # grid, so "the panel came back" is a show_areas and stays readable as an
    # assertion. What the playing screen does is covered in its own file.
    payload = {
        "state": "stopped",
        "volume": volume,
        "min_volume": 20,
        "max_volume": 40,
        "volume_step": 5,
        **fields,
    }
    service._handle_mqtt_message(STATUS, json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# When it is raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_status_does_not_flash_the_overlay(service: DisplayService):
    """A restart replays the retained status; that is state, not a change."""
    _status(service, 20)
    assert service._hud_view is None


@pytest.mark.asyncio
async def test_a_volume_change_raises_the_overlay(service: DisplayService):
    _status(service, 20)
    _status(service, 30)
    assert service._hud_view is not None
    # The box allows 20 to 40, so 30 is halfway - not "30 %".
    assert service._hud_view.percent == 50


@pytest.mark.asyncio
async def test_a_republished_identical_status_does_not(service: DisplayService):
    _status(service, 20)
    _status(service, 25)
    service._hud_view = None
    _status(service, 25)
    assert service._hud_view is None


@pytest.mark.asyncio
async def test_a_track_change_does_not(service: DisplayService):
    """audio/status carries far more than the volume."""
    _status(service, 20)
    _status(service, 20, track_id="other")
    assert service._hud_view is None


@pytest.mark.asyncio
async def test_mute_raises_the_overlay(service: DisplayService):
    _status(service, 20)
    _status(service, 20, muted=True)
    assert service._hud_view is not None
    assert service._hud_view.muted


@pytest.mark.asyncio
async def test_a_new_maximum_changes_what_the_same_volume_means(
    service: DisplayService,
):
    _status(service, 30)
    _status(service, 30, max_volume=80)
    assert service._hud_view is not None
    # Same level, a wider range: 30 is now near the bottom of 20 to 80.
    assert service._hud_view.percent == 17


# ---------------------------------------------------------------------------
# What reaches the panel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_overlay_is_drawn_and_then_gives_the_panel_back(
    panel, service: DisplayService, fast_hud
):
    _configured(service)
    _status(service, 20)

    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(0.03)
    drawn_before = len(panel.frames)

    _status(service, 25)
    await asyncio.sleep(0.03)
    overlay = panel.frames[-1]

    await asyncio.sleep(0.12)  # past the overlay deadline
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(panel.frames) > drawn_before
    assert panel.frames[-1].tobytes() != overlay.tobytes(), "overlay still up"


@pytest.mark.asyncio
async def test_a_turn_of_the_knob_does_not_become_a_frame_per_detent(
    panel, service: DisplayService, monkeypatch
):
    """The I2C bus is shared with the RFID reader; a burst has to collapse."""
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.05)
    monkeypatch.setattr("display_service.main.HUD_SECONDS", 1.0)
    _configured(service)
    _status(service, 0)

    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(0.02)
    # Spread out the way a hand turns a knob, so the loop really does get a
    # chance to run between detents - fed in one go it could only ever
    # produce a single frame and the test would prove nothing.
    for volume in (5, 10, 15, 20, 25, 30, 35, 40):
        _status(service, volume)
        await asyncio.sleep(0.012)
    await asyncio.sleep(0.06)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    frames = panel.names.count("show_image")
    assert 1 <= frames <= 4, f"eight detents produced {frames} frames"


@pytest.mark.asyncio
async def test_a_config_redraw_does_not_stomp_the_overlay(
    panel, service: DisplayService
):
    _configured(service)
    _status(service, 20)
    _status(service, 25)
    before = panel.names.count("show_areas")
    service._redraw_now()
    assert panel.names.count("show_areas") == before


@pytest.mark.asyncio
async def test_the_test_pattern_outranks_the_overlay(panel, service: DisplayService):
    """Otherwise the overlay reappears on top of what the user asked to see."""
    _configured(service)
    _status(service, 20)
    _status(service, 25)
    assert await service.show_test_pattern()
    assert service._hud_view is None
    assert service._hud_until == 0.0


@pytest.mark.asyncio
async def test_the_panel_comes_back_without_waiting_out_the_tick(
    panel, service: DisplayService, monkeypatch
):
    """The loop ticks once a second; an overlay must not outlive its deadline
    by most of a tick, or a 1.5 s overlay stands for 2.5 s."""
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 5.0)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)
    monkeypatch.setattr("display_service.main.HUD_SECONDS", 0.05)
    _configured(service)
    _status(service, 20)

    task = asyncio.create_task(service._render_loop())
    _status(service, 25)
    await asyncio.sleep(0.03)
    overlay = panel.frames[-1]

    await asyncio.sleep(0.15)  # well past the deadline, far short of a tick
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert panel.frames[-1].tobytes() != overlay.tobytes(), (
        "the overlay was still holding the panel"
    )


@pytest.mark.asyncio
async def test_an_expired_overlay_is_dropped_even_with_no_panel(
    panel, service: DisplayService, monkeypatch
):
    """Left standing, it keeps the loop waking against a deadline in the past
    - which on an unplugged panel means spinning at 20 Hz for as long as it
    stays away."""
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)
    monkeypatch.setattr("display_service.main.DISPLAY_INIT_RETRY_INTERVAL", 999.0)
    monkeypatch.setattr("display_service.main.HUD_SECONDS", 0.02)
    _configured(service)
    _status(service, 20)
    _status(service, 25)
    assert service._hud_view is not None

    panel.available = False
    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert service._hud_view is None


@pytest.mark.asyncio
async def test_a_volume_that_moves_with_the_play_state_is_not_a_gesture(
    service: DisplayService,
):
    """Lifting the figure stopped playback, and the volume reported alongside
    it dropped to the minimum - libVLC answers -1 once stop() has released the
    media. The panel must not turn that into a full-screen "Leise"."""
    _status(service, 30, state="playing")
    _status(service, 20, state="stopped")
    assert service._hud_view is None


@pytest.mark.asyncio
async def test_the_knob_still_works_while_stopped(service: DisplayService):
    """Adjusting the volume between tracks is ordinary, and must still show."""
    _status(service, 30, state="stopped")
    _status(service, 25, state="stopped")
    assert service._hud_view is not None


@pytest.mark.asyncio
async def test_a_volume_outside_the_allowed_range_is_not_a_volume(
    service: DisplayService,
):
    """Putting a figure on used to raise the overlay: libVLC reports 0 in the
    moment after play(), while the audio output is still coming up. The box
    clamps every write into [min, max], so it cannot be at 0 when the minimum
    is 20 - and the level either side of the artefact is unchanged."""
    _status(service, 30, state="playing")
    _status(service, 0, state="playing")
    assert service._hud_view is None
    _status(service, 30, state="playing")
    assert service._hud_view is None, "the level never actually changed"


@pytest.mark.asyncio
async def test_an_artefact_does_not_hide_a_real_change_after_it(
    service: DisplayService,
):
    _status(service, 30, state="playing")
    _status(service, 0, state="playing")
    _status(service, 25, state="playing")
    assert service._hud_view is not None
