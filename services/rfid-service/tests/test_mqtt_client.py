"""Tests for the RFID MQTT client: command handling and the last will."""

from __future__ import annotations

import json

from rfid_test_doubles import make_config

from rfid_service.infrastructure.mqtt_client import MQTTClient


def _client(received: list[str] | None = None) -> MQTTClient:
    sink = received if received is not None else []
    return MQTTClient(make_config(), on_set_mode_callback=sink.append)


def test_subscribes_to_command_and_general_config() -> None:
    client = _client()

    assert set(client._subscriptions) == {
        "minabox/testbox/rfid/cmd/set-mode",
        "minabox/testbox/config/general",
    }


def test_valid_mode_reaches_the_callback() -> None:
    received: list[str] = []
    client = _client(received)

    client._handle_set_mode(json.dumps({"mode": "learning"}).encode())

    assert received == ["learning"]


def test_unknown_mode_is_ignored() -> None:
    received: list[str] = []
    client = _client(received)

    client._handle_set_mode(json.dumps({"mode": "party"}).encode())

    assert received == []


def test_malformed_payloads_are_ignored() -> None:
    received: list[str] = []
    client = _client(received)

    client._handle_set_mode(b"not json")
    client._handle_set_mode(b"[]")
    client._handle_set_mode(b"\xff\xfe")

    assert received == []


def test_last_will_clears_the_retained_presence() -> None:
    """A crashed service must not leave subscribers believing a tag is present."""
    client = _client()
    will = client._will

    assert will is not None
    assert will.topic == "minabox/testbox/rfid/presence"
    assert will.retain is True
    assert json.loads(will.payload)["tag_present"] is False
