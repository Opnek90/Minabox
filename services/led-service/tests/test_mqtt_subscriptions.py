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
    async def on_message(topic: str, payload: bytes) -> None:
        return None

    async def on_reload() -> None:
        return None

    return MQTTClient(
        config=make_config(),
        on_message_callback=on_message,
        on_config_reload_callback=on_reload,
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
        f"{prefix}/led/config/reload",
        f"{prefix}/config/general",
    } <= subscribed


def test_the_dead_config_topics_are_gone(client: MQTTClient) -> None:
    """Nothing ever published them, and config is mounted read-only anyway."""
    prefix = f"minabox/{DEVICE_ID}"
    subscribed = set(client._build_subscription_topics())

    assert f"{prefix}/led/config/update" not in subscribed
    assert f"{prefix}/led/config/get" not in subscribed


def test_subscriptions_are_registered_before_the_first_connect(
    client: MQTTClient,
) -> None:
    """The base client replays them on every connect, including the first."""
    assert set(client._subscriptions) == set(client._build_subscription_topics())
