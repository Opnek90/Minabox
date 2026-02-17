"""State manager for deriving logical states from MQTT messages.

This module maps MQTT topics and payloads to logical states that the LED
service understands (e.g. 'audio_playing', 'system_error', 'rfid_scanned').
"""

from __future__ import annotations

import json
from typing import Dict, Optional

import structlog

from .exceptions import StateError


logger = structlog.get_logger(__name__)


class StateManager:
    """Derives logical states from MQTT messages."""

    def __init__(self, device_id: str) -> None:
        """Initialize the state manager.
        
        Args:
            device_id: The device ID for MQTT topic matching.
        """
        self.device_id = device_id
        self._state_derivation_rules = self._build_derivation_rules()

    def _build_derivation_rules(self) -> Dict[str, callable]:
        """Build the mapping from MQTT topics to state derivation functions.
        
        Returns:
            Dictionary mapping topic patterns to derivation functions.
        """
        prefix = f"minabox/{self.device_id}"
        
        return {
            f"{prefix}/audio/status": self._derive_audio_state,
            f"{prefix}/rfid/tag-scanned": lambda _: "rfid_scanned",
            f"{prefix}/rfid/tag-removed": lambda _: "rfid_removed",
            f"{prefix}/rfid/unknown-tag": lambda _: "rfid_unknown_tag",
            f"{prefix}/system/service-started": lambda _: "system_online",
            f"{prefix}/system/service-error": lambda _: "system_error",
            f"{prefix}/system/booting": lambda _: "system_booting",
            f"{prefix}/button/raw-event": lambda _: "button_pressed",
            f"{prefix}/backend/unreachable": lambda _: "backend_unreachable",
        }

    def derive_state(self, topic: str, payload: bytes) -> Optional[str]:
        """Derive a logical state from an MQTT message.
        
        Args:
            topic: The MQTT topic.
            payload: The MQTT message payload.
            
        Returns:
            The derived logical state, or None if no derivation is possible.
            
        Raises:
            StateError: If state derivation fails unexpectedly.
        """
        derivation_func = self._state_derivation_rules.get(topic)
        
        if derivation_func is None:
            logger.debug("no_derivation_rule", topic=topic)
            return None
        
        try:
            state = derivation_func(payload)
            logger.debug(
                "state_derived",
                topic=topic,
                logical_state=state,
            )
            return state
        except Exception as exc:
            logger.error(
                "state_derivation_failed",
                topic=topic,
                error=str(exc),
                exc_info=True,
            )
            raise StateError(f"Failed to derive state from topic '{topic}': {exc}") from exc

    def _derive_audio_state(self, payload: bytes) -> str:
        """Derive audio state from audio/status payload.
        
        Expected payload format:
        {
            "state": "playing" | "paused" | "stopped",
            ...
        }
        
        Args:
            payload: The MQTT message payload.
            
        Returns:
            The derived logical state (e.g. 'audio_playing').
            
        Raises:
            StateError: If the payload is invalid.
        """
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
            return "audio_stopped"  # Fallback
