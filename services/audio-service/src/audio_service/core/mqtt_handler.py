"""MQTT message handler for the Audio Service.

Processes incoming MQTT commands and routes them to appropriate handlers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError
from shared_lib.logging import setup_structlog

from ..config_schema import AppConfig, AudioConfig
from ..exceptions import ConfigUpdateError

logger = structlog.get_logger(__name__)


class PlayCommand(BaseModel):
    """Play command payload schema."""

    track_id: str
    source_type: str  # "file" or "stream"
    source_uri: str
    start_position_ms: int = 0


class VolumeCommand(BaseModel):
    """Set volume command payload schema."""

    volume: int


# One turn of the knob. The button service publishes an empty payload, so this
# default is what a click is actually worth - which is why it is published in
# audio/status: the display draws one block per detent and must not guess it.
DEFAULT_VOLUME_STEP = 5


class VolumeStepCommand(BaseModel):
    """Volume up/down command payload schema."""

    step: int = DEFAULT_VOLUME_STEP


class AnnounceCommand(BaseModel):
    """Announce command payload schema.

    The backend decides *what* is said and has the clip made; this service only
    plays it. ``source_uri`` is therefore a path into the shared clip volume,
    not a sentence - nothing here synthesises anything.
    """

    source_uri: str
    #: What the music is turned down to while the phrase runs, as a percentage
    #: of the level it is at. 100 means no ducking at all.
    duck_percent: int = 30
    #: How loud the phrase itself is, as a percentage of full gain.
    volume_percent: int = 100


class MQTTMessageHandler:
    """Handles incoming MQTT messages for the Audio Service.

    Routes commands to appropriate handlers and manages config updates.
    """

    def __init__(
        self,
        config: AppConfig,
        on_play: Callable[[PlayCommand], None] | None = None,
        on_pause: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_next: Callable[[], None] | None = None,
        on_prev: Callable[[], None] | None = None,
        on_set_volume: Callable[[VolumeCommand], None] | None = None,
        on_volume_up: Callable[[VolumeStepCommand], None] | None = None,
        on_volume_down: Callable[[VolumeStepCommand], None] | None = None,
        on_mute_toggle: Callable[[], None] | None = None,
        on_announce: Callable[[AnnounceCommand], None] | None = None,
        on_config_update: Callable[[AudioConfig], None] | None = None,
        on_config_reload: Callable[[], None] | None = None,
        on_config_get: Callable[[], None] | None = None,
        on_switch_device: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize MQTT message handler.

        Args:
            config: Service configuration
            on_play: Callback for play commands
            on_pause: Callback for pause commands
            on_stop: Callback for stop commands
            on_next: Callback for next commands
            on_prev: Callback for previous commands
            on_set_volume: Callback for set volume commands
            on_volume_up: Callback for volume up commands
            on_volume_down: Callback for volume down commands
            on_mute_toggle: Callback for mute toggle (mute/unmute)
            on_announce: Callback for announce commands (spoken phrases)
            on_config_update: Callback for config update commands
            on_config_reload: Callback for config reload commands
            on_config_get: Callback for config get requests
            on_switch_device: Callback for switch-device
                (payload: alsa_device?, direction?)
        """
        self._config = config
        self._on_play = on_play
        self._on_pause = on_pause
        self._on_stop = on_stop
        self._on_next = on_next
        self._on_prev = on_prev
        self._on_set_volume = on_set_volume
        self._on_volume_up = on_volume_up
        self._on_volume_down = on_volume_down
        self._on_mute_toggle = on_mute_toggle
        self._on_announce = on_announce
        self._on_config_update = on_config_update
        self._on_config_reload = on_config_reload
        self._on_config_get = on_config_get
        self._on_switch_device = on_switch_device

    async def handle_message(self, topic: str, payload: str) -> None:
        """Handle incoming MQTT message.

        Args:
            topic: MQTT topic
            payload: Message payload (JSON string)
        """
        logger.debug(
            "mqtt_command_received",
            topic=topic,
            payload_length=len(payload),
        )

        try:
            # General config (log_level) lives on .../config/general,
            # not under .../audio/...
            if topic.endswith("/config/general"):
                await self._handle_config_general(payload)
                return
            # Parse action from topic
            action = self._extract_action(topic)
            # Route to appropriate handler
            await self._route_command(action, payload)

        except Exception as e:
            logger.error(
                "mqtt_message_handling_failed",
                topic=topic,
                error=str(e),
            )

    def _extract_action(self, topic: str) -> str:
        """Extract action from MQTT topic.

        Args:
            topic: MQTT topic (e.g., 'minabox/box1/audio/play')

        Returns:
            Action string (e.g., 'play')
        """
        parts = topic.split("/")
        if len(parts) >= 4:
            return "/".join(parts[3:])  # Support nested actions like 'config/update'
        return ""

    async def _route_command(self, action: str, payload: str) -> None:
        """Route command to appropriate handler.

        Args:
            action: Command action
            payload: JSON payload
        """
        # Parse JSON payload
        data: dict[str, Any] = {}
        if payload:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error("invalid_json_payload", action=action, error=str(e))
                return

        # Route to handler
        if action == "play":
            await self._handle_play(data)
        elif action == "pause":
            await self._handle_pause()
        elif action == "stop":
            await self._handle_stop()
        elif action == "next":
            await self._handle_next()
        elif action == "prev":
            await self._handle_prev()
        elif action == "set-volume":
            await self._handle_set_volume(data)
        elif action == "volume-up":
            await self._handle_volume_up(data)
        elif action == "volume-down":
            await self._handle_volume_down(data)
        elif action == "mute-toggle":
            await self._handle_mute_toggle()
        elif action == "announce":
            await self._handle_announce(data)
        elif action == "config/update":
            await self._handle_config_update(data)
        elif action == "config/reload":
            await self._handle_config_reload()
        elif action == "config/get":
            await self._handle_config_get()
        elif action == "switch-device":
            await self._handle_switch_device(data)
        else:
            logger.warning("unknown_command", action=action)

    async def _handle_play(self, data: dict[str, Any]) -> None:
        """Handle play command."""
        try:
            if data and "source_uri" in data:  # Full play command with source
                command = PlayCommand(**data)
                logger.debug(
                    "play_command_received",
                    track_id=command.track_id,
                    source_type=command.source_type,
                )
                if self._on_play:
                    await self._on_play(command)
            else:  # Resume (empty payload or timestamp-only)
                logger.debug("play_resume_command_received")
                if self._on_play:
                    await self._on_play(None)
        except ValidationError as e:
            logger.error("invalid_play_command", error=str(e))

    async def _handle_pause(self) -> None:
        """Handle pause command."""
        logger.debug("pause_command_received")
        if self._on_pause:
            await self._on_pause()

    async def _handle_stop(self) -> None:
        """Handle stop command."""
        logger.debug("stop_command_received")
        if self._on_stop:
            await self._on_stop()

    async def _handle_next(self) -> None:
        """Handle next command."""
        logger.debug("next_command_received")
        if self._on_next:
            await self._on_next()

    async def _handle_prev(self) -> None:
        """Handle previous command."""
        logger.debug("prev_command_received")
        if self._on_prev:
            await self._on_prev()

    async def _handle_set_volume(self, data: dict[str, Any]) -> None:
        """Handle set volume command."""
        try:
            command = VolumeCommand(**data)
            logger.debug("set_volume_command_received", volume=command.volume)
            if self._on_set_volume:
                await self._on_set_volume(command)
        except ValidationError as e:
            logger.error("invalid_volume_command", error=str(e))

    async def _handle_volume_up(self, data: dict[str, Any]) -> None:
        """Handle volume up command."""
        try:
            command = VolumeStepCommand(**data) if data else VolumeStepCommand()
            logger.debug("volume_up_command_received", step=command.step)
            if self._on_volume_up:
                await self._on_volume_up(command)
        except ValidationError as e:
            logger.error("invalid_volume_up_command", error=str(e))

    async def _handle_volume_down(self, data: dict[str, Any]) -> None:
        """Handle volume down command."""
        try:
            command = VolumeStepCommand(**data) if data else VolumeStepCommand()
            logger.debug("volume_down_command_received", step=command.step)
            if self._on_volume_down:
                await self._on_volume_down(command)
        except ValidationError as e:
            logger.error("invalid_volume_down_command", error=str(e))

    async def _handle_mute_toggle(self) -> None:
        """Handle mute toggle command (mute ↔ unmute)."""
        logger.debug("mute_toggle_command_received")
        if self._on_mute_toggle:
            await self._on_mute_toggle()

    async def _handle_announce(self, data: dict[str, Any]) -> None:
        """Handle announce command (play one spoken phrase over the music)."""
        try:
            command = AnnounceCommand(**data)
        except ValidationError as e:
            logger.error("invalid_announce_command", error=str(e))
            return
        logger.debug("announce_command_received", source_uri=command.source_uri)
        if self._on_announce:
            await self._on_announce(command)

    async def _handle_config_update(self, data: dict[str, Any]) -> None:
        """Handle config update command."""
        try:
            new_config = AudioConfig(**data)
            logger.debug("config_update_command_received")
            if self._on_config_update:
                await self._on_config_update(new_config)
        except ValidationError as e:
            logger.error("invalid_config_update", error=str(e))
            raise ConfigUpdateError(f"Invalid config: {e}") from e

    async def _handle_config_reload(self) -> None:
        """Handle config reload command."""
        logger.debug("config_reload_command_received")
        if self._on_config_reload:
            await self._on_config_reload()

    async def _handle_config_get(self) -> None:
        """Handle config get request."""
        logger.debug("config_get_request_received")
        if self._on_config_get:
            await self._on_config_get()

    async def _handle_config_general(self, payload: str) -> None:
        """Handle config/general (e.g. log_level from Admin UI)."""
        try:
            data = json.loads(payload) if payload else {}
            level = (data.get("log_level") or "INFO").upper()
            if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                setup_structlog(level)
                logger.info("log_level_applied", log_level=level)
            else:
                logger.warning("invalid_log_level", log_level=level)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("config_general_parse_failed", error=str(exc))

    async def _handle_switch_device(self, data: dict[str, Any]) -> None:
        """Handle switch-device command (alsa_device or direction=next)."""
        logger.debug("switch_device_command_received", data=data)
        if self._on_switch_device:
            await self._on_switch_device(data)
