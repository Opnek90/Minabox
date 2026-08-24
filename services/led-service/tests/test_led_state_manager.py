"""Tests for deriving logical states from MQTT messages."""

from __future__ import annotations

import json

import pytest
from led_test_doubles import DEVICE_ID

from led_service.core import StateManager
from led_service.exceptions import StateError

PREFIX = f"minabox/{DEVICE_ID}"


@pytest.fixture
def states() -> StateManager:
    return StateManager(DEVICE_ID)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        (f"{PREFIX}/rfid/tag-scanned", "rfid_scanned"),
        (f"{PREFIX}/rfid/tag-removed", "rfid_removed"),
        (f"{PREFIX}/rfid/unknown-tag", "rfid_unknown_tag"),
        (f"{PREFIX}/rfid/tag-blocked", "rfid_tag_blocked"),
        (f"{PREFIX}/system/service-started", "system_online"),
        (f"{PREFIX}/system/service-error", "system_error"),
        (f"{PREFIX}/system/booting", "system_booting"),
        (f"{PREFIX}/button/raw-event", "button_pressed"),
        (f"{PREFIX}/backend/unreachable", "backend_unreachable"),
        (f"{PREFIX}/led/usage-denied", "usage_denied"),
    ],
)
def test_topics_map_to_their_logical_state(
    states: StateManager, topic: str, expected: str
) -> None:
    assert states.derive_state(topic, b"{}") == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("playing", "audio_playing"),
        ("paused", "audio_paused"),
        ("stopped", "audio_stopped"),
    ],
)
def test_audio_status_maps_its_state_field(
    states: StateManager, state: str, expected: str
) -> None:
    payload = json.dumps({"state": state}).encode()

    assert states.derive_state(f"{PREFIX}/audio/status", payload) == expected


def test_an_unknown_audio_state_falls_back_to_stopped(states: StateManager) -> None:
    """Better a dark LED than one stuck showing playback that ended."""
    payload = json.dumps({"state": "buffering"}).encode()

    assert states.derive_state(f"{PREFIX}/audio/status", payload) == "audio_stopped"


@pytest.mark.parametrize(
    ("present", "expected"),
    [(True, "rfid_scanned"), (False, "rfid_removed")],
)
def test_retained_presence_recovers_the_tag_state(
    states: StateManager, present: bool, expected: str
) -> None:
    """This is how a state-dependent LED recovers after a config reload."""
    payload = json.dumps({"tag_present": present}).encode()

    assert states.derive_state(f"{PREFIX}/rfid/presence", payload) == expected


def test_a_topic_of_another_device_is_ignored(states: StateManager) -> None:
    assert states.derive_state("minabox/other-box/rfid/tag-scanned", b"{}") is None


def test_a_topic_without_a_rule_is_ignored(states: StateManager) -> None:
    assert states.derive_state(f"{PREFIX}/audio/volume", b"{}") is None


@pytest.mark.parametrize("topic", [f"{PREFIX}/audio/status", f"{PREFIX}/rfid/presence"])
def test_a_malformed_payload_raises_instead_of_guessing(
    states: StateManager, topic: str
) -> None:
    with pytest.raises(StateError):
        states.derive_state(topic, b"not json")
