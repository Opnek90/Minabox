from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from aiomqtt import Client
import structlog

logger = structlog.get_logger(__name__)


class HasMqttConfig(Protocol):
    mqtt_broker: str
    mqtt_port: int


class BaseMQTTClient(ABC):
    """Small shared base for MQTT clients used across services.

    Services can subclass this and implement domain-specific subscription and
    message handling while reusing the connection lifecycle.
    """

    def __init__(self, host: str, port: int, identifier: str | None = None) -> None:
        self._host = host
        self._port = port
        self._identifier = identifier
        self._client: Client | None = None
        self._running = False

    @classmethod
    def from_config(cls, cfg: HasMqttConfig, identifier: str | None = None) -> "BaseMQTTClient":
        return cls(cfg.mqtt_broker, cfg.mqtt_port, identifier)

    @property
    def client(self) -> Client | None:
        return self._client

    @property
    def is_running(self) -> bool:
        return self._running

    async def connect(self) -> None:
        """Open MQTT connection. Subclasses can override to add logging or auth."""
        logger.debug("mqtt_base_connecting", host=self._host, port=self._port, ident=self._identifier)
        self._client = Client(
            hostname=self._host,
            port=self._port,
            identifier=self._identifier,
        )
        await self._client.__aenter__()
        logger.debug("mqtt_base_connected", host=self._host, port=self._port)
        await self.on_connected()

    async def disconnect(self) -> None:
        if not self._client:
            return
        try:
            await self._client.__aexit__(None, None, None)
            logger.debug("mqtt_base_disconnected")
        finally:
            self._client = None

    async def run(self) -> None:
        """Main receive loop with reconnection hook; subclasses implement iteration."""
        self._running = True
        try:
            await self.connect()
            await self.iter_messages()
        finally:
            self._running = False
            await self.disconnect()

    @abstractmethod
    async def on_connected(self) -> None:
        """Called after a successful connection; subscribe to topics here."""

    @abstractmethod
    async def iter_messages(self) -> None:
        """Iterate over messages and dispatch them."""


__all__ = ["BaseMQTTClient", "HasMqttConfig"]
