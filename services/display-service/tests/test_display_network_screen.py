"""The screen for "you cannot reach this box the usual way".

Two states earn it - the fallback hotspot is up, or there is no network - and
nothing else. "Local network only" is a corner mark, not a screen, and a box
that is plainly online must never show an address it does not need to.
"""

from __future__ import annotations

from display_service.config_schema import DisplayServiceConfig
from display_service.core.state_manager import StateManager
from display_service.main import (
    SCREEN_IDLE,
    SCREEN_NETWORK,
    SCREEN_PLAYING,
    DisplayService,
)
from display_service.render.network import (
    render_hotspot,
    render_no_network,
    wander_offset,
)
from display_service.render.primitives import HEIGHT, WIDTH

HOTSPOT = {"active": True, "ssid": "Minabox-Setup", "password": "abcd1234"}


def _lit(img) -> int:
    px = img.load()
    return sum(1 for x in range(WIDTH) for y in range(HEIGHT) if px[x, y])


def _region_has_ink(img, y0: int, y1: int) -> bool:
    px = img.load()
    return any(px[x, y] for x in range(WIDTH) for y in range(y0, y1))


# ── State ────────────────────────────────────────────────────────────────


def test_only_hotspot_and_no_network_want_the_screen():
    sm = StateManager("box1")
    assert sm.wants_network_screen() is False  # "unknown" at startup

    for mode, wanted in (
        ("online", False),
        ("local_only", False),
        ("hotspot", True),
        ("no_network", True),
    ):
        sm.update_network({"mode": mode, "hotspot": {}})
        assert sm.wants_network_screen() is wanted, mode


def test_update_network_keeps_only_what_the_screen_draws():
    sm = StateManager("box1")
    sm.update_network(
        {
            "mode": "hotspot",
            "ssid": None,
            "manage_url": "http://10.42.0.1",
            "hotspot": HOTSPOT,
            "internet": False,
            "interface": "wlan0",
        }
    )
    assert sm.get_network() == {
        "mode": "hotspot",
        "ssid": None,
        "manage_url": "http://10.42.0.1",
        "hotspot": HOTSPOT,
    }


def test_a_failed_poll_does_not_leave_a_stale_hotspot_screen():
    # The backend answers with the "unknown" fallback when the host-helper is
    # down; that has to take the screen away, not freeze it.
    sm = StateManager("box1")
    sm.update_network({"mode": "hotspot", "hotspot": {"active": True}})
    assert sm.wants_network_screen() is True
    sm.update_network({"mode": "unknown", "hotspot": {}})
    assert sm.wants_network_screen() is False


# ── Priority ─────────────────────────────────────────────────────────────


def _configured(service: DisplayService) -> DisplayService:
    service._display_config = DisplayServiceConfig(enabled=True)
    return service


def test_network_screen_beats_idle(service: DisplayService):
    _configured(service)
    service.state_manager.update_network({"mode": "hotspot", "hotspot": HOTSPOT})
    assert service._current_screen(now=100.0) == SCREEN_NETWORK


def test_playing_beats_the_network_screen(service: DisplayService):
    _configured(service)
    service.state_manager.update_network({"mode": "no_network", "hotspot": {}})
    service.state_manager._audio["state"] = "playing"
    assert service._current_screen(now=100.0) == SCREEN_PLAYING


def test_an_online_box_shows_the_idle_screen(service: DisplayService):
    _configured(service)
    service.state_manager.update_network({"mode": "online", "hotspot": {}})
    assert service._current_screen(now=100.0) == SCREEN_IDLE


def test_the_screen_frame_carries_the_credentials_into_the_fingerprint(
    service: DisplayService,
):
    _configured(service)
    service.state_manager.update_network(
        {
            "mode": "hotspot",
            "manage_url": "http://10.42.0.1",
            "hotspot": HOTSPOT,
        }
    )
    fingerprint, image = service._screen_frame(SCREEN_NETWORK, now=0.0)
    assert "Minabox-Setup" in fingerprint
    assert "abcd1234" in fingerprint
    assert "10.42.0.1" in fingerprint
    assert image.size == (WIDTH, HEIGHT)


# ── Render ───────────────────────────────────────────────────────────────


def test_hotspot_frame_puts_something_on_every_band():
    img = render_hotspot("Minabox-Setup", "abcd1234", "http://10.42.0.1")
    assert _region_has_ink(img, 0, 20)   # title / ssid
    assert _region_has_ink(img, 20, 45)  # code
    assert _region_has_ink(img, 45, HEIGHT)  # url


def test_a_long_ssid_still_fits_the_panel_width():
    img = render_hotspot("A-Really-Quite-Long-Network-Name", "abcd1234", None)
    px = img.load()
    # Nothing lit in the last column: it was clipped to fit, not drawn off-edge.
    assert not any(px[WIDTH - 1, y] for y in range(HEIGHT))


def test_no_network_frame_is_not_blank_and_stays_in_bounds():
    img = render_no_network()
    assert _lit(img) > 20
    assert img.size == (WIDTH, HEIGHT)


def test_the_block_wanders_to_spread_oled_wear():
    assert wander_offset(0.0) != wander_offset(90.0)
