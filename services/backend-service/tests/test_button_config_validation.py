"""The backend must reject exactly the button configs the button service would.

PUT /api/config/buttons only checked that "buttons" was a list. Anything past
that was written to disk, and `config/reload` went out regardless: the button
service refused the file, kept its previous config, answered on a topic nobody
subscribes to -- and the WebUI reported success. The next container start then
died on that file, over and over.

The half of these tests that matters most is the last one: a validator that is
*stricter* than the button service would lock the user out of their own
configuration, which is worse than what it replaces.
"""

from __future__ import annotations

import pytest
from backend_service.api.routes_config import _validate_buttons_config
from backend_service.core.api_errors import ApiError


def _push(**overrides) -> dict:
    button = {
        "id": "btn_1",
        "name": "Play",
        "mode": "basic",
        "type": "push",
        "gpio": 13,
        "clk": None,
        "dt": None,
        "sw": None,
        "action": "play_pause",
        "actions": None,
        "enabled": True,
    }
    button.update(overrides)
    return button


def _rotary(**overrides) -> dict:
    button = {
        "id": "btn_2",
        "name": "Volume",
        "mode": "advanced",
        "type": "rotary",
        "gpio": None,
        "clk": 24,
        "dt": 23,
        "sw": 25,
        "actions": {"rotate_cw": "volume_up", "rotate_ccw": "volume_down"},
        "enabled": True,
    }
    button.update(overrides)
    return button


VALID_BODIES = [
    pytest.param({"buttons": []}, id="empty"),
    pytest.param({"buttons": [_push()]}, id="push-basic"),
    pytest.param({"buttons": [_rotary()]}, id="rotary-advanced"),
    pytest.param({"buttons": [_push(), _rotary()]}, id="both"),
    pytest.param({"buttons": [_push(enabled=False)]}, id="disabled"),
    pytest.param(
        {"buttons": [_push(mode="advanced", action=None, actions={"short_press": "next"})]},
        id="push-advanced",
    ),
    pytest.param({"buttons": [_push(id="a"), _push(id="b", gpio=26)]}, id="two-push"),
    # Ugly but legal: the button service checks truthiness, not .strip(). The
    # backend has to agree, or this config becomes unsavable in the WebUI.
    pytest.param({"buttons": [_push(action="   ")]}, id="basic-with-blank-action"),
]

INVALID_BODIES = [
    pytest.param({"buttons": [_push(gpio=None)]}, id="push-without-gpio"),
    pytest.param({"buttons": [_push(action=None)]}, id="basic-without-action"),
    pytest.param({"buttons": [_rotary(sw=None)]}, id="rotary-without-sw"),
    pytest.param({"buttons": [_rotary(clk=None, dt=None)]}, id="rotary-without-clk-dt"),
    pytest.param(
        {"buttons": [_rotary(mode="advanced", actions=None)]}, id="advanced-without-actions"
    ),
    pytest.param({"buttons": [_push(name="")]}, id="empty-name"),
    pytest.param({"buttons": [_push(id="")]}, id="empty-id"),
    pytest.param({"buttons": [_push(type="slider")]}, id="unknown-type"),
    pytest.param({"buttons": [_push(mode="expert")]}, id="unknown-mode"),
    pytest.param({"buttons": ["not an object"]}, id="not-an-object"),
]


@pytest.mark.parametrize("body", VALID_BODIES)
def test_valid_configs_pass(body):
    _validate_buttons_config(body)


@pytest.mark.parametrize("body", INVALID_BODIES)
def test_invalid_configs_are_rejected_with_422(body):
    with pytest.raises(ApiError) as excinfo:
        _validate_buttons_config(body)
    assert excinfo.value.status_code == 422


def test_the_error_names_the_button_and_the_field():
    """The WebUI shows this string, so it has to point somewhere."""
    with pytest.raises(ApiError) as excinfo:
        _validate_buttons_config({"buttons": [_push(id="btn_7", gpio=None)]})
    detail = str(excinfo.value.detail)
    assert "btn_7" in detail
    assert "gpio" in detail


@pytest.mark.parametrize("body", VALID_BODIES + INVALID_BODIES)
def test_the_verdict_matches_the_button_service_schema(body):
    """Both ends must agree, or a legitimate config becomes unsavable.

    Skipped inside the backend image, which does not carry the button service;
    runs in the repo venv, where every service source is on the path.
    """
    schema = pytest.importorskip("button_service.config_schema")

    try:
        schema.ButtonServiceConfig.model_validate(body)
        service_accepts = True
    except Exception:
        service_accepts = False

    try:
        _validate_buttons_config(body)
        backend_accepts = True
    except ApiError:
        backend_accepts = False

    assert backend_accepts == service_accepts, (
        f"backend={'accepts' if backend_accepts else 'rejects'} but "
        f"button service={'accepts' if service_accepts else 'rejects'}"
    )
