"""Tests for the shared resilient MQTT client.

These pin down the behaviour that the 2026-08-18 diagnostic package showed was
missing: a broker that disappears must not take the service down, and a service
that reconnects must not come back mute.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aiomqtt import MqttError

from shared_lib.mqtt.base_client import BaseMQTTClient

_DROP = object()


class FakeMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = SimpleNamespace(value=topic)
        self.payload = payload


class FakeBroker:
    """A broker we can take away and bring back at will."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.connect_attempts = 0
        self.subscriptions: list[tuple[str, int]] = []
        self.published: list[tuple[str, object, int, bool]] = []
        self.queue: asyncio.Queue = asyncio.Queue()
        # Error the next connect attempt fails with.
        self.connect_error = "[Errno 111] Connection refused"

    def go_down(self, error: str = "[Errno -2] Name or service not known") -> None:
        """Broker vanishes mid message iteration, as a restarting container would."""
        self.available = False
        self.connect_error = error
        self.queue.put_nowait(_DROP)

    def come_back(self) -> None:
        self.available = True

    def deliver(self, topic: str, payload: bytes) -> None:
        self.queue.put_nowait(FakeMessage(topic, payload))

    def subscribed_topics(self) -> set[str]:
        return {t for t, _ in self.subscriptions}


class FakeClient:
    def __init__(self, broker: FakeBroker) -> None:
        self._broker = broker

    async def __aenter__(self) -> "FakeClient":
        self._broker.connect_attempts += 1
        if not self._broker.available:
            raise MqttError(self._broker.connect_error)
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def _require_up(self) -> None:
        if not self._broker.available:
            raise MqttError("Disconnected")

    async def subscribe(self, topic: str, qos: int = 1) -> None:
        self._require_up()
        self._broker.subscriptions.append((topic, qos))

    async def unsubscribe(self, topic: str) -> None:
        self._require_up()

    async def publish(self, topic: str, payload: object, qos: int = 1, retain: bool = False) -> None:
        self._require_up()
        self._broker.published.append((topic, payload, qos, retain))

    @property
    async def messages(self):
        while True:
            item = await self._broker.queue.get()
            if item is _DROP:
                raise MqttError("Disconnected during message iteration")
            yield item


class RecordingClient(BaseMQTTClient):
    def __init__(self, broker: FakeBroker, **kwargs: object) -> None:
        super().__init__(
            "test-broker",
            1883,
            service_name="test",
            client_factory=lambda: FakeClient(broker),
            initial_backoff=0.01,
            max_backoff=0.05,
            jitter=0.0,
            **kwargs,
        )
        self.received: list[tuple[str, bytes]] = []
        self.connect_events = 0

    async def on_message(self, topic: str, payload: bytes) -> None:
        self.received.append((topic, payload))

    async def on_connected(self) -> None:
        self.connect_events += 1


