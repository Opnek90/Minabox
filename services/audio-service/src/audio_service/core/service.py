"""Audio Service orchestration.

Coordinates between MQTT, VLC backend, and state management.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import Any

import structlog

from ..config_manager import ConfigManager
from ..config_schema import AppConfig, AudioConfig, OutputDeviceType
from ..infrastructure.audio_backend import AudioStatus, PlaybackState
from ..infrastructure.mqtt_client import MQTTClient
from ..infrastructure.vlc_backend import VLCBackend
from .mqtt_handler import (
    MQTTMessageHandler,
    PlayCommand,
    VolumeCommand,
    VolumeStepCommand,
)
from .state_manager import StateManager

logger = structlog.get_logger(__name__)


# #region agent log
def _agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        log_path = Path("/cursor-debug/debug-bd7bd2.log") if Path("/cursor-debug").exists() else Path("/home/pi/minabox/.cursor/debug-bd7bd2.log")
        payload = {"sessionId": "bd7bd2", "timestamp": int(time() * 1000), "location": location, "message": message, "data": data, "hypothesisId": hypothesis_id}
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


def _status_fingerprint(
    status: AudioStatus,
    muted: bool,
    multiple_output_devices: bool,
    bluetooth_sink_available: bool,
) -> tuple[Any, ...]:
    """Return a tuple of the fields that matter for LED / UI state changes.

    Intentionally excludes position_ms and timestamp so a playing track
    does not trigger a publish every 2 seconds.
    """
    return (
        status.state,
        status.track_id,
        status.source_uri,
        status.volume,
        muted,
        multiple_output_devices,
        bluetooth_sink_available,
    )


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
        self._vlc_backend = VLCBackend(config.audio)
        self._state_manager = StateManager(Path(config.env.audio_state_path))

        # Instantiate once to avoid repeated OS calls (PulseAudio/PipeWire sink
        # enumeration) on every 2-second status-loop tick.
        from ..infrastructure.pulse_detector import PulseSinkDetector
        self._pulse_detector = PulseSinkDetector()

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

        # Playback command lock (issue #61)
        # Prevents race conditions when multiple play/stop/pause commands arrive
        # simultaneously (e.g., rapid button presses by children)
        self._playback_lock = asyncio.Lock()
        self._current_playback_task: asyncio.Task | None = None

        # Last-published fingerprint for change detection in the periodic loop
        self._last_published_fingerprint: tuple[Any, ...] | None = None

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
            self._state_manager.load()

            await self._vlc_backend.initialize()

            audio_cfg = self._get_audio_config()
            min_vol = getattr(audio_cfg, "min_volume", 0)
            state = self._state_manager.get_state()
            if state.last_volume > 0:
                initial_volume = min(state.last_volume, audio_cfg.max_volume)
            else:
                initial_volume = min(
                    audio_cfg.default_volume,
                    audio_cfg.max_volume,
                )
            initial_volume = max(initial_volume, min_vol)
            _agent_log(
                "service.py:start",
                "initial_volume",
                {"initial_volume": initial_volume, "state_last_volume": state.last_volume, "max_volume": audio_cfg.max_volume, "min_volume": min_vol},
                "B",
            )
            logger.debug("setting_service_initial_volume", volume=initial_volume)
            await self._vlc_backend.set_volume(initial_volume)

            await self._mqtt_client.connect()
            await self._subscribe_to_topics()
            self._mqtt_client._on_message = self._mqtt_handler.handle_message

            self._running = True
            self._status_publish_task = asyncio.create_task(self._status_publish_loop())
            self._mqtt_task = asyncio.create_task(self._mqtt_client.run())

            await self._publish_system_event("service-started")

        except Exception as exc:
            logger.error("audio_service_start_failed", error=str(exc))
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Shutdown the audio service gracefully."""
        logger.info("audio_service_shutting_down")

        self._running = False

        # Cancel any ongoing playback operation
        if self._current_playback_task and not self._current_playback_task.done():
            self._current_playback_task.cancel()
            try:
                await self._current_playback_task
            except asyncio.CancelledError:
                pass

        if self._status_publish_task is not None:
            self._status_publish_task.cancel()
            try:
                await self._status_publish_task
            except asyncio.CancelledError:
                pass

        await self._mqtt_client.stop()
        if self._mqtt_task is not None:
            try:
                await asyncio.wait_for(self._mqtt_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        try:
            # Report position to backend BEFORE stopping VLC so we still
            # have an accurate position_ms from the running playback.
            await self._report_position_to_backend()
        except Exception as exc:
            logger.warning("shutdown_report_position_failed", error=str(exc))

        try:
            await self._vlc_backend.stop()
        except Exception as exc:
            logger.warning("shutdown_stop_failed", error=str(exc))

        try:
            await self._save_current_state()
        except Exception as exc:
            logger.warning("shutdown_save_state_failed", error=str(exc))

        try:
            await self._publish_system_event("service-stopped")
        except Exception as exc:
            logger.warning("shutdown_publish_failed", error=str(exc))

        await self._mqtt_client.disconnect()
        await self._vlc_backend.shutdown()

        logger.info("audio_service_shutdown_complete")

    async def _subscribe_to_topics(self) -> None:
        """Subscribe to all required MQTT topics.

        Uses self._config.get_mqtt_topic() consistently instead of building
        f-strings manually (issue #33).
        """
        topics = [
            self._config.get_mqtt_topic("audio", "play"),
            self._config.get_mqtt_topic("audio", "pause"),
            self._config.get_mqtt_topic("audio", "stop"),
            self._config.get_mqtt_topic("audio", "next"),
            self._config.get_mqtt_topic("audio", "prev"),
            self._config.get_mqtt_topic("audio", "set-volume"),
            self._config.get_mqtt_topic("audio", "volume-up"),
            self._config.get_mqtt_topic("audio", "volume-down"),
            self._config.get_mqtt_topic("audio", "mute-toggle"),
            self._config.get_mqtt_topic("audio", "config/update"),
            self._config.get_mqtt_topic("audio", "config/reload"),
            self._config.get_mqtt_topic("audio", "config/get"),
            self._config.get_mqtt_topic("audio", "switch-device"),
            self._config.get_mqtt_topic("config", "general"),
        ]

        for topic in topics:
            await self._mqtt_client.subscribe(topic)

    async def _status_publish_loop(self) -> None:
        """Periodically publish audio status to MQTT - only on state changes."""
        while self._running:
            try:
                await asyncio.sleep(2.0)
                await self._publish_status(force=False)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("status_publish_loop_error", error=str(exc))

    async def _publish_status(self, *, force: bool = True) -> None:
        """Publish current audio status to MQTT."""
        try:
            status = await self._vlc_backend.get_status()

            multiple_output_devices = False
            bluetooth_sink_available = False
            try:
                config = self._get_audio_config()
                enabled_list = getattr(config, "enabled_output_devices", None) or []
                devices = await self.get_audio_devices(enabled_only=bool(enabled_list))
                multiple_output_devices = len(devices) >= 2
                bluetooth_sink_available = any(
                    (d.get("alsa_device") or "").startswith("bluez_") for d in devices
                )
            except Exception as exc:
                logger.warning("audio_status_devices_failed", error=str(exc))

            fingerprint = _status_fingerprint(
                status, self._muted, multiple_output_devices, bluetooth_sink_available
            )

            if not force and fingerprint == self._last_published_fingerprint:
                logger.debug("audio_status_unchanged_skipping_publish")
                return

            payload = {
                "state": status.state.value,
                "track_id": status.track_id,
                "source_type": status.source_type,
                "source_uri": status.source_uri,
                "position_ms": status.position_ms,
                "duration_ms": status.duration_ms,
                "volume": status.volume,
                "muted": self._muted,
                "multiple_output_devices": multiple_output_devices,
                "bluetooth_sink_available": bluetooth_sink_available,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            topic = self._config.get_mqtt_topic("audio", "status")
            await self._mqtt_client.publish(topic, payload, retain=True)
            self._last_published_fingerprint = fingerprint

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

    async def _report_position_to_backend(self) -> None:
        """Publish current playback position to backend-service via MQTT.

        Called on stop, pause, and graceful shutdown so the backend can
        persist the resume position in SQLite (Issue #51).
        Skipped silently for live streams (source_type == 'stream').
        """
        status = await self._vlc_backend.get_status()
        if not status.source_uri or status.source_type == "stream":
            return
        if status.position_ms <= 0:
            return
        payload = {
            "source_uri": status.source_uri,
            "source_type": status.source_type,
            "position_ms": status.position_ms,
            "duration_ms": status.duration_ms,
        }
        topic = self._config.get_mqtt_topic("audio", "position-report")
        await self._mqtt_client.publish(topic, payload)
        logger.debug(
            "position_report_published",
            source_uri=status.source_uri,
            position_ms=status.position_ms,
        )

    async def _reinitialize_and_resume(self, config: AudioConfig) -> None:
        """Re-initialize VLC backend and resume playback from the last snapshot.

        Extracts the repeated reinitialize + conditional-resume pattern that
        previously appeared verbatim in both _handle_config_reload() and
        switch_output_device().
        """
        snapshot = await self._vlc_backend.reinitialize(config)
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

    # Command Handlers

    async def _handle_play(self, command: PlayCommand | None) -> None:
        """Handle play command with race condition protection.

        Fixes issue #61: Multiple rapid play commands (from button mashing) used to
        corrupt VLC's pipeline, causing "LED on, no sound" symptom. Now protected by
        a lock that cancels any in-progress play operation when a new one arrives.
        """
        # Cancel any currently running play operation
        if self._current_playback_task and not self._current_playback_task.done():
            logger.info("play_interrupted_cancelling_previous")
            self._current_playback_task.cancel()
            try:
                await self._current_playback_task
            except asyncio.CancelledError:
                pass

        # Create new play task with lock protection
        async def _execute_play():
            async with self._playback_lock:
                try:
                    _agent_log(
                        "service.py:_handle_play",
                        "play_handler_called",
                        {"has_command": command is not None, "source_uri": command.source_uri if command else None, "track_id": command.track_id if command else None},
                        "C_E",
                    )
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
                        current_status = await self._vlc_backend.get_status()
                        if current_status.state == PlaybackState.PAUSED:
                            await self._vlc_backend.resume()
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
                except asyncio.CancelledError:
                    logger.debug("play_cancelled_by_new_request")
                    raise
                except Exception as exc:
                    logger.error("handle_play_failed", error=str(exc))
                    await self._publish_error("playback_error", str(exc))

        self._current_playback_task = asyncio.create_task(_execute_play())
        try:
            await self._current_playback_task
        except asyncio.CancelledError:
            pass  # Expected when cancelled by new play request

    async def _handle_pause(self) -> None:
        """Handle pause command with race condition protection."""
        async with self._playback_lock:
            try:
                # Report position BEFORE pausing so VLC still has accurate position_ms
                await self._report_position_to_backend()
                await self._vlc_backend.pause()
                await self._save_current_state()
                await self._publish_status()
            except Exception as exc:
                logger.error("handle_pause_failed", error=str(exc))
                await self._publish_error("playback_error", str(exc))

    async def _handle_stop(self) -> None:
        """Handle stop command with race condition protection."""
        async with self._playback_lock:
            try:
                # Report position BEFORE stopping so VLC still has accurate position_ms
                await self._report_position_to_backend()
                await self._vlc_backend.stop()
                self._state_manager.clear()
                await self._publish_status()
            except Exception as exc:
                logger.error("handle_stop_failed", error=str(exc))
                await self._publish_error("playback_error", str(exc))

    async def _handle_next(self) -> None:
        """Handle next command (backend decides next track).

        This feature is not yet implemented. The subscription exists for
        future use. A warning is logged so the unimplemented state is
        visible in logs (issue #34).
        """
        logger.warning("next_command_not_implemented", hint="Feature pending, no action taken")

    async def _handle_prev(self) -> None:
        """Handle previous command (backend decides previous track).

        This feature is not yet implemented. The subscription exists for
        future use. A warning is logged so the unimplemented state is
        visible in logs (issue #34).
        """
        logger.warning("prev_command_not_implemented", hint="Feature pending, no action taken")

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
            min_vol = getattr(self._get_audio_config(), "min_volume", 0)
            new_volume = max(current_volume - command.step, min_vol)
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
                audio_cfg = self._get_audio_config()
                min_vol = getattr(audio_cfg, "min_volume", 0)
                volume = min(
                    self._volume_before_mute,
                    audio_cfg.max_volume,
                )
                volume = max(volume, min_vol)
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
            if device_changed and self._vlc_backend.is_initialized:
                await self._reinitialize_and_resume(current)
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
            sink_name = data.get("sink_name") or data.get("alsa_device")
            direction = data.get("direction")
            await self.switch_output_device(sink_name=sink_name, direction=direction)
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
        """Check if VLC backend is initialized via public property (issue #35)."""
        return self._vlc_backend.is_initialized

    async def get_audio_status(self) -> AudioStatus:
        """Get current audio status."""
        return await self._vlc_backend.get_status()

    async def get_audio_devices(self, enabled_only: bool = False) -> list[dict]:
        """Get detected Pulse sinks, optionally filtered by enabled_output_devices."""
        sinks = await self._pulse_detector.detect_sinks()
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
        sink_name: str | None = None,
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
        elif sink_name:
            allowed = {d["alsa_device"] for d in devices}
            if sink_name not in allowed:
                raise ValueError(f"Device not available or not enabled: {sink_name!r}")
            target = sink_name
        else:
            raise ValueError("Provide sink_name or direction='next'")

        new_config = config.model_copy(update={
            "output_device_type": OutputDeviceType.PULSEAUDIO,
            "output_device_name": target,
        })
        self._config_manager.update_config(new_config)
        await self._reinitialize_and_resume(new_config)
        return await self._vlc_backend.get_status()
