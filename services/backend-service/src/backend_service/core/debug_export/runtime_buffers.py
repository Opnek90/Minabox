"""In-memory ring buffers for things that are gone by the time anyone looks.

Container logs are rotated and truncated, and MQTT traffic is not persisted at
all. Both matter for diagnosis: "the button press never reached the backend" is
only answerable if the last few hundred messages are still around.

Bounded, memory-only, no persistence: on a Pi these must not grow and must not
write to the SD card.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_LOG_ENTRIES = 300
MAX_MQTT_ENTRIES = 500
MAX_PAYLOAD_CHARS = 500
CAPTURED_LEVELS = frozenset({"warning", "error", "critical", "exception"})


class RingBuffer:
    """Thread-safe bounded buffer. The log processor runs on whatever thread logs."""

    def __init__(self, maxlen: int) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(item)

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


log_buffer = RingBuffer(MAX_LOG_ENTRIES)
mqtt_buffer = RingBuffer(MAX_MQTT_ENTRIES)


def structlog_ring_processor(logger: Any, method_name: str, event_dict: dict) -> dict:
    """structlog processor that keeps the last warnings and errors.

    Must pass the event dict through untouched - it sits in the middle of the
    processor chain, and swallowing or mutating it would break logging itself.
    Any failure here is deliberately ignored for the same reason.
    """
    try:
        level = str(event_dict.get("level") or method_name or "").lower()
        if level in CAPTURED_LEVELS:
            entry = {
                "at": event_dict.get("timestamp") or datetime.now(UTC).isoformat(),
                "level": level,
                "event": str(event_dict.get("event", ""))[:200],
            }
            for key, value in event_dict.items():
                if key in ("event", "level", "timestamp"):
                    continue
                entry[str(key)[:40]] = str(value)[:200]
            log_buffer.add(entry)
    except Exception:  # noqa: BLE001 - logging must never fail because of this
        pass
    return event_dict


def record_mqtt(direction: str, topic: str, payload: str | bytes | None) -> None:
    """Record one MQTT message. Called from the hot path, so it stays cheap."""
    try:
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", errors="replace")
        else:
            text = str(payload or "")
        mqtt_buffer.add(
            {
                "at": datetime.now(UTC).isoformat(),
                "direction": direction,
                "topic": str(topic)[:200],
                "payload": text[:MAX_PAYLOAD_CHARS],
                "truncated": len(text) > MAX_PAYLOAD_CHARS,
            }
        )
    except Exception:  # noqa: BLE001 - never break message handling
        pass
