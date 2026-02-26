"""Audio Service orchestration.

Coordinates between MQTT, VLC backend, and state management.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import time

import structlog

from .audio_backend import AudioStatus
from .config_manager import ConfigManager
from .audio_backend import PlaybackState
from .config_schema import AppConfig, AudioConfig, OutputDeviceType
from .mqtt_client import MQTTClient
from .mqtt_handler import (
    MQTTMessageHandler,
    PlayCommand,
    VolumeCommand,
    VolumeStepCommand,
)
from .state_manager import StateManager

logger = structlog.get_logger(__name__)


class AudioService:
    """Main audio service orchestrator.

    Coordinates MQTT communication, VLC playback, and state management.
    """

    def __init__(self, config: AppConfig) -> None:
        """Initialize audio service.

        Args:
            config: Application configuration.
        """
        self._config = config
        self._config_manager = ConfigManager(config.env.audio_config_path)

        # Initialize components
        self._mqtt_client = MQTTClient(config)
        from .vlc_backend import VLCBackend
        self._vlc_backend = VLCBackend(config.audio)
        self._state_manager = StateManager(Path(config.env.audio_state_path))

        # MQTT message handler with callbacks
        self._mqtt_handler = MQTTMessageHandler(
            config=config,
            on_play=self._handle_play,
            on_pause=self._handle_pause,
            on_stop=self._handle_stop,
            on_next=self._handle_next,
            on_prev=self._handle_prev,
            on_set_volume=self._handle_set_volume,
            on_volume_up=self._handle_volume_up,
            on_volume_down=self._handle_volume_down,
            on_mute_toggle=self._handle_mute_toggle,
            on_config_update=self._handle_config_update,
            on_config_reload=self._handle_config_reload,
            on_config_get=self._handle_config_get,
            on_switch_device=self._handle_switch_device,
        )

        # Service state
        self._start_time = time()
        self._muted = False
        self._volume_before_mute = 0
        self._status_publish_task: asyncio.Task | None = None
        self._mqtt_task: asyncio.Task | None = None
        self._running = False

    @property
    def mqtt_client(self) -> MQTTClient:
        """Expose MQTT client for health checks."""
        return self._mqtt_client

    def _get_audio_config(self) -> AudioConfig:
        """Return current audio config (reloaded from disk if available)."""
        current = self._config_manager.get_current_config()
        return current if current is not None else self._config.audio

    async def start(self) -> None:
        """Start the audio service (non-blocking)."""
        logger.debug("audio_service_starting")

        try:
            # Load state
            self._state_manager.load()

            # Initialize VLC backend
            await self._vlc_backend.initialize()

            # Set initial volume
            audio_cfg = self._get_audio_config()
            state = self._state_manager.get_state()
            if state.last_volume > 0:
                initial_volume = min(state.last_volume, audio_cfg.max_volume)
            else:
                initial_volume = min(
                    audio_cfg.default_volume,
                    audio_cfg.max_volume,
                )
            initial_volume = max(initial_volume, 0)
            logger.debug("setting_service_initial_volume", volume=initial_volume)
            await self._vlc_backend.set_volume(initial_volume)

            # Connect to MQTT
            await self._mqtt_client.connect()

            # Subscribe to command topics
            await self._subscribe_to_topics()

            # Set message handler on MQTT client
            self._mqtt_client._on_message = self._mqtt_handler.handle_message

            # Start background tasks
            self._running = True
            self._status_publish_task = asyncio.create_task(self._status_publish_loop())
            self._mqtt_task = asyncio.create_task(self._mqtt_client.run())

            # Publish online status
            await self._publish_system_event("service-started")

            logger.info("audio_service_started")

        except Exception as exc:
            logger.error("audio_service_start_failed", error=str(exc))
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

        # Stop MQTT run loop
        await self._mqtt_client.stop()
        if self._mqtt_task is not None:
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Stop playback
        try:
            await self._vlc_backend.stop()
        except Exception as exc:
            logger.warning("shutdown_stop_failed", error=str(exc))

        # Save final state
        try:
            await self._save_current_state()
        except Exception as exc:
            logger.warning("shutdown_save_state_failed", error=str(exc))

        # Publish offline status
        try:
            await self._publish_system_event("service-stopped")
        except Exception as exc:
            logger.warning("shutdown_publish_failed", error=str(exc))

        # Disconnect MQTT
        await self._mqtt_client.disconnect()

        # Shutdown VLC
        await self._vlc_backend.shutdown()

        logger.info("audio_service_shutdown_complete")

    async def _subscribe_to_topics(self) -> None:
        """Subscribe to all required MQTT topics."""
        device_id = self._config.env.minabox_device_id

        topics = [
            f"minabox/{device_id}/audio/play",
            f"minabox/{device_id}/audio/pause",
            f"minabox/{device_id}/audio/stop",
            f"minabox/{device_id}/audio/next",
            f"minabox/{device_id}/audio/prev",
            f"minabox/{device_id}/audio/set-volume",
            f"minabox/{device_id}/audio/volume-up",
            f"minabox/{device_id}/audio/volume-down",
            f"minabox/{device_id}/audio/mute-toggle",
            f"minabox/{device_id}/audio/config/update",
            f"minabox/{device_id}/audio/config/reload",
            f"minabox/{device_id}/audio/config/get",
            f"minabox/{device_id}/audio/switch-device",
        ]

        for topic in topics:
            await self._mqtt_client.subscribe(topic)

    async def _status_publish_loop(self) -> None:
        """Periodically publish audio status to MQTT."""
        while self._running:
            try:
                await asyncio.sleep(2.0)
                await self._publish_status()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("status_publish_loop_error", error=str(exc))

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
                "muted": self._muted,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            topic = self._config.get_mqtt_topic("audio", "status")
            await self._mqtt_client.publish(topic, payload, retain=True)

        except Exception as exc:
            logger.error("publish_status_failed", error=str(exc))

    async def _publish_error(self, error_code: str, message: str, **details) -> None:
        """Publish error event to MQTT."""
        payload = {
            "error_code": error_code,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            **details,
        }
        topic = self._config.get_mqtt_topic("audio", "error")
        await self._mqtt_client.publish(topic, payload)

    async def _publish_system_event(self, event: str) -> None:
        """Publish system event to MQTT."""
        payload = {
            "event": event,
            "service": "audio",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        topic = self._config.get_mqtt_topic("system", event)
        await self._mqtt_client.publish(topic, payload)

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
        await self._mqtt_client.publish(topic, payload)

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
                self._vlc_backend.set_track_metadata(
                    track_id=command.track_id,
                    source_type=command.source_type,
                )
                await self._vlc_backend.play(
                    source_uri=command.source_uri,
                    start_position_ms=command.start_position_ms,
                )
            else:
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
        except Exception as exc:
            logger.error("handle_play_failed", error=str(exc))
            await self._publish_error("playback_error", str(exc))

    async def _handle_pause(self) -> None:
        """Handle pause command."""
        try:
            await self._vlc_backend.pause()
            await self._save_current_state()
            await self._publish_status()
        except Exception as exc:
            logger.error("handle_pause_failed", error=str(exc))
            await self._publish_error("playback_error", str(exc))

    async def _handle_stop(self) -> None:
        """Handle stop command."""
        try:
            await self._vlc_backend.stop()
            self._state_manager.clear()
            await self._publish_status()
        except Exception as exc:
            logger.error("handle_stop_failed", error=str(exc))
            await self._publish_error("playback_error", str(exc))

    async def _handle_next(self) -> None:
        """Handle next command (backend decides next track)."""
        logger.debug("next_command_received_awaiting_backend")

    async def _handle_prev(self) -> None:
        """Handle previous command (backend decides previous track)."""
        logger.debug("prev_command_received_awaiting_backend")

    async def _handle_set_volume(self, command: VolumeCommand) -> None:
        """Handle set volume command."""
        try:
            await self._vlc_backend.set_volume(command.volume)
            await self._save_current_state()
            await self._publish_status()
        except Exception as exc:
            logger.error("handle_set_volume_failed", error=str(exc))
            await self._publish_error("volume_error", str(exc))

    async def _handle_volume_up(self, command: VolumeStepCommand) -> None:
        """Handle volume up command."""
        try:
            current_volume = await self._vlc_backend.get_volume()
            new_volume = min(current_volume + command.step, 100)
            await self._vlc_backend.set_volume(new_volume)
            await self._save_current_state()
            await self._publish_status()
        except Exception as exc:
            logger.error("handle_volume_up_failed", error=str(exc))
            await self._publish_error("volume_error", str(exc))

    async def _handle_volume_down(self, command: VolumeStepCommand) -> None:
        """Handle volume down command."""
        try:
            current_volume = await self._vlc_backend.get_volume()
            new_volume = max(current_volume - command.step, 0)
            await self._vlc_backend.set_volume(new_volume)
            await self._save_current_state()
            await self._publish_status()
        except Exception as exc:
            logger.error("handle_volume_down_failed", error=str(exc))
            await self._publish_error("volume_error", str(exc))

    async def _handle_mute_toggle(self) -> None:
        """Toggle between muted and unmuted."""
        try:
            if self._muted:
                volume = min(
                    self._volume_before_mute,
                    self._get_audio_config().max_volume,
                )
                await self._vlc_backend.set_volume(volume)
                self._muted = False
                logger.debug("mute_toggle_unmuted", volume=volume)
            else:
                self._volume_before_mute = await self._vlc_backend.get_volume()
                await self._vlc_backend.set_volume(0)
                self._muted = True
                logger.debug("mute_toggle_muted", volume_before=self._volume_before_mute)
            await self._publish_status()
        except Exception as exc:
            logger.error("mute_toggle_failed", error=str(exc))
            await self._publish_error("volume_error", str(exc))

    async def _handle_config_update(self, new_config: AudioConfig) -> None:
        """Handle config update command."""
        try:
            self._config_manager.update_config(new_config)
            await self._publish_config_response(success=True)
            logger.debug("config_update_successful")
        except Exception as exc:
            logger.error("config_update_failed", error=str(exc))
            await self._publish_config_response(success=False, error=str(exc))

    async def _handle_config_reload(self) -> None:
        """Handle config reload command. Re-initializes VLC if output device changed."""
        try:
            old_config = self._config_manager.get_current_config()
            self._config_manager.reload_config()
            current = self._config_manager.get_current_config()
            if current is None:
                await self._publish_config_response(success=True)
                logger.debug("config_reload_successful")
                return

            device_changed = (
                old_config is None
                or old_config.output_device_type != current.output_device_type
                or old_config.output_device_name != current.output_device_name
            )
            if device_changed and self._vlc_backend._initialized:
                snapshot = await self._vlc_backend.reinitialize(current)
                if snapshot.get("source_uri") and snapshot.get("state") in (
                    PlaybackState.PLAYING.value,
                    PlaybackState.PAUSED.value,
                ):
                    self._vlc_backend.set_track_metadata(
                        track_id=snapshot.get("track_id"),
                        source_type=snapshot.get("source_type"),
                    )
                    await self._vlc_backend.play(
                        source_uri=snapshot["source_uri"],
                        start_position_ms=snapshot.get("position_ms", 0),
                    )
                    if snapshot.get("state") == PlaybackState.PAUSED.value:
                        await self._vlc_backend.pause()
            else:
                self._vlc_backend.update_config(current)
            await self._publish_config_response(success=True)
            logger.debug("config_reload_successful")
        except Exception as exc:
            logger.error("config_reload_failed", error=str(exc))
            await self._publish_config_response(success=False, error=str(exc))

    async def _handle_config_get(self) -> None:
        """Handle config get request."""
        try:
            current = self._config_manager.get_current_config()
            if current:
                config_dict = current.model_dump()
            else:
                config_dict = self._config.audio.model_dump()
            topic = self._config.get_mqtt_topic("audio", "config/response")
            await self._mqtt_client.publish(topic, config_dict)
            logger.debug("config_get_response_sent")
        except Exception as exc:
            logger.error("config_get_failed", error=str(exc))

    async def _handle_switch_device(self, data: dict) -> None:
        """Handle switch-device command (MQTT)."""
        try:
            alsa_device = data.get("alsa_device")
            direction = data.get("direction")
            await self.switch_output_device(alsa_device=alsa_device, direction=direction)
            await self._publish_status()
        except ValueError as e:
            logger.warning("switch_device_invalid", error=str(e))
        except Exception as exc:
            logger.error("switch_device_failed", error=str(exc))
            await self._publish_error("switch_device_error", str(exc))

    # Public API for health checks

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        return time() - self._start_time

    def is_mqtt_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._mqtt_client.is_connected

    def is_vlc_initialized(self) -> bool:
        """Check if VLC backend is initialized."""
        return self._vlc_backend._initialized

    async def get_audio_status(self) -> AudioStatus:
        """Get current audio status."""
        return await self._vlc_backend.get_status()

    async def get_audio_devices(self, enabled_only: bool = False) -> list[dict]:
        """Get detected Pulse sinks, optionally filtered by enabled_output_devices."""
        from .pulse_detector import PulseSinkDetector

        detector = PulseSinkDetector()
        sinks = await detector.detect_sinks()
        config = self._get_audio_config()
        enabled = getattr(config, "enabled_output_devices", None) or []
        display_names = getattr(config, "device_display_names", None) or {}
        if enabled_only and enabled:
            allowed = set(enabled)
            sinks = [s for s in sinks if s.sink_name in allowed]
        out = []
        seen_base_names: set[str] = set()
        for s in sinks:
            base_name = display_names.get(s.sink_name) or s.name
            if base_name in seen_base_names:
                name = f"{base_name} ({s.sink_name})"
            else:
                name = base_name
                seen_base_names.add(base_name)
            out.append({
                "id": s.sink_name,
                "name": name,
                "card_name": s.description,
                "alsa_device": s.sink_name,
                "priority": s.priority,
            })
        return out

    async def switch_output_device(
        self,
        alsa_device: str | None = None,
        direction: str | None = None,
    ) -> AudioStatus:
        """Switch output device, re-init VLC, optionally resume. Returns new status."""
        config = self._get_audio_config()
        enabled_list = getattr(config, "enabled_output_devices", None) or []
        devices = await self.get_audio_devices(enabled_only=bool(enabled_list))
        if not devices:
            raise ValueError("No audio devices available")

        if direction == "next":
            current = config.output_device_name
            idx = next((i for i, d in enumerate(devices) if d["alsa_device"] == current), -1)
            next_idx = (idx + 1) % len(devices)
            target = devices[next_idx]["alsa_device"]
        elif alsa_device:
            allowed = {d["alsa_device"] for d in devices}
            if alsa_device not in allowed:
                raise ValueError(f"Device not available or not enabled: {alsa_device!r}")
            target = alsa_device
        else:
            raise ValueError("Provide alsa_device or direction='next'")

        new_config = config.model_copy(update={
            "output_device_type": OutputDeviceType.PULSEAUDIO,
            "output_device_name": target,
        })
        self._config_manager.update_config(new_config)
        snapshot = await self._vlc_backend.reinitialize(new_config)
        if snapshot.get("source_uri") and snapshot.get("state") in (
            PlaybackState.PLAYING.value,
            PlaybackState.PAUSED.value,
        ):
            self._vlc_backend.set_track_metadata(
                track_id=snapshot.get("track_id"),
                source_type=snapshot.get("source_type"),
            )
            await self._vlc_backend.play(
                source_uri=snapshot["source_uri"],
                start_position_ms=snapshot.get("position_ms", 0),
            )
            if snapshot.get("state") == PlaybackState.PAUSED.value:
                await self._vlc_backend.pause()
        return await self._vlc_backend.get_status()