async def wait_for(predicate, timeout: float = 3.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


# ---------------------------------------------------------------------------
# The regression from the diagnostic package
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_loss_mid_iteration_does_not_kill_the_task():
    """Broker drops during `async for message in client.messages`.

    Before the fix this raised MqttError out of the message loop and, via the
    startup path, terminated the process with `service_crashed`.
    """
    broker = FakeBroker()
    client = RecordingClient(broker)
    await client.subscribe("minabox/box1/audio/play")
    task = await client.start()

    assert await wait_for(lambda: client.is_connected)
    broker.deliver("minabox/box1/audio/play", b"{}")
    assert await wait_for(lambda: len(client.received) == 1)

    broker.go_down()

    # The loop task must still be alive, and health must report the outage.
    assert await wait_for(lambda: not client.is_connected)
    assert not task.done(), "message loop task died on broker loss"
    assert client.is_running

    broker.come_back()
    assert await wait_for(lambda: client.is_connected)
    assert not task.done()

    # And it must be able to receive again after the reconnect.
    broker.deliver("minabox/box1/audio/play", b"{}")
    assert await wait_for(lambda: len(client.received) == 2)

    await client.stop()


@pytest.mark.asyncio
async def test_health_reports_mqtt_disconnected_during_outage():
    broker = FakeBroker()
    client = RecordingClient(broker)
    await client.start()
    assert await wait_for(lambda: client.is_connected)

    broker.go_down()
    assert await wait_for(lambda: client.is_connected is False)
    # is_running stays True: the service is alive and retrying, just not connected.
    assert client.is_running is True

    broker.come_back()
    assert await wait_for(lambda: client.is_connected is True)
    await client.stop()


@pytest.mark.asyncio
async def test_subscriptions_are_replayed_after_reconnect():
    broker = FakeBroker()
    client = RecordingClient(broker)
    for topic in ("minabox/box1/audio/play", "minabox/box1/config/general"):
        await client.subscribe(topic)

    await client.start()
    assert await wait_for(lambda: client.is_connected)
    assert broker.subscribed_topics() == {
        "minabox/box1/audio/play",
        "minabox/box1/config/general",
    }

    broker.subscriptions.clear()  # broker restarted: it forgot everything
    broker.go_down()
    assert await wait_for(lambda: not client.is_connected)
    broker.come_back()

    assert await wait_for(
        lambda: broker.subscribed_topics()
        == {"minabox/box1/audio/play", "minabox/box1/config/general"}
    ), "service reconnected but did not re-subscribe"
    await client.stop()


@pytest.mark.asyncio
async def test_last_status_is_republished_after_reconnect():
    """A reconnected service must not be silently mute."""
    broker = FakeBroker()
    client = RecordingClient(broker)
    await client.start()
    assert await wait_for(lambda: client.is_connected)

    status_topic = "minabox/box1/audio/status"
    await client.publish(status_topic, {"state": "playing"}, retain=True, remember=True)
    assert await wait_for(lambda: any(t == status_topic for t, *_ in broker.published))

    broker.published.clear()
    broker.go_down()
    assert await wait_for(lambda: not client.is_connected)
    broker.come_back()

    assert await wait_for(
        lambda: any(t == status_topic for t, *_ in broker.published)
    ), "last reported status was not republished after reconnect"
    await client.stop()


@pytest.mark.asyncio
async def test_dns_failure_is_an_ordinary_retry_not_a_crash():
    """[Errno -2] just means the broker container is not back yet."""
    broker = FakeBroker(available=False)
    broker.connect_error = "[Errno -2] Name or service not known"
    client = RecordingClient(broker)
    await client.subscribe("minabox/box1/led/set")
    task = await client.start()

    # Several failed attempts, and the service is still up.
    assert await wait_for(lambda: broker.connect_attempts >= 3)
    assert not task.done()
    assert client.is_connected is False

    broker.come_back()
    assert await wait_for(lambda: client.is_connected)
    assert "minabox/box1/led/set" in broker.subscribed_topics()
    await client.stop()


@pytest.mark.asyncio
async def test_startup_does_not_block_on_an_unreachable_broker():
    """The fatal path was connecting during startup; start() must not raise."""
    broker = FakeBroker(available=False)
    client = RecordingClient(broker)
    task = await client.start()  # must return promptly and not raise
    assert not task.done()

    # Publishing while down reports failure instead of raising.
    assert await client.publish("minabox/box1/system/service-started", {"service": "x"}) is False
    await client.stop()


@pytest.mark.asyncio
async def test_message_handler_error_does_not_drop_the_connection():
    broker = FakeBroker()

    class Boom(RecordingClient):
        async def on_message(self, topic: str, payload: bytes) -> None:
            await super().on_message(topic, payload)
            raise ValueError("handler bug")

    client = Boom(broker)
    task = await client.start()
    assert await wait_for(lambda: client.is_connected)

    broker.deliver("minabox/box1/audio/play", b"{}")
    assert await wait_for(lambda: len(client.received) == 1)
    broker.deliver("minabox/box1/audio/play", b"{}")
    assert await wait_for(lambda: len(client.received) == 2)

    assert client.is_connected
    assert not task.done()
    await client.stop()


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------


def test_backoff_is_exponential_and_capped():
    client = BaseMQTTClient(
        "h", 1883, initial_backoff=1.0, max_backoff=60.0, backoff_factor=2.0, jitter=0.0
    )
    delays = [client._next_delay(i) for i in range(10)]
    assert delays[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert all(d <= 60.0 for d in delays)
    assert delays[-1] == 60.0


def test_backoff_jitter_stays_within_bounds():
    client = BaseMQTTClient(
        "h", 1883, initial_backoff=1.0, max_backoff=60.0, backoff_factor=2.0, jitter=0.25
    )
    samples = [client._next_delay(3) for _ in range(200)]
    assert all(6.0 <= d <= 10.0 for d in samples)  # 8s +/- 25%
    assert len(set(samples)) > 1, "jitter is not actually randomising"
