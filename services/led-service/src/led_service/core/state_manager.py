"""State manager for deriving logical states from MQTT messages.

This module maps MQTT topics and payloads to logical states that the LED
service understands (e.g. 'audio_playing', 'system_error', 'rfid_scanned').
"""

from __future__ import annotations

import json
from collections.abc import Callable

import structlog

from ..exceptions import StateError

logger = structlog.get_logger(__name__)


class StateManager:
    """Derives logical states from MQTT messages."""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._state_derivation_rules = self._build_derivation_rules()

    def _build_derivation_rules(self) -> dict[str, Callable[[bytes], str]]:
        prefix = f"minabox/{self.device_id}"

        return {
            f"{prefix}/audio/status": self._derive_audio_state,
            f"{prefix}/rfid/tag-scanned": lambda _: "rfid_scanned",
            f"{prefix}/rfid/tag-removed": lambda _: "rfid_removed",
            f"{prefix}/rfid/unknown-tag": lambda _: "rfid_unknown_tag",
            # Issue #63: blocked tag fires rfid_tag_blocked so LED bindings can
            # react (e.g. a red blink pattern) without starting playback.
            f"{prefix}/rfid/tag-blocked": lambda _: "rfid_tag_blocked",
            # Retained presence topic: allows state recovery after LED config
            # reload or any other re-initialization. Maps tag_present=true to
            # rfid_scanned and tag_present=false to rfid_removed.
            f"{prefix}/rfid/presence": self._derive_rfid_presence_state,
            f"{prefix}/system/service-started": lambda _: "system_online",
            f"{prefix}/system/service-error": lambda _: "system_error",
            f"{prefix}/system/booting": lambda _: "system_booting",
            f"{prefix}/button/raw-event": lambda _: "button_pressed",
            f"{prefix}/backend/unreachable": lambda _: "backend_unreachable",
            f"{prefix}/led/usage-denied": lambda _: "usage_denied",
        }

    def derive_state(self, topic: str, payload: bytes) -> str | None:
        derivation_func = self._state_derivation_rules.get(topic)

        if derivation_func is None:
            logger.debug("no_derivation_rule", topic=topic)
            return None

        try:
            state = derivation_func(payload)
            logger.debug("state_derived", topic=topic, logical_state=state)
            return state
        except Exception as exc:
            logger.error(
                "state_derivation_failed",
                topic=topic,
                error=str(exc),
                exc_info=True,
            )
            raise StateError(
                f"Failed to derive state from topic '{topic}': {exc}"
            ) from exc

    def _derive_audio_state(self, payload: bytes) -> str:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateError(f"Invalid JSON in audio/status payload: {exc}") from exc

        audio_state = data.get("state")
        if audio_state == "playing":
            return "audio_playing"
        elif audio_state == "paused":
            return "audio_paused"
        elif audio_state == "stopped":
            return "audio_stopped"
        else:
            logger.warning("unknown_audio_state", state=audio_state)
            return "audio_stopped"

    def _derive_rfid_presence_state(self, payload: bytes) -> str:
        """Derive rfid_scanned / rfid_removed from the retained presence topic.

        This is used for state recovery after LED re-initialization (e.g. after
        a config reload). The MQTT broker delivers the retained presence message
        immediately on subscribe, so the LED-service always recovers the correct
        RFID state without waiting for the next physical scan event.

        Args:
            payload: JSON payload from minabox/{id}/rfid/presence.

        Returns:
            'rfid_scanned' if tag_present is True, 'rfid_removed' otherwise.
        """
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateError(f"Invalid JSON in rfid/presence payload: {exc}") from exc

        return "rfid_scanned" if data.get("tag_present") else "rfid_removed"
