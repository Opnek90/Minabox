"""The nine element renderers, and the registry that dispatches to them.

Each one is a small function with a clear contract: return the dict the layout
should draw, or None to disappear. The registry is what makes adding a type a
one-line change, so it is worth asserting that it stays in step with the schema.
"""

from __future__ import annotations

import pytest

from display_service.config_schema import DisplayElementType
from display_service.main import _ELEMENT_RENDERERS


def _call(type_: str, *, audio=None, sleep_timer=None, session=None, error=False):
    class _State:
        def has_error(self):
            return error

    return _ELEMENT_RENDERERS[type_](
        audio or {},
        sleep_timer or {},
        session or {},
        _State(),
    )


def test_the_registry_covers_every_type_the_schema_allows():
    """A type the schema accepts but the registry does not know renders nothing."""
    schema_types = set(DisplayElementType.__args__)
    assert schema_types == set(_ELEMENT_RENDERERS)


# ---------------------------------------------------------------------------
# Unconditional types
# ---------------------------------------------------------------------------


def test_volume_renders_a_percentage():
    assert _call("volume", audio={"volume": 35}) == {"type": "text", "value": "35%"}


def test_volume_without_a_value_renders_zero():
    assert _call("volume") == {"type": "text", "value": "0%"}


@pytest.mark.parametrize(
    "state,icon",
    [
        ("playing", "play"),
        ("paused", "pause"),
        ("stopped", "stop"),
        ("anything-else", "stop"),
    ],
)
def test_play_state_maps_to_an_icon(state, icon):
    assert _call("play_state", audio={"state": state}) == {
        "type": "icon",
        "value": icon,
    }


def test_play_state_without_a_value_is_stopped():
    assert _call("play_state") == {"type": "icon", "value": "stop"}


def test_clock_renders_hours_and_minutes():
    import re

    item = _call("clock")
    assert item["type"] == "text"
    assert re.fullmatch(r"\d{2}:\d{2}", item["value"])


# ---------------------------------------------------------------------------
# Conditional types
# ---------------------------------------------------------------------------


def test_mute_only_while_muted():
    assert _call("mute", audio={"muted": True}) == {"type": "icon", "value": "mute"}
    assert _call("mute", audio={"muted": False}) is None
    assert _call("mute") is None


def test_error_state_only_while_the_flag_is_set():
    assert _call("error_state", error=True) == {"type": "icon", "value": "error"}
    assert _call("error_state", error=False) is None


def test_repeat_only_for_repeat_all():
    assert _call("repeat", session={"repeat_mode": "all"}) == {
        "type": "icon",
        "value": "repeat",
    }
    assert _call("repeat", session={"repeat_mode": "one"}) is None
    assert _call("repeat", session={"repeat_mode": "none"}) is None
    assert _call("repeat") is None


def test_shuffle_only_while_on():
    assert _call("shuffle", session={"shuffle": True}) == {
        "type": "icon",
        "value": "shuffle",
    }
    assert _call("shuffle", session={"shuffle": False}) is None


def test_bluetooth_needs_a_sink_and_a_choice_of_outputs():
    both = {"bluetooth_sink_available": True, "multiple_output_devices": True}
    assert _call("bluetooth", audio=both) == {"type": "icon", "value": "bluetooth"}
    assert _call("bluetooth", audio={**both, "multiple_output_devices": False}) is None
    assert _call("bluetooth", audio={**both, "bluetooth_sink_available": False}) is None
    assert _call("bluetooth") is None


# ---------------------------------------------------------------------------
# Sleep timer: the one with arithmetic
# ---------------------------------------------------------------------------


def test_sleep_timer_is_absent_while_inactive():
    assert _call("sleep_timer", sleep_timer={"active": False}) is None
    assert _call("sleep_timer") is None


def test_sleep_timer_is_absent_without_a_remaining_value():
    assert (
        _call("sleep_timer", sleep_timer={"active": True, "remaining_ms": None}) is None
    )


@pytest.mark.parametrize(
    "remaining_ms,minutes",
    [
        (0, 0),
        (1, 1),  # a running timer must never read 0m
        (59_999, 1),
        (60_000, 1),
        (60_001, 2),  # rounds up
        (90_000, 2),
        (1_800_000, 30),
    ],
)
def test_remaining_minutes_round_up(remaining_ms, minutes):
    item = _call(
        "sleep_timer", sleep_timer={"active": True, "remaining_ms": remaining_ms}
    )
    assert item == {"type": "sleep_timer", "minutes": minutes}


def test_a_negative_remainder_does_not_render_negative_minutes():
    item = _call("sleep_timer", sleep_timer={"active": True, "remaining_ms": -5000})
    assert item["minutes"] >= 0
