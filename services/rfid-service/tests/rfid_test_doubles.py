"""Test doubles for the RFID service tests."""

from __future__ import annotations

from typing import Any

from rfid_service.config_schema import (
    AppConfig,
    EnvConfig,
    ModeConfig,
    ReaderConfig,
    RFIDServiceConfig,
    ServiceConfig,
)
from rfid_service.exceptions import ProtocolError
from rfid_service.infrastructure.hardware import RFIDReader


class FakeMQTT:
    """Records publishes instead of talking to a broker."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.is_connected = True

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 1,
        retain: bool = False,
        *,
        remember: bool = False,
    ) -> bool:
        self.messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
                "remember": remember,
            }
        )
        return True

    def topics(self) -> list[str]:
        """Published topics, reduced to the part after the device prefix."""
        return [m["topic"].split("/rfid/", 1)[-1] for m in self.messages]

    def payloads_for(self, suffix: str) -> list[dict[str, Any]]:
        return [m["payload"] for m in self.messages_for(suffix)]

    def messages_for(self, suffix: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["topic"].endswith(f"/rfid/{suffix}")]


class ScriptedReader(RFIDReader):
    """Reader that replays a fixed sequence of reads.

    Each script entry is either a tag UID, ``None`` for an empty read, or an
    exception instance that is raised instead. Once the script is exhausted the
    reader keeps returning the ``tail`` value and invokes ``on_exhausted``,
    which the loop tests use to stop the manager.
    """

    def __init__(
        self,
        script: list[Any] | None = None,
        *,
        tail: str | None = None,
        init_failures: int = 0,
        init_error: Exception | None = None,
        on_exhausted: Any = None,
        reader_id: str = "scripted_test",
    ) -> None:
        self._script = list(script or [])
        self._tail = tail
        self._init_failures = init_failures
        self._init_error = init_error or ProtocolError("scripted init failure")
        self._on_exhausted = on_exhausted
        self._reader_id = reader_id

        self.init_calls = 0
        self.read_calls = 0
        self.cleanup_calls = 0

    def initialize(self) -> None:
        self.init_calls += 1
        if self.init_calls <= self._init_failures:
            raise self._init_error

    def read_tag_uid(self) -> str | None:
        self.read_calls += 1
        if not self._script:
            if self._on_exhausted is not None:
                self._on_exhausted()
            return self._tail
        entry = self._script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return entry

    def cleanup(self) -> None:
        self.cleanup_calls += 1

    @property
    def reader_id(self) -> str:
        return self._reader_id


def make_config(**reader_overrides: Any) -> AppConfig:
    """Build an AppConfig with test-friendly defaults."""
    learning_timeout_s = reader_overrides.pop("learning_timeout_s", 300)
    reader_settings: dict[str, Any] = {
        "reader_type": "mock",
        "interface": "i2c",
        "scan_interval_ms": 20,
        "duplicate_suppression_ms": 2000,
        "removal_debounce_reads": 3,
        "error_retry_delay_ms": 100,
        "init_retry_delay_ms": 100,
        "init_retry_max_delay_ms": 200,
        "init_max_attempts": 0,
        "reinit_after_read_errors": 5,
    }
    reader_settings.update(reader_overrides)

    return AppConfig(
        env=EnvConfig(
            mqtt_broker="broker",
            mqtt_port=1883,
            minabox_device_id="testbox",
            log_level="INFO",
        ),
        rfid=RFIDServiceConfig(
            reader=ReaderConfig(**reader_settings),
            modes=ModeConfig(learning_timeout_s=learning_timeout_s),
            service=ServiceConfig(),
        ),
    )
