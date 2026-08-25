"""_build_areas turns config plus state into the three lists the renderer draws.

It is the piece with the most branches in the service and had no tests at all:
ordering, the enabled flag, conditional elements that return None, the per-area
cap, and an unknown type that must warn rather than raise.
"""

from __future__ import annotations

import re

import pytest
from display_test_doubles import element

from display_service.main import _HEADER_MAX_ITEMS, DisplayService


def _types(items: list[dict]) -> list:
    """The value that identifies each rendered item, for readable assertions."""
    return [i.get("value", i.get("type")) for i in items]


# ---------------------------------------------------------------------------
# Areas and ordering
# ---------------------------------------------------------------------------


def test_no_config_gives_three_empty_areas(service: DisplayService):
    assert service._build_areas() == [[], [], []]


def test_disabled_display_renders_nothing(service, configure):
    configure(element("clock"), enabled=False)
    assert service._build_areas() == [[], [], []]


def test_elements_land_in_their_configured_area(service, configure):
    configure(
        element("clock", area=0),
        element("volume", area=1),
        element("play_state", area=2),
    )
    header, left, right = service._build_areas()
    assert len(header) == 1
    assert re.fullmatch(r"\d{2}:\d{2}", header[0]["value"])
    assert _types(left) == ["0%"]
    assert _types(right) == ["stop"]


def test_order_decides_position_within_an_area(service, configure):
    configure(
        element("play_state", area=1, order=2),
        element("volume", area=1, order=1),
    )
    _, left, _ = service._build_areas()
    assert _types(left) == ["0%", "stop"]


def test_order_is_independent_per_area(service, configure):
    configure(
        element("volume", area=1, order=5),
        element("play_state", area=2, order=0),
    )
    _, left, right = service._build_areas()
    assert _types(left) == ["0%"]
    assert _types(right) == ["stop"]


def test_disabled_elements_are_skipped(service, configure):
    configure(
        element("volume", area=1),
        element("play_state", area=1, enabled=False),
    )
    _, left, _ = service._build_areas()
    assert _types(left) == ["0%"]


def test_no_enabled_elements_gives_empty_areas(service, configure):
    configure(element("volume", area=1, enabled=False))
    assert service._build_areas() == [[], [], []]


# ---------------------------------------------------------------------------
# Conditional element types
# ---------------------------------------------------------------------------


def test_conditional_elements_are_absent_when_they_have_nothing_to_say(
    service, configure
):
    configure(
        element("mute", area=1),
        element("sleep_timer", area=1),
        element("error_state", area=1),
        element("repeat", area=1),
        element("shuffle", area=1),
        element("bluetooth", area=1),
    )
    assert service._build_areas() == [[], [], []]


def test_mute_appears_once_muted(service, configure):
    configure(element("mute", area=1))
    service.state_manager.update_audio(
        "minabox/box1/audio/status", b'{"muted": true, "volume": 5}'
    )
    _, left, _ = service._build_areas()
    assert _types(left) == ["mute"]


def test_error_state_appears_once_an_error_was_reported(service, configure):
    configure(element("error_state", area=0))
    service.state_manager.set_error()
    header, _, _ = service._build_areas()
    assert _types(header) == ["error"]


def test_sleep_timer_appears_while_the_timer_runs(service, configure):
    configure(element("sleep_timer", area=1))
    service.state_manager.update_sleep_timer(True, 90_000)
    _, left, _ = service._build_areas()
    assert left == [{"type": "sleep_timer", "minutes": 2}]


def test_repeat_and_shuffle_follow_the_session(service, configure):
    configure(element("repeat", area=2), element("shuffle", area=2, order=1))
    service.state_manager.update_session("all", True)
    _, _, right = service._build_areas()
    assert _types(right) == ["repeat", "shuffle"]


# ---------------------------------------------------------------------------
# The per-area caps
# ---------------------------------------------------------------------------


def test_header_drops_what_exceeds_its_limit(service, configure):
    # Seven always-visible elements in a header that holds six.
    configure(*[element("volume", area=0, order=i, id_=f"v{i}") for i in range(7)])
    header, _, _ = service._build_areas()
    assert len(header) == _HEADER_MAX_ITEMS


def test_a_column_drops_what_exceeds_its_limit(service, configure):
    configure(*[element("volume", area=1, order=i, id_=f"v{i}") for i in range(5)])
    _, left, _ = service._build_areas()
    assert len(left) == 3


def test_the_cap_counts_rendered_items_not_configured_ones(service, configure):
    """Three conditionals that stay silent must not use up the column."""
    configure(
        element("mute", area=1, order=0),
        element("repeat", area=1, order=1),
        element("shuffle", area=1, order=2),
        element("volume", area=1, order=3),
    )
    _, left, _ = service._build_areas()
    assert _types(left) == ["0%"]


# ---------------------------------------------------------------------------
# Bad configuration
# ---------------------------------------------------------------------------


def test_an_unknown_type_is_skipped_rather_than_raising(service, configure):
    cfg = configure(element("volume", area=1))
    # Past the schema, as a hand-edited file or an older service would see it.
    object.__setattr__(cfg.elements[0], "type", "gibt_es_nicht")
    assert service._build_areas() == [[], [], []]


def test_one_unknown_type_does_not_hide_the_others(service, configure):
    cfg = configure(
        element("volume", area=1, order=0),
        element("play_state", area=1, order=1),
    )
    object.__setattr__(cfg.elements[0], "type", "gibt_es_nicht")
    _, left, _ = service._build_areas()
    assert _types(left) == ["stop"]


@pytest.mark.parametrize("area", [0, 1, 2])
def test_every_area_is_always_present_in_the_result(service, configure, area):
    configure(element("volume", area=area))
    areas = service._build_areas()
    assert len(areas) == 3
    assert all(isinstance(a, list) for a in areas)
