"""The backend must reject exactly the display configs the display service would.

PUT /api/config/display only checked that "elements" was a list. Anything past
that was written to disk and `config/reload` went out regardless: the running
display service caught the ValidationError and kept its previous config, so the
box looked fine -- and the next container start died on that file and went into
a restart loop. The person who changed the setting and the person who found the
broken box were separated by a reboot.

The half of these tests that matters most is the last group: a validator that is
*stricter* than the display service would lock the user out of their own
configuration, which is worse than what it replaces. Every body under
VALID_BODIES is one the display schema accepts, so it must pass here too.
"""

from __future__ import annotations

import pytest

from backend_service.api.routes_config import _validate_display_config
from backend_service.core.api_errors import ApiError


def _element(**overrides) -> dict:
    element = {
        "id": "vol",
        "type": "volume",
        "enabled": True,
        "order": 0,
        "area": 1,
    }
    element.update(overrides)
    return element


def _body(*elements, **overrides) -> dict:
    body = {
        "enabled": True,
        "i2c_bus": 1,
        "i2c_address": 60,
        "font_size": "large",
        "font": "sans",
        "elements": list(elements),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Bodies the display service loads happily -- these must not be rejected
# ---------------------------------------------------------------------------

VALID_BODIES = [
    pytest.param(_body(), id="no-elements"),
    pytest.param(_body(_element()), id="single-element"),
    pytest.param(
        _body(*[_element(id=t, type=t, area=0) for t in ("clock", "error_state")]),
        id="header-elements",
    ),
    # Every type the schema knows, so a new type added to one side and not the
    # other shows up as a failure here.
    pytest.param(
        _body(
            *[
                _element(id=t, type=t)
                for t in (
                    "volume",
                    "sleep_timer",
                    "mute",
                    "play_state",
                    "clock",
                    "error_state",
                    "repeat",
                    "shuffle",
                    "bluetooth",
                )
            ]
        ),
        id="all-types",
    ),
    pytest.param(_body(font_size="small"), id="font-size-small"),
    pytest.param(_body(font_size="medium"), id="font-size-medium"),
    pytest.param(_body(font="default"), id="font-default"),
    pytest.param(_body(font="terminus"), id="font-terminus"),
    pytest.param(_body(_element(area=0)), id="area-header"),
    pytest.param(_body(_element(area=2)), id="area-right"),
    pytest.param(_body(_element(order=99)), id="high-order"),
    # Defaults exist for everything except id and type, so a minimal element is
    # legal and must stay legal.
    pytest.param({"elements": [{"id": "x", "type": "clock"}]}, id="minimal-element"),
    pytest.param({"elements": []}, id="elements-only"),
    # A blank-but-not-empty id passes min_length=1 in the schema.
    pytest.param({"elements": [{"id": " ", "type": "clock"}]}, id="blank-id"),
]


@pytest.mark.parametrize("body", VALID_BODIES)
def test_valid_bodies_are_accepted(body):
    _validate_display_config(body)


# ---------------------------------------------------------------------------
# Bodies the display service refuses -- writing these caused the restart loop
# ---------------------------------------------------------------------------

INVALID_BODIES = [
    pytest.param(_body(_element(type="gibt_es_nicht")), "type", id="unknown-type"),
    pytest.param(_body(_element(type=None)), "type", id="type-missing"),
    pytest.param(_body(_element(area=9)), "area", id="area-out-of-range"),
    pytest.param(_body(_element(area=-1)), "area", id="area-negative"),
    pytest.param(_body(_element(id="")), "id", id="empty-id"),
    pytest.param(_body(_element(id=None)), "id", id="id-missing"),
    pytest.param(_body(_element(id=42)), "id", id="id-not-a-string"),
    pytest.param(_body(_element(order=-1)), "order", id="negative-order"),
    pytest.param(_body(_element(order="first")), "order", id="order-not-an-int"),
    pytest.param(_body("not-an-object"), "must be an object", id="element-not-a-dict"),
    pytest.param(_body(font_size="huge"), "font_size", id="unknown-font-size"),
    pytest.param(_body(font="comic-sans"), "font", id="unknown-font"),
    pytest.param(_body(i2c_bus=0), "i2c_bus", id="bus-zero"),
    pytest.param(_body(i2c_bus=-1), "i2c_bus", id="bus-negative"),
    pytest.param(_body(i2c_address=-1), "i2c_address", id="address-negative"),
]


@pytest.mark.parametrize("body,expected", INVALID_BODIES)
def test_invalid_bodies_are_rejected(body, expected):
    with pytest.raises(ApiError) as excinfo:
        _validate_display_config(body)
    assert excinfo.value.status_code == 422
    assert expected in str(excinfo.value.detail)


def test_the_config_that_caused_the_restart_loop():
    """The exact body from the go-live review, reproduced end to end."""
    body = {
        "enabled": True,
        "i2c_bus": 1,
        "i2c_address": 60,
        "font_size": "large",
        "font": "sans",
        "elements": [
            {"id": "time", "type": "clock", "enabled": True, "order": 0, "area": 0},
            {
                "id": "kaputt",
                "type": "gibt_es_nicht",
                "enabled": True,
                "order": 0,
                "area": 9,
            },
        ],
    }
    with pytest.raises(ApiError) as excinfo:
        _validate_display_config(body)
    detail = str(excinfo.value.detail)
    # Both faults reported at once, so the user does not fix them one per save.
    assert "type" in detail
    assert "area" in detail


def test_every_error_is_reported_not_just_the_first():
    body = _body(_element(id="", type="nope", area=7, order=-2))
    with pytest.raises(ApiError) as excinfo:
        _validate_display_config(body)
    detail = str(excinfo.value.detail)
    assert detail.count(";") >= 3


def test_element_types_match_the_endpoint_that_advertises_them():
    """The admin UI offers _DISPLAY_ELEMENT_TYPES; the validator must accept all."""
    from backend_service.api.routes_config import _DISPLAY_ELEMENT_TYPES

    body = _body(*[_element(id=t, type=t) for t in _DISPLAY_ELEMENT_TYPES])
    _validate_display_config(body)


# ---------------------------------------------------------------------------
# The two ends, held together
#
# These are the tests that keep the copy honest. The rules above are a
# transcription of display_service/config_schema.py, and a transcription drifts.
# Here both are run against the same bodies: whatever the schema accepts the
# validator must accept, and whatever the schema refuses the validator must
# refuse -- otherwise the copy has gone stale and this fails instead of a box
# going into a restart loop months later.
# ---------------------------------------------------------------------------


def _display_schema():
    display_service = pytest.importorskip(
        "display_service.config_schema",
        reason="display service source not on the path",
    )
    return display_service.DisplayServiceConfig


@pytest.mark.parametrize("body", VALID_BODIES)
def test_valid_bodies_really_load_in_the_display_service(body):
    _display_schema().model_validate(body)


@pytest.mark.parametrize("body,expected", INVALID_BODIES)
def test_invalid_bodies_really_fail_in_the_display_service(body, expected):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _display_schema().model_validate(body)


def test_the_two_type_lists_are_the_same():
    from backend_service.api.routes_config import _DISPLAY_ELEMENT_TYPES

    schema = _display_schema()
    field = schema.model_fields["elements"]
    element_model = field.annotation.__args__[0]
    schema_types = set(element_model.model_fields["type"].annotation.__args__)
    assert schema_types == set(_DISPLAY_ELEMENT_TYPES)
