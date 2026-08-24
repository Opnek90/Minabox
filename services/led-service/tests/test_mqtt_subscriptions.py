"""The subscription list must cover every state the service can derive.

`rfid/tag-blocked` had a derivation rule and a slot in the WebUI, but no
subscription -- so binding an LED to a blocked card did nothing at all, without
a single log line. This test keeps the two lists from drifting apart again.
"""

from __future__ import annotations

import pytest
from led_test_doubles import DEVICE_ID, make_config

from led_service.core import StateManager
from led_service.infrastructure import MQTTClient


@pytest.fixture
def client() -> MQTTClient:
    return MQTTClient(
        config=make_config(),
        on_message_callback=lambda topic, payload: None,
        on_config_update_callback=lambda config: None,
        on_config_reload_callback=lambda: None,
    )


def test_every_derived_topic_is_subscribed(client: MQTTClient) -> None:
    derived = set(StateManager(DEVICE_ID)._build_derivation_rules())
    subscribed = set(client._build_subscription_topics())

    assert derived - subscribed == set()


def test_a_blocked_tag_reaches_the_service(client: MQTTClient) -> None:
    assert (
        f"minabox/{DEVICE_ID}/rfid/tag-blocked" in client._build_subscription_topics()
    )


def test_the_config_api_is_subscribed(client: MQTTClient) -> None:
    prefix = f"minabox/{DEVICE_ID}"
    subscribed = set(client._build_subscription_topics())

    assert {
        f"{prefix}/led/config/update",
        f"{prefix}/led/config/reload",
        f"{prefix}/led/config/get",
        f"{prefix}/config/general",
    } <= subscribed


def test_subscriptions_are_registered_before_the_first_connect(
    client: MQTTClient,
) -> None:
    """The base client replays them on every connect, including the first."""
    assert set(client._subscriptions) == set(client._build_subscription_topics())
