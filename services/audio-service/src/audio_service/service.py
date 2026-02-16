"""Audio Service orchestration.

Coordinates between MQTT, VLC backend, and state management.
"""

import asyncio
import json
from datetime import UTC, datetime
from time import time

import structlog

from .audio_backend import AudioStatus
from .config_manager import ConfigManager
from .config_schema import AudioConfig
from .mqtt_client import MQTTClient
from .mqtt_handler import (
    MQTTMessageHandler,
    PlayCommand,
    VolumeCommand,
    VolumeStepCommand,
)
from .state_manager import StateManager
from .vlc_backend import VLCBackend

logger = structlog.get_logger(__name__)


class AudioService:
    """Main audio service orchestrator.

    Coordinates MQTT communication, VLC playback, and state management.
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialize audio service.

        Args:
            config_manager: Configuration manager instance
        """
        self._config_manager = config_manager
        self._config = config_manager.config

        # Initialize components
        self._mqtt_client = MQTTClient(self._config)
        self._vlc_backend = VLCBackend(self._config.audio_config)
        self._state_manager = StateManager(self._config.global_config.audio_state_path)

        # MQTT message handler with callbacks
        self._mqtt_handler = MQTTMessageHandler(
            config=self._config,
            on_play=self._handle_play,
            on_pause=self._handle_pause,
            on_stop=self._handle_stop,
            on_next=self._handle_next,
            on_prev=self._handle_prev,
            on_set_volume=self._handle_set_volume,
            on_volume_up=self._handle_volume_up,
            on_volume_down=self._handle_volume_down,
            on_config_update=self._handle_config_update,
            on_config_reload=self._handle_config_reload,
            on_config_get=self._handle_config_get,
        )

        # Service state
        self._start_time = time()
        self._status_publish_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the audio service."""
        logger.info("audio_service_starting")

        try:
            # Load state
            self._state_manager.load()

            # Initialize VLC backend
            await self._vlc_backend.initialize()

            # FIXED: Set initial volume from state or config default
            state = self._state_manager.get_state()

            # Use last_volume if valid (>0), otherwise use default_volume
            if state.last_volume > 0:
                initial_volume = min(
                    state.last_volume, self._config.audio_config.max_volume
                )
            else:
                initial_volume = min(
                    self._config.audio_config.default_volume,
                    self._config.audio_config.max_volume,
                )

            initial_volume = max(initial_volume, 0)  # Safety clamp

            logger.info("setting_service_initial_volume", volume=initial_volume)
            await self._vlc_backend.set_volume(initial_volume)

            # Connect to MQTT
            await self._mqtt_client.connect()

            # Subscribe to command topics
            await self._subscribe_to_topics()

            # Start background tasks
            self._running = True
            self._status_publish_task = asyncio.create_task(self._status_publish_loop())

            # Publish online status
            await self._publish_system_event("service-started")

            logger.info("audio_service_started")

            # Start listening for MQTT messages
            await self._mqtt_client.listen(self._mqtt_handler.handle_message)

        except Exception as e:
            logger.error("audio_service_start_failed", error=str(e))
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Shutdown the audio service gracefully."""
        logger.info("audio_service_shutting_down")

        self._running = False

        # Cancel background tasks
        if self._status_publish_task is not None:
            self._status_publish_task.cancel()
            try:
                await self._status_publish_task
            except asyncio.CancelledError:
                pass

        # Stop playback
        try:
            await self._vlc_backend.stop()
        except Exception as e:
            logger.warning("shutdown_stop_failed", error=str(e))

        # Save final state
        try:
            await self._save_current_state()
        except Exception as e:
            logger.warning("shutdown_save_state_failed", error=str(e))

        # Publish offline status
        try:
            await self._publish_system_event("service-stopped")
        except Exception as e:
            logger.warning("shutdown_publish_failed", error=str(e))

        # Disconnect MQTT
        await self._mqtt_client.disconnect()

        # Shutdown VLC
        await self._vlc_backend.shutdown()

        logger.info("audio_service_shutdown_complete")

    async def _subscribe_to_topics(self) -> None:
        """Subscribe to all required MQTT topics."""
        device_id = self._config.global_config.minabox_device_id

        topics = [
            f"minabox/{device_id}/audio/play",
            f"minabox/{device_id}/audio/pause",
            f"minabox/{device_id}/audio/stop",
            f"minabox/{device_id}/audio/next",
            f"minabox/{device_id}/audio/prev",
            f"minabox/{device_id}/audio/set-volume",
            f"minabox/{device_id}/audio/volume-up",
            f"minabox/{device_id}/audio/volume-down",
            f"minabox/{device_id}/audio/config/update",
            f"minabox/{device_id}/audio/config/reload",
            f"minabox/{device_id}/audio/config/get",
        ]

        for topic in topics:
            await self._mqtt_client.subscribe(topic)

    async def _status_publish_loop(self) -> None:
        """Periodically publish audio status to MQTT."""
        while self._running:
            try:
                await asyncio.sleep(2.0)  # Publish every 2 seconds
                await self._publish_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("status_publish_loop_error", error=str(e))

    async def _publish_status(self) -> None:
        """Publish current audio status to MQTT."""
        try:
            status = await self._vlc_backend.get_status()

            payload = {
                "state": status.state.value,
                "track_id": status.track_id,
                "source_type": status.source_type,
                "source_uri": status.source_uri,
                "position_ms": status.position_ms,
                "duration_ms": status.duration_ms,
                "volume": status.volume,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            topic = self._config.get_mqtt_topic("audio", "status")
            await self._mqtt_client.publish(
                topic=topic,
                payload=json.dumps(payload),
                retain=True,  # Retain status for new subscribers
            )

        except Exception as e:
            logger.error("publish_status_failed", error=str(e))

    async def _publish_error(self, error_code: str, message: str, **details) -> None:
        """Publish error event to MQTT."""
        payload = {
            "error_code": error_code,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            **details,
        }

        topic = self._config.get_mqtt_topic("audio", "error")
        await self._mqtt_client.publish(topic=topic, payload=json.dumps(payload))

    async def _publish_system_event(self, event: str) -> None:
        """Publish system event to MQTT."""
        payload = {
            "event": event,
            "service": "audio",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        topic = self._config.get_mqtt_topic("system", event)
        await self._mqtt_client.publish(topic=topic, payload=json.dumps(payload))

    async def _publish_config_response(
        self, success: bool, error: str | None = None
    ) -> None:
        """Publish config operation response."""
        payload = {
            "success": success,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        topic = self._config.get_mqtt_topic("audio", "config/response")
        await self._mqtt_client.publish(topic=topic, payload=json.dumps(payload))

    async def _save_current_state(self) -> None:
        """Save current playback state."""
        status = await self._vlc_backend.get_status()
        self._state_manager.update_playback(
            track_id=status.track_id,
            source_type=status.source_type,
            source_uri=status.source_uri,
            position_ms=status.position_ms,
            state=status.state,
            volume=status.volume,
        )

    # Command Handlers

    async def _handle_play(self, command: PlayCommand | None) -> None:
        """Handle play command."""
        try:
            if command is not None:
                # Play new track
                self._vlc_backend.set_track_metadata(
                    track_id=command.track_id,
                    source_type=command.source_type,
                )
                await self._vlc_backend.play(
                    source_uri=command.source_uri,
                    start_position_ms=command.start_position_ms,
                )
            else:
                # Resume from state
                state = self._state_manager.get_state()
                if state.last_source_uri and self._state_manager.can_resume():
                    self._vlc_backend.set_track_metadata(
                        track_id=state.last_track_id,
                        source_type=state.last_source_type,
                    )
                    await self._vlc_backend.play(
                        source_uri=state.last_source_uri,
                        start_position_ms=state.last_position_ms,
                    )
                else:
                    logger.warning("play_resume_no_state")

            await self._publish_status()

        except Exception as e:
            logger.error("handle_play_failed", error=str(e))
            await self._publish_error("playback_error", str(e))

    async def _handle_pause(self) -> None:
        """Handle pause command."""
        try:
            await self._vlc_backend.pause()
            await self._save_current_state()
            await self._publish_status()
        except Exception as e:
            logger.error("handle_pause_failed", error=str(e))
            await self._publish_error("playback_error", str(e))

    async def _handle_stop(self) -> None:
        """Handle stop command."""
        try:
            await self._vlc_backend.stop()
            self._state_manager.clear()
            await self._publish_status()
        except Exception as e:
            logger.error("handle_stop_failed", error=str(e))
            await self._publish_error("playback_error", str(e))

    async def _handle_next(self) -> None:
        """Handle next command (backend decides next track)."""
        logger.info("next_command_received_awaiting_backend")
        # Backend will send new play command with next track

    async def _handle_prev(self) -> None:
        """Handle previous command (backend decides previous track)."""
        logger.info("prev_command_received_awaiting_backend")
        # Backend will send new play command with previous track

    async def _handle_set_volume(self, command: VolumeCommand) -> None:
        """Handle set volume command."""
        try:
            await self._vlc_backend.set_volume(command.volume)
            await self._publish_status()
        except Exception as e:
            logger.error("handle_set_volume_failed", error=str(e))
            await self._publish_error("volume_error", str(e))

    async def _handle_volume_up(self, command: VolumeStepCommand) -> None:
        """Handle volume up command."""
        try:
            current_volume = await self._vlc_backend.get_volume()
            new_volume = min(current_volume + command.step, 100)
            await self._vlc_backend.set_volume(new_volume)
            await self._publish_status()
        except Exception as e:
            logger.error("handle_volume_up_failed", error=str(e))
            await self._publish_error("volume_error", str(e))

    async def _handle_volume_down(self, command: VolumeStepCommand) -> None:
        """Handle volume down command."""
        try:
            current_volume = await self._vlc_backend.get_volume()
            new_volume = max(current_volume - command.step, 0)
            await self._vlc_backend.set_volume(new_volume)
            await self._publish_status()
        except Exception as e:
            logger.error("handle_volume_down_failed", error=str(e))
            await self._publish_error("volume_error", str(e))

    async def _handle_config_update(self, new_config: AudioConfig) -> None:
        """Handle config update command."""
        try:
            self._config_manager.update_audio_config(new_config)
            await self._publish_config_response(success=True)
            logger.info("config_update_successful")
        except Exception as e:
            logger.error("config_update_failed", error=str(e))
            await self._publish_config_response(success=False, error=str(e))

    async def _handle_config_reload(self) -> None:
        """Handle config reload command."""
        try:
            self._config_manager.reload_audio_config()
            await self._publish_config_response(success=True)
            logger.info("config_reload_successful")
        except Exception as e:
            logger.error("config_reload_failed", error=str(e))
            await self._publish_config_response(success=False, error=str(e))

    async def _handle_config_get(self) -> None:
        """Handle config get request."""
        try:
            config_dict = self._config.audio_config.model_dump()
            topic = self._config.get_mqtt_topic("audio", "config/response")
            await self._mqtt_client.publish(
                topic=topic,
                payload=json.dumps(config_dict),
            )
            logger.info("config_get_response_sent")
        except Exception as e:
            logger.error("config_get_failed", error=str(e))

    # Public API for FastAPI routes

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        return time() - self._start_time

    def is_mqtt_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._mqtt_client.is_connected()

    def is_vlc_initialized(self) -> bool:
        """Check if VLC backend is initialized."""
        return self._vlc_backend._initialized

    async def get_audio_status(self) -> AudioStatus:
        """Get current audio status."""
        return await self._vlc_backend.get_status()
