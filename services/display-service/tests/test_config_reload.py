"""What a config reload does to the device, and what the render loop retries.

A reload used to only redraw. Three things followed from that, all of them
looking to the user like the setting simply did not work:

* changing the I2C address kept talking to the old one,
* switching the display off left the last frame standing on the panel,
* switching it on for a box that started with it off did nothing at all.

And init() was called exactly once, at startup, so a panel that was not ready
then stayed dark for the life of the process.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest
from display_test_doubles import FakePanel

from display_service.config_schema import DisplayServiceConfig
from display_service.main import DisplayService


@pytest.fixture
def panel(monkeypatch) -> FakePanel:
    fake = FakePanel()
    monkeypatch.setattr("display_service.main.is_available", fake.is_available)
    monkeypatch.setattr("display_service.main.display_init", fake.init)
    monkeypatch.setattr("display_service.main.display_shutdown", fake.shutdown)
    monkeypatch.setattr("display_service.main.clear", fake.clear)
    monkeypatch.setattr("display_service.main.show_image", fake.show_image)
    monkeypatch.setattr("display_service.main.show_lines", fake.show_lines)
    return fake


def _cfg(**overrides) -> DisplayServiceConfig:
    base = {"enabled": True, "i2c_bus": 1, "i2c_address": 60, "elements": []}
    base.update(overrides)
    return DisplayServiceConfig(**base)


# ---------------------------------------------------------------------------
# Address changes
# ---------------------------------------------------------------------------


def test_a_changed_address_reopens_the_device(panel, service: DisplayService):
    panel.available = True
    service._apply_hardware_config(_cfg(i2c_address=60), _cfg(i2c_address=61))
    assert panel.names == ["shutdown", "init"]
    assert panel.calls[1] == ("init", 1, 61)


def test_a_changed_bus_reopens_the_device(panel, service: DisplayService):
    panel.available = True
    service._apply_hardware_config(_cfg(i2c_bus=1), _cfg(i2c_bus=0 + 3))
    assert panel.calls == [("shutdown",), ("init", 3, 60)]


def test_an_unchanged_address_leaves_the_device_alone(panel, service: DisplayService):
    panel.available = True
    service._apply_hardware_config(_cfg(), _cfg())
    assert panel.calls == []


def test_only_the_elements_changing_leaves_the_device_alone(
    panel, service: DisplayService
):
    panel.available = True
    service._apply_hardware_config(_cfg(), _cfg())
    assert panel.calls == []


# ---------------------------------------------------------------------------
# The enabled flag
# ---------------------------------------------------------------------------


def test_switching_off_blanks_the_panel(panel, service: DisplayService):
    panel.available = True
    service._apply_hardware_config(_cfg(enabled=True), _cfg(enabled=False))
    assert panel.names == ["clear"]


def test_switching_off_without_a_panel_does_nothing(panel, service: DisplayService):
    panel.available = False
    service._apply_hardware_config(_cfg(enabled=True), _cfg(enabled=False))
    assert panel.calls == []


def test_switching_on_opens_a_panel_that_was_never_initialised(
    panel, service: DisplayService
):
    panel.available = False
    service._apply_hardware_config(_cfg(enabled=False), _cfg(enabled=True))
    assert panel.calls == [("init", 1, 60)]


def test_staying_on_with_a_working_panel_does_not_reinitialise(
    panel, service: DisplayService
):
    panel.available = True
    service._apply_hardware_config(_cfg(enabled=True), _cfg(enabled=True))
    assert panel.calls == []


def test_disabled_wins_over_a_changed_address(panel, service: DisplayService):
    """No point opening the new address just to leave it dark."""
    panel.available = True
    service._apply_hardware_config(
        _cfg(i2c_address=60), _cfg(i2c_address=61, enabled=False)
    )
    assert panel.names == ["shutdown"]


def test_a_first_load_has_nothing_to_compare_against(panel, service: DisplayService):
    """previous is None at startup; start() owns the first init, not this."""
    panel.available = True
    service._apply_hardware_config(None, _cfg())
    assert panel.calls == []


# ---------------------------------------------------------------------------
# The redraw that follows a reload
# ---------------------------------------------------------------------------


def test_a_reload_asks_the_loop_for_a_frame(panel, service: DisplayService):
    """It used to draw the widget grid here. The grid is gone - every state
    has its own screen now - and drawing from two places would race the render
    loop for the panel. So this only wakes it."""
    panel.available = True
    service._display_config = _cfg()
    service._redraw_now()
    assert service._wake.is_set()
    assert panel.names == []


def test_no_redraw_without_a_panel(panel, service: DisplayService):
    panel.available = False
    service._display_config = _cfg()
    service._redraw_now()
    assert panel.calls == []


def test_no_redraw_while_disabled(panel, service: DisplayService):
    panel.available = True
    service._display_config = _cfg(enabled=False)
    service._redraw_now()
    assert panel.calls == []


def test_no_redraw_when_there_is_nothing_to_draw(panel, service: DisplayService):
    panel.available = True
    service._display_config = _cfg(elements=[])
    service._redraw_now()
    assert panel.calls == []


@pytest.mark.asyncio
async def test_a_reload_does_not_wipe_the_test_pattern(panel, service: DisplayService):
    """Saving display settings while the six-second test pattern is up."""
    panel.available = True
    service._display_config = _cfg()
    service._test_pattern_until = asyncio.get_running_loop().time() + 6.0

    service._redraw_now()
    assert panel.calls == []


@pytest.mark.asyncio
async def test_the_redraw_returns_once_the_test_pattern_expired(
    panel, service: DisplayService
):
    panel.available = True
    service._display_config = _cfg()
    service._test_pattern_until = asyncio.get_running_loop().time() - 1.0

    service._redraw_now()
    assert service._wake.is_set()


# ---------------------------------------------------------------------------
# The full reload path
# ---------------------------------------------------------------------------


def test_a_failed_reload_keeps_the_previous_config(
    panel, service: DisplayService, monkeypatch
):
    """The running service must survive a file it cannot load."""
    panel.available = True
    previous = _cfg()
    service._display_config = previous

    def _boom():
        raise ValueError("2 validation errors for DisplayServiceConfig")

    monkeypatch.setattr(service.config_manager, "reload_config", _boom)

    service._handle_config_reload()

    assert service._display_config is previous
    assert panel.calls == []


def test_a_successful_reload_applies_and_redraws(
    panel, service: DisplayService, monkeypatch
):
    panel.available = True
    service._display_config = _cfg(i2c_address=60)
    new = _cfg(i2c_address=61)
    monkeypatch.setattr(service.config_manager, "reload_config", lambda: new)

    service._handle_config_reload()

    assert service._display_config is new
    assert panel.names == ["shutdown", "init"]
    assert service._wake.is_set()


@pytest.mark.asyncio
async def test_the_test_pattern_takes_the_lock_before_drawing(
    panel, service: DisplayService
):
    panel.available = True
    service._display_config = _cfg()

    assert await service.show_test_pattern() is True
    assert panel.calls == [("show_lines", ("Minabox", "Display OK"))]
    assert service._test_pattern_until > 0


@pytest.mark.asyncio
async def test_the_test_pattern_reports_failure_and_releases_the_lock(
    panel, service: DisplayService, monkeypatch
):
    panel.available = True
    service._display_config = _cfg()

    def _boom(lines):
        raise OSError("bus error")

    monkeypatch.setattr("display_service.main.show_lines", _boom)

    assert await service.show_test_pattern() is False
    assert service._test_pattern_until == 0.0


@pytest.mark.asyncio
async def test_no_test_pattern_without_a_panel(panel, service: DisplayService):
    panel.available = False
    service._display_config = _cfg()
    assert await service.show_test_pattern() is False


@pytest.mark.asyncio
async def test_no_test_pattern_while_disabled(panel, service: DisplayService):
    panel.available = True
    service._display_config = _cfg(enabled=False)
    assert await service.show_test_pattern() is False


# ---------------------------------------------------------------------------
# The render loop's init retry
#
# This is the one path that cannot be exercised on real hardware without
# unplugging the panel mid-run, so it is pinned here instead.
# ---------------------------------------------------------------------------


async def _run_loop_briefly(service: DisplayService, ticks: float = 0.2) -> None:
    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(ticks)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.fixture
def fast_loop(monkeypatch):
    """A render loop that ticks fast enough to observe in a test."""
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.DISPLAY_INIT_RETRY_INTERVAL", 0.0)
    # The floor between frames is longer than this whole test; frame pacing is
    # covered in test_display_volume_hud.py.
    monkeypatch.setattr("display_service.main.MIN_REDRAW_INTERVAL", 0.0)


@pytest.mark.asyncio
async def test_the_loop_reopens_a_panel_that_was_not_ready_at_startup(
    panel, service: DisplayService, fast_loop
):
    panel.available = False
    service._display_config = _cfg()

    await _run_loop_briefly(service)

    assert "init" in panel.names
    # And once it is open, the loop goes on to draw.
    assert "show_image" in panel.names


@pytest.mark.asyncio
async def test_the_loop_keeps_retrying_while_there_is_no_panel(
    panel, service: DisplayService, fast_loop
):
    panel.available = False
    panel.init_succeeds = False
    service._display_config = _cfg()

    await _run_loop_briefly(service)

    assert panel.names.count("init") > 1
    assert "show_image" not in panel.names


@pytest.mark.asyncio
async def test_the_retry_is_throttled(panel, service: DisplayService, monkeypatch):
    """Otherwise a box with no panel would hammer the I2C bus once a second."""
    monkeypatch.setattr("display_service.main.RENDER_INTERVAL", 0.01)
    monkeypatch.setattr("display_service.main.DISPLAY_INIT_RETRY_INTERVAL", 30.0)
    panel.available = False
    panel.init_succeeds = False
    service._display_config = _cfg()

    await _run_loop_briefly(service)

    assert panel.names.count("init") == 1


@pytest.mark.asyncio
async def test_a_disabled_display_is_not_reopened(
    panel, service: DisplayService, fast_loop
):
    panel.available = False
    service._display_config = _cfg(enabled=False)

    await _run_loop_briefly(service)

    assert panel.calls == []


@pytest.mark.asyncio
async def test_the_retry_does_not_log_a_warning_each_time(
    panel, service: DisplayService, fast_loop, monkeypatch
):
    """A box that simply has no panel must not fill the log for years."""
    seen: list[bool] = []

    def _init(bus, address, *, log_failure=True):
        seen.append(log_failure)
        return False

    monkeypatch.setattr("display_service.main.display_init", _init)
    service._display_config = _cfg()

    await _run_loop_briefly(service)

    assert seen and not any(seen)


@pytest.mark.asyncio
async def test_identical_content_is_only_drawn_once(
    panel, service: DisplayService, fast_loop
):
    """The frame-skip: 20 ticks of unchanged content are one frame on the bus."""
    panel.available = True
    service._display_config = _cfg()

    await _run_loop_briefly(service, ticks=0.2)

    assert panel.names.count("show_image") == 1


@pytest.mark.asyncio
async def test_a_reappearing_panel_is_redrawn_from_scratch(
    panel, service: DisplayService, fast_loop
):
    """A panel that comes back shows unknown content, so the skip must not hold.

    Nothing about the config or the state changes here -- without the
    re-appearance branch the fingerprint would still match and the panel would
    stay showing whatever it had.
    """
    panel.available = True
    panel.init_succeeds = False
    service._display_config = _cfg()

    task = asyncio.create_task(service._render_loop())
    await asyncio.sleep(0.1)
    drawn_first = panel.names.count("show_image")

    panel.available = False  # unplugged
    await asyncio.sleep(0.05)
    panel.available = True  # back again
    await asyncio.sleep(0.1)

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert drawn_first == 1
    assert panel.names.count("show_image") == 2
