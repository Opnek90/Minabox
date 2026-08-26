"""The backend must reject exactly the display configs the display service would.

PUT /api/config/display only checked that "elements" was a list. Anything past
that was written to disk and `config/reload` went out regardless: the running
display service caught the ValidationError and kept its previous config, so the
box looked fine -- and the next container start died on that file and went into
a restart loop. The person who changed the setting and the person who found the
broken box were separated by a reboot.

There is much less to check now. The layout - elements, areas, order, font -
stopped reaching the panel when every state of the box got a screen of its own,
and the display service ignores those keys entirely. So they must be *accepted*
here: a box running today still has them in its file, and rejecting them would
lock it out of changing anything else.

The half that matters most is still the last group. A validator stricter than
the display service locks the user out of their own configuration, which is
worse than what it replaces, so every body under VALID_BODIES is run through the
real schema as well.
"""

from __future__ import annotations

import pytest

from backend_service.api.routes_config import _validate_display_config
from backend_service.core.api_errors import ApiError


def _body(**overrides) -> dict:
    body = {"enabled": True, "i2c_bus": 1, "i2c_address": 60}
    body.update(overrides)
    return body


VALID_BODIES = {
    "the whole thing": _body(),
    "empty": {},
    "off": _body(enabled=False),
    "another bus": _body(i2c_bus=3),
    "address zero": _body(i2c_address=0),
    "a high address": _body(i2c_address=127),
    # Everything below is a file a running box still has.
    "with the old element list": _body(
        elements=[
            {"id": "vol", "type": "volume", "area": 1, "order": 0, "enabled": True},
            {"id": "time", "type": "clock", "area": 0, "order": 0, "enabled": True},
        ]
    ),
    "with the old font keys": _body(font="terminus", font_size="large"),
    "with an element type that never existed": _body(
        elements=[{"id": "x", "type": "was_auch_immer", "area": 9}]
    ),
    "with a font that never existed": _body(font="comic-sans"),
    "with elements that are not even a list": _body(elements="nope"),
    # Pydantic reads these as 1 and 60. Odd to write, harmless to load, and
    # refusing them here would be stricter than the service - see _as_int.
    "bus as a numeric string": _body(i2c_bus="1"),
    "address as a numeric string": _body(i2c_address="60"),
    "bus as a boolean": _body(i2c_bus=True),
    "address as a boolean": _body(i2c_address=False),
    # Brightness and the night window.
    "with brightness": _body(
        brightness={
            "day": 255,
            "night": 40,
            "night_from": "20:00",
            "night_to": "07:00",
            "off_at_night": True,
        }
    ),
    "brightness, partly given": _body(brightness={"night": 10}),
    "brightness, empty": _body(brightness={}),
    "a night window inside one day": _body(
        brightness={"night_from": "13:00", "night_to": "15:00"}
    ),
    "contrast at the edges": _body(brightness={"day": 0, "night": 255}),
    "midnight": _body(brightness={"night_from": "00:00", "night_to": "23:59"}),
}

INVALID_BODIES = {
    "bus zero": _body(i2c_bus=0),
    "negative bus": _body(i2c_bus=-1),
    "bus as a word": _body(i2c_bus="drei"),
    "negative address": _body(i2c_address=-1),
    "address as a word": _body(i2c_address="sechzig"),
    "enabled as text": _body(enabled="ja"),
    "brightness that is not an object": _body(brightness="hell"),
    "contrast above 255": _body(brightness={"day": 256}),
    "contrast below zero": _body(brightness={"night": -1}),
    "an hour that does not exist": _body(brightness={"night_from": "24:00"}),
    "a minute that does not exist": _body(brightness={"night_to": "07:60"}),
    "a time in words": _body(brightness={"night_from": "abends"}),
    "a time without a colon": _body(brightness={"night_to": "0700"}),
    "off_at_night as text": _body(brightness={"off_at_night": "nachts"}),
}


@pytest.mark.parametrize("name", sorted(VALID_BODIES))
def test_a_config_the_display_service_accepts_passes(name):
    _validate_display_config(VALID_BODIES[name])


@pytest.mark.parametrize("name", sorted(INVALID_BODIES))
def test_a_config_the_display_service_would_refuse_is_rejected(name):
    with pytest.raises(ApiError) as excinfo:
        _validate_display_config(INVALID_BODIES[name])
    assert excinfo.value.status_code == 422


def test_the_message_names_what_is_wrong():
    with pytest.raises(ApiError) as excinfo:
        _validate_display_config(_body(i2c_bus=0, i2c_address=-1))
    detail = excinfo.value.detail
    assert "i2c_bus" in detail
    assert "i2c_address" in detail


# ---------------------------------------------------------------------------
# Both ends, held together
# ---------------------------------------------------------------------------


def _display_schema():
    """The real schema from the display service, or a skip if it is not on the path."""
    try:
        from display_service.config_schema import DisplayServiceConfig
    except ImportError:  # pragma: no cover - display service not installed
        pytest.skip("display service package not importable")
    return DisplayServiceConfig


@pytest.mark.parametrize("name", sorted(VALID_BODIES))
def test_everything_this_accepts_the_display_service_also_accepts(name):
    """A validator stricter than the service locks the user out of their box."""
    _display_schema()(**VALID_BODIES[name])


@pytest.mark.parametrize("name", sorted(INVALID_BODIES))
def test_everything_this_rejects_the_display_service_also_rejects(name):
    """And one that is laxer lets a file through that kills the next start."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _display_schema()(**INVALID_BODIES[name])


# ---------------------------------------------------------------------------
# What the settings page actually sends
# ---------------------------------------------------------------------------


def test_the_body_the_settings_page_sends_is_accepted():
    """The panel sends three keys and nothing else.

    A second, older shape check demanded that "elements" be a list, and it
    survived the removal of the grid. So the endpoint answered the new panel
    with 422 - the settings page could not save anything at all, while every
    unit test here passed, because this file only ever called the display
    validator and never the shape check in front of it.
    """
    _validate_display_config({"enabled": True, "i2c_bus": 1, "i2c_address": 60})


def test_the_endpoint_no_longer_demands_an_element_list():
    from backend_service.api.routes_config import _CONFIG_SHAPE

    assert "display" not in _CONFIG_SHAPE
