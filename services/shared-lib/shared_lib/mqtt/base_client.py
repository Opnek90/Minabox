"""Resilient MQTT client shared by all Minabox services.

Every service used to carry its own near-identical copy of the connect /
subscribe / message-loop code. They also shared the same fatal weakness: the
broker connection was established *during startup*, outside the supervised
message loop, so a broker that was briefly unreachable took the whole process
down (see docs/Troubleshooting.md, "MQTT-Verlust").

This module centralises the lifecycle so the correction lives in one place:

* connecting is never fatal -- ``run()`` retries forever with exponential
  backoff plus jitter, and a DNS failure (broker container not back yet) is
  treated exactly like a refused connection,
* subscriptions and the last reported status are replayed on every successful
  (re)connect, so a reconnected service is not silently mute,
* ``is_connected`` reflects the *live* socket state, so ``/health`` can report
  ``mqtt_connected: false`` while the broker is away,
* ``publish()`` never raises when the broker is gone -- it reports failure via
  its return value, so a status publish cannot kill a caller's task.

Services subclass this and implement :meth:`on_message` (and optionally
:meth:`on_connected`) with their domain-specific dispatch.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Callable
from typing import Any, Protocol

import structlog
from aiomqtt import Client, MqttError

logger = structlog.get_logger(__name__)

# Backoff defaults: first retry after ~1s, capped at ~60s, +/-25% jitter so a
# whole fleet of services does not hammer the broker in lockstep.
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 60.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_JITTER = 0.25


class HasMqttConfig(Protocol):
    mqtt_broker: str
    mqtt_port: int


def _encode(payload: Any) -> bytes | str:
    """Encode a publish payload; dicts and lists become JSON."""
    if isinstance(payload, (bytes, bytearray, str)):
        return payload if not isinstance(payload, bytearray) else bytes(payload)
    return json.dumps(payload)


class BaseMQTTClient:
    """MQTT client with a self-healing connection.

    Subclasses implement :meth:`on_message`. The connection lifecycle, the
    reconnect backoff, subscription replay and status replay are handled here.
    """

    def __init__(
        self,
        host: str,
        port: int,
        identifier: str | None = None,
        *,
        service_name: str = "service",
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._identifier = identifier
        self._service_name = service_name

        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._backoff_factor = backoff_factor
        self._jitter = jitter
        self._client_factory = client_factory

        self._client: Any | None = None
        self._connected = False
        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Replayed on every (re)connect.
        self._subscriptions: dict[str, int] = {}
        self._remembered: dict[str, tuple[bytes | str, int, bool]] = {}

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: HasMqttConfig, identifier: str | None = None, **kwargs: Any):
        return cls(cfg.mqtt_broker, cfg.mqtt_port, identifier, **kwargs)

    def _make_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        return Client(hostname=self._host, port=self._port, identifier=self._identifier)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def client(self) -> Any | None:
        return self._client

    @property
    def is_connected(self) -> bool:
        """True only while the broker connection is actually usable.

        This is the value ``/health`` reports as ``mqtt_connected``; it flips to
        False the moment message iteration fails, not just at shutdown.
        """
        return self._connected

    @property
    def is_running(self) -> bool:
        """True while the supervised loop is active (regardless of connection)."""
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> asyncio.Task[None]:
        """Start the supervised message loop without blocking on the broker.

        Startup must not depend on the broker being reachable, so this returns
        as soon as the loop task exists. Publishes issued before the first
        successful connect are dropped (or replayed, if remembered).
        """
        if self._task is not None and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self.run())
        return self._task

    async def connect(self) -> None:
        """Open a single connection attempt. Raises MqttError on failure.

        Prefer :meth:`start`; this is exposed for tests and for callers that
        deliberately want a one-shot attempt.
        """
        client = self._make_client()
        await client.__aenter__()
        self._client = client
        self._connected = True
        logger.debug(
            "mqtt_connected",
            service=self._service_name,
            broker=self._host,
            port=self._port,
        )

    async def disconnect(self) -> None:
        """Close the connection, tolerating an already-dead socket."""
        self._connected = False
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.__aexit__(None, None, None)
            logger.debug("mqtt_disconnected", service=self._service_name)
        except Exception as exc:  # noqa: BLE001 - teardown must never propagate
            logger.debug("mqtt_disconnect_error", service=self._service_name, error=str(exc))

    async def stop(self) -> None:
        """Stop the loop and close the connection."""
        self._running = False
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.debug("mqtt_stop_error", service=self._service_name, error=str(exc))
        self._task = None
        await self.disconnect()

    def _next_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped at ``max_backoff``."""
        base = min(
            self._initial_backoff * (self._backoff_factor ** attempt),
            self._max_backoff,
        )
        if self._jitter:
            base *= random.uniform(1.0 - self._jitter, 1.0 + self._jitter)
        return max(0.0, base)

    async def run(self) -> None:
        """Supervised receive loop. Only returns via :meth:`stop` or cancellation.

        Connection errors -- refused, DNS not resolvable, disconnected mid
        iteration -- are all the same ordinary case: wait, then try again.
        """
        self._running = True
        attempt = 0
        try:
            while self._running:
                try:
                    await self.connect()
                    attempt = 0
                    await self._replay_state()
                    await self.on_connected()
                    await self._consume()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - loop must survive anything
                    if isinstance(exc, MqttError):
                        logger.warning(
                            "mqtt_connection_lost",
                            service=self._service_name,
                            error=str(exc),
                        )
                    else:
                        logger.warning(
                            "mqtt_loop_error",
                            service=self._service_name,
                            error=str(exc),
                            exc_info=True,
                        )
                    await self._on_loop_error(exc)
                else:
                    # Iteration ended without raising. Either stop() was
                    # requested, or the broker closed the stream quietly -- the
                    # latter still needs a backoff, otherwise we would spin.
                    await self.disconnect()

                if not self._running:
                    break
                delay = self._next_delay(attempt)
                attempt += 1
                logger.info(
                    "mqtt_reconnect_scheduled",
                    service=self._service_name,
                    delay_seconds=round(delay, 2),
                    attempt=attempt,
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise
        finally:
            self._running = False
            await self.disconnect()

    async def _on_loop_error(self, exc: BaseException) -> None:
        self._connected = False
        await self.disconnect()
        try:
            await self.on_disconnected(exc)
        except Exception as hook_exc:  # noqa: BLE001
            logger.warning(
                "mqtt_on_disconnected_failed",
                service=self._service_name,
                error=str(hook_exc),
            )

    async def _consume(self) -> None:
        """Iterate broker messages and dispatch them to :meth:`on_message`."""
        assert self._client is not None
        async for message in self._client.messages:
            if not self._running:
                break
            topic = message.topic.value
            payload = message.payload
            try:
                await self.on_message(topic, payload)
            except Exception as exc:  # noqa: BLE001 - a handler bug must not drop the connection
                logger.error(
                    "mqtt_message_handler_error",
                    service=self._service_name,
                    topic=topic,
                    error=str(exc),
                    exc_info=True,
                )

    async def _replay_state(self) -> None:
        """Re-apply subscriptions and re-publish the last reported status.

        Without this a reconnected service is connected but mute: the broker
        has forgotten our subscriptions, and any retained status we published
        before the outage may have been lost with the broker.
        """
        for topic, qos in list(self._subscriptions.items()):
            try:
                await self._client.subscribe(topic, qos=qos)
                logger.debug("mqtt_resubscribed", service=self._service_name, topic=topic)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mqtt_resubscribe_failed",
                    service=self._service_name,
                    topic=topic,
                    error=str(exc),
                )
                raise

        for topic, (payload, qos, retain) in list(self._remembered.items()):
            try:
                await self._client.publish(topic, payload, qos=qos, retain=retain)
                logger.debug("mqtt_status_republished", service=self._service_name, topic=topic)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mqtt_status_republish_failed",
                    service=self._service_name,
                    topic=topic,
                    error=str(exc),
                )
                raise

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def subscribe(self, topic: str, qos: int = 1) -> None:
        """Subscribe, and remember the topic so it survives a reconnect.

        Safe to call before the first connection: the topic is recorded and
        applied as soon as the client is connected.
        """
        self._subscriptions[topic] = qos
        if not self._connected or self._client is None:
            logger.debug(
                "mqtt_subscribe_deferred", service=self._service_name, topic=topic
            )
            return
        try:
            await self._client.subscribe(topic, qos=qos)
            logger.debug("mqtt_subscribed", service=self._service_name, topic=topic)
        except Exception as exc:  # noqa: BLE001 - replayed on the next reconnect
            logger.warning(
                "mqtt_subscribe_failed",
                service=self._service_name,
                topic=topic,
                error=str(exc),
            )

    async def unsubscribe(self, topic: str, *, forget: bool = True) -> None:
        if forget:
            self._subscriptions.pop(topic, None)
        if not self._connected or self._client is None:
            return
        try:
            await self._client.unsubscribe(topic)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "mqtt_unsubscribe_failed",
                service=self._service_name,
                topic=topic,
                error=str(exc),
            )

    async def resubscribe(self, topic: str, qos: int = 1) -> None:
        """Force the broker to re-deliver a retained topic.

        A retained message is only delivered on subscribe, so a live connection
        needs an unsubscribe/subscribe cycle to see it again.
        """
        await self.unsubscribe(topic, forget=False)
        await self.subscribe(topic, qos=qos)

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 1,
        retain: bool = False,
        *,
        remember: bool = False,
    ) -> bool:
        """Publish a message. Never raises because of a broken connection.

        Args:
            remember: keep this as the service's last reported state for
                ``topic`` and re-publish it after every reconnect.

        Returns:
            True if the message reached the broker, False if it was dropped
            because the connection is down.
        """
        encoded = _encode(payload)
        if remember:
            self._remembered[topic] = (encoded, qos, retain)

        if not self._connected or self._client is None:
            logger.debug(
                "mqtt_publish_skipped_disconnected",
                service=self._service_name,
                topic=topic,
            )
            return False

        try:
            await self._client.publish(topic, encoded, qos=qos, retain=retain)
            logger.debug("mqtt_published", service=self._service_name, topic=topic)
            return True
        except Exception as exc:  # noqa: BLE001 - the run loop handles reconnection
            logger.warning(
                "mqtt_publish_failed",
                service=self._service_name,
                topic=topic,
                error=str(exc),
            )
            self._connected = False
            return False

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    async def apply_general_config(self, payload: bytes) -> bool:
        """Apply a ``config/general`` payload (currently the log level).

        Every service handled this identically; it lives here so the four
        copies cannot drift apart.

        Returns:
            True if the payload was understood and applied.
        """
        from shared_lib.logging import setup_structlog

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            logger.warning(
                "config_general_parse_failed", service=self._service_name, error=str(exc)
            )
            return False

        level = (data.get("log_level") or "INFO").upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            logger.warning("invalid_log_level", service=self._service_name, log_level=level)
            return False

        setup_structlog(level)
        logger.info("log_level_applied", service=self._service_name, log_level=level)
        return True

    async def on_message(self, topic: str, payload: bytes) -> None:
        """Handle one incoming message. Override in subclasses."""

    async def on_connected(self) -> None:
        """Called after subscriptions and status have been replayed."""

    async def on_disconnected(self, exc: BaseException) -> None:
        """Called after the connection dropped, before the backoff sleep."""


__all__ = ["BaseMQTTClient", "HasMqttConfig"]
