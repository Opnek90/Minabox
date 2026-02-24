"""VLC-based audio backend implementation.

Uses python-vlc to provide audio playback functionality.
"""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import structlog
import vlc

from .audio_backend import AudioBackend, AudioStatus, PlaybackState
from .config_schema import AudioConfig, OutputDeviceType
from .exceptions import (
    FileNotFoundError,
    PlaybackError,
    StreamUnreachableError,
    VLCError,
)

logger = structlog.get_logger(__name__)

# #region agent log
DEBUG_LOG_PATH = Path("/cursor-debug/debug-eb9057.log")


def _agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        payload = {"sessionId": "eb9057", "timestamp": int(time.time() * 1000), "location": location, "message": message, "data": data, "hypothesisId": hypothesis_id}
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


class VLCBackend(AudioBackend):
    """VLC-based audio backend implementation.

    Uses libVLC through python-vlc bindings for robust audio playback.
    Supports both local files and HTTP/HTTPS streams.
    """

    def __init__(self, config: AudioConfig) -> None:
        """Initialize VLC backend.

        Args:
            config: Audio configuration
        """
        self._config = config
        self._instance: vlc.Instance | None = None
        self._player: vlc.MediaPlayer | None = None
        self._initialized = False
        self._pending_volume: int | None = None  # desired volume when VLC has no media (returns -1)
        self._current_track_id: str | None = None
        self._current_source_type: str | None = None
        self._current_source_uri: str | None = None

    def update_config(self, config: AudioConfig) -> None:
        """Update audio config at runtime (e.g. after hot-reload). Only the config reference is updated; VLC stays initialized."""
        self._config = config

    async def reinitialize(self, config: AudioConfig) -> dict:
        """Shutdown VLC, apply new config, and re-initialize (for device switch). Returns state to resume: {source_uri, position_ms, state}."""
        snapshot = {}
        if self._initialized and self._player is not None:
            try:
                status = await self.get_status()
                snapshot = {
                    "source_uri": status.source_uri,
                    "position_ms": status.position_ms or 0,
                    "state": status.state.value,
                    "track_id": status.track_id,
                    "source_type": status.source_type,
                }
            except Exception as e:
                logger.warning("reinitialize_status_snapshot_failed", error=str(e))
        await self.shutdown()
        self._config = config
        await self.initialize()
        return snapshot

    async def initialize(self) -> None:
        """Initialize VLC instance and media player.

        Raises:
            VLCError: If VLC initialization fails
            OutputDeviceError: If audio output device is unavailable
        """
        logger.info("vlc_backend_initializing")

        try:
            # AUTO: Use Pulse when PULSE_SERVER is set; otherwise default
            if self._config.output_device_type == OutputDeviceType.AUTO:
                pulse_server = os.environ.get("PULSE_SERVER")
                if pulse_server:
                    logger.info(
                        "audio_device_using_pulseaudio",
                        pulse_server=pulse_server,
                    )
                    self._config.output_device_type = OutputDeviceType.PULSEAUDIO
                    if not (self._config.output_device_name and self._config.output_device_name.strip()):
                        self._config.output_device_name = ""
                else:
                    logger.info("audio_device_no_pulse_using_default")
                    self._config.output_device_type = OutputDeviceType.DEFAULT
                    self._config.output_device_name = "default"

            # VLC pulse module has no device option; set Pulse default sink so VLC uses it
            if (
                self._config.output_device_type == OutputDeviceType.PULSEAUDIO
                and self._config.output_device_name
                and self._config.output_device_name.strip()
            ):
                self._set_pulse_default_sink(self._config.output_device_name.strip())

            # Create VLC instance with audio output configuration
            vlc_args = self._build_vlc_args()
            self._instance = vlc.Instance(vlc_args)

            if self._instance is None:
                raise VLCError("Failed to create VLC instance")

            # Create media player
            self._player = self._instance.media_player_new()

            if self._player is None:
                raise VLCError("Failed to create VLC media player")

            # FIXED: Safe initial volume calculation
            # VLC returns -1 for audio_get_volume() without media
            initial_volume = getattr(self._config, "default_volume", 40)
            if initial_volume is None:
                initial_volume = 40
            initial_volume = min(initial_volume, self._config.max_volume)
            initial_volume = max(initial_volume, 0)  # Clamp to valid VLC range (0-100)

            logger.debug("setting_initial_volume", volume=initial_volume)

            # Set initial volume with error handling
            # Note: VLC may return -1 if no audio output is ready yet
            result = self._player.audio_set_volume(initial_volume)
            if result == -1:
                logger.warning(
                    "initial_volume_set_returned_error",
                    requested=initial_volume,
                    vlc_result=result,
                )
                # Don't fail initialization - this is normal without loaded media
            else:
                logger.debug("initial_volume_set_success", volume=initial_volume)

            self._initialized = True

            logger.info(
                "vlc_backend_initialized",
                output_device=self._config.output_device_name,
                initial_volume=initial_volume,
            )

        except Exception as e:
            logger.error("vlc_backend_initialization_failed", error=str(e))
            raise VLCError(f"VLC backend initialization failed: {e}") from e

    def _build_vlc_args(self) -> list[str]:
        """Build VLC instance arguments based on configuration.

        Returns:
            List of VLC command-line arguments
        """
        args = [
            "--quiet",  # Suppress VLC console output
            "--no-video",  # Audio only
        ]

        # Configure audio output: Pulse only (ALSA removed). VLC pulse module has no device
        # option; default sink is set via pactl before creating the instance.
        if self._config.output_device_type == OutputDeviceType.PULSEAUDIO:
            args.append("--aout=pulse")
        # DEFAULT uses VLC's auto-detection

        return args

    def _set_pulse_default_sink(self, sink_name: str) -> None:
        """Set Pulse default sink so VLC (--aout=pulse) uses the configured device."""
        if not os.environ.get("PULSE_SERVER"):
            return
        try:
            result = subprocess.run(
                ["pactl", "set-default-sink", sink_name],
                capture_output=True,
                text=True,
                timeout=5,
                env=os.environ.copy(),
            )
            if result.returncode == 0:
                logger.info("pulse_default_sink_set", sink=sink_name)
            else:
                logger.warning(
                    "pulse_set_default_sink_failed",
                    sink=sink_name,
                    stderr=(result.stderr or "").strip() or None,
                )
        except FileNotFoundError:
            logger.warning("pulse_set_default_sink_pactl_not_found")
        except subprocess.TimeoutExpired:
            logger.warning("pulse_set_default_sink_timeout", sink=sink_name)
        except Exception as e:
            logger.warning("pulse_set_default_sink_error", sink=sink_name, error=str(e))

    async def shutdown(self) -> None:
        """Shutdown VLC backend gracefully."""
        logger.info("vlc_backend_shutting_down")

        try:
            if self._player is not None:
                self._player.stop()
                self._player.release()
                self._player = None

            if self._instance is not None:
                self._instance.release()
                self._instance = None

            self._initialized = False
            logger.info("vlc_backend_shutdown_complete")

        except Exception as e:
            logger.warning("vlc_backend_shutdown_error", error=str(e))

    async def play(
        self,
        source_uri: str,
        start_position_ms: int = 0,
    ) -> None:
        """Start playing audio from source.

        Args:
            source_uri: Path or URL to audio source
            start_position_ms: Start position in milliseconds

        Raises:
            PlaybackError: If playback fails
            FileNotFoundError: If source file doesn't exist
            StreamUnreachableError: If stream is unreachable
        """
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        logger.info(
            "play_started",
            source_uri=source_uri,
            start_position_ms=start_position_ms,
        )

        try:
            # Validate source
            await self._validate_source(source_uri)

            # Reset player when transitioning from Ended/Stopped to new media (e.g. next track in playlist).
            # Without this, VLC may not transition to Playing when loading new media after a track has ended.
            try:
                self._player.stop()
                await self._wait_for_state(vlc.State.Stopped, timeout_sec=1.5)
            except (PlaybackError, Exception):
                await asyncio.sleep(0.2)

            # Create media
            media = self._instance.media_new(source_uri)
            if media is None:
                raise PlaybackError(f"Failed to create media from {source_uri}")

            # Set media to player
            self._player.set_media(media)

            # Start playback
            result = self._player.play()
            if result == -1:
                raise PlaybackError("VLC player.play() returned error")

            # Streams need longer to connect and buffer than local files
            is_stream = source_uri.startswith(("http://", "https://", "rtsp://", "rtmp://"))
            timeout_sec = 15.0 if is_stream else 5.0
            try:
                await self._wait_for_state(vlc.State.Playing, timeout_sec=timeout_sec)
            except PlaybackError as e:
                if "Timeout" in str(e) and self._player.get_state() == vlc.State.Stopped:
                    logger.warning("play_first_attempt_timeout_retrying", source_uri=source_uri)
                    self._player.stop()
                    await asyncio.sleep(1.0)
                    result = self._player.play()
                    if result == -1:
                        raise PlaybackError("VLC player.play() returned error on retry") from e
                    await self._wait_for_state(vlc.State.Playing, timeout_sec=timeout_sec)
                else:
                    raise

            # Apply pending volume (set while no media was loaded)
            if self._pending_volume is not None:
                applied = min(self._pending_volume, self._config.max_volume)
                applied = max(applied, 0)
                if self._player.audio_set_volume(applied) != -1:
                    self._pending_volume = None
                else:
                    self._pending_volume = applied

            # Set start position if specified
            if start_position_ms > 0:
                await asyncio.sleep(0.2)  # Brief delay for VLC to load media
                self._player.set_time(start_position_ms)

            self._current_source_uri = source_uri

            logger.info("play_successful", source_uri=source_uri)

        except (FileNotFoundError, StreamUnreachableError):
            raise
        except Exception as e:
            logger.error("play_failed", source_uri=source_uri, error=str(e))
            raise PlaybackError(f"Playback failed: {e}") from e

    async def _validate_source(self, source_uri: str) -> None:
        """Validate audio source exists or is a known remote/stream scheme.

        Local files are checked with Path.exists(). HTTP(S) and remote schemes
        (smb, nfs, dlna, etc.) are passed through to VLC without existence check.
        """
        # Remote/stream schemes: no local path check (VLC handles them)
        if source_uri.startswith(
            ("http://", "https://", "smb://", "nfs://", "dlna://", "ftp://")
        ):
            return
        # Local file: must exist
        path = Path(source_uri)
        # #region agent log
        exists = path.exists()
        is_file = path.is_file() if exists else None
        stat_info = {}
        try:
            s = path.stat()
            stat_info = {"mode_oct": oct(s.st_mode), "uid": s.st_uid, "gid": s.st_gid}
        except OSError as e:
            stat_info = {"errno": e.errno, "strerror": str(e)}
        _agent_log(
            "vlc_backend.py:_validate_source",
            "path check before exists",
            {"source_uri": source_uri, "path_str": str(path), "exists": exists, "is_file": is_file, "stat": stat_info, "cwd": str(Path.cwd()), "process_uid": os.getuid(), "process_gid": os.getgid()},
            "H1_H2_H3_H4",
        )
        # #endregion
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {source_uri}")

    async def _wait_for_state(
        self,
        expected_state: vlc.State,
        timeout_sec: float = 5.0,
    ) -> None:
        """Wait for VLC player to reach expected state.

        Args:
            expected_state: Expected VLC state
            timeout_sec: Maximum time to wait

        Raises:
            PlaybackError: If timeout occurs
        """
        elapsed = 0.0
        interval = 0.1

        while elapsed < timeout_sec:
            if self._player.get_state() == expected_state:
                return
            await asyncio.sleep(interval)
            elapsed += interval

        raise PlaybackError(
            f"Timeout waiting for state {expected_state}, "
            f"current state: {self._player.get_state()}"
        )

    async def pause(self) -> None:
        """Pause current playback."""
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        logger.info("pause_requested")

        try:
            self._player.pause()
            logger.info("pause_successful")
        except Exception as e:
            logger.error("pause_failed", error=str(e))
            raise PlaybackError(f"Pause failed: {e}") from e

    async def resume(self) -> None:
        """Resume paused playback."""
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        logger.info("resume_requested")

        try:
            if self._player.get_state() == vlc.State.Paused:
                self._player.play()
                logger.info("resume_successful")
            else:
                logger.warning("resume_ignored_not_paused")
        except Exception as e:
            logger.error("resume_failed", error=str(e))
            raise PlaybackError(f"Resume failed: {e}") from e

    async def stop(self) -> None:
        """Stop current playback."""
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        logger.info("stop_requested")

        try:
            self._player.stop()
            self._current_source_uri = None
            logger.info("stop_successful")
        except Exception as e:
            logger.error("stop_failed", error=str(e))
            raise PlaybackError(f"Stop failed: {e}") from e

    async def set_volume(self, volume: int) -> None:
        """Set playback volume.

        Args:
            volume: Volume level (0-100), clamped to max_volume
        """
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        # Clamp to max_volume for child protection
        clamped_volume = min(volume, self._config.max_volume)
        clamped_volume = max(clamped_volume, 0)  # Ensure valid range

        logger.debug(
            "volume_set_requested",
            requested=volume,
            clamped=clamped_volume,
        )

        try:
            result = self._player.audio_set_volume(clamped_volume)
            if result == -1:
                # VLC often returns -1 when no media is loaded; store desired volume and apply on next play
                self._pending_volume = clamped_volume
                logger.debug(
                    "volume_set_deferred_no_media",
                    volume=clamped_volume,
                )
                return
            self._pending_volume = None
            logger.debug("volume_set_successful", volume=clamped_volume)
        except Exception as e:
            logger.error("volume_set_failed", error=str(e))
            raise PlaybackError(f"Set volume failed: {e}") from e

    async def get_volume(self) -> int:
        """Get current volume level."""
        if not self._initialized or self._player is None:
            return 0

        try:
            vol = self._player.audio_get_volume()
            # VLC returns -1 if no media loaded or error; use pending volume so UI/state stay consistent
            if vol >= 0:
                return vol
            return self._pending_volume if self._pending_volume is not None else 0
        except Exception as e:
            logger.warning("get_volume_failed", error=str(e))
            return 0

    async def get_position(self) -> int:
        """Get current playback position in milliseconds."""
        if not self._initialized or self._player is None:
            return 0

        try:
            return self._player.get_time()
        except Exception as e:
            logger.warning("get_position_failed", error=str(e))
            return 0

    async def get_duration(self) -> int | None:
        """Get total duration in milliseconds."""
        if not self._initialized or self._player is None:
            return None

        try:
            duration = self._player.get_length()
            return duration if duration > 0 else None
        except Exception as e:
            logger.warning("get_duration_failed", error=str(e))
            return None

    async def get_state(self) -> PlaybackState:
        """Get current playback state."""
        if not self._initialized or self._player is None:
            return PlaybackState.STOPPED

        try:
            vlc_state = self._player.get_state()

            if vlc_state == vlc.State.Playing:
                return PlaybackState.PLAYING
            elif vlc_state == vlc.State.Paused:
                return PlaybackState.PAUSED
            elif vlc_state in (vlc.State.Error, vlc.State.Ended):
                return (
                    PlaybackState.ERROR
                    if vlc_state == vlc.State.Error
                    else PlaybackState.STOPPED
                )
            else:
                return PlaybackState.STOPPED

        except Exception as e:
            logger.warning("get_state_failed", error=str(e))
            return PlaybackState.ERROR

    async def get_status(self) -> AudioStatus:
        """Get complete audio status."""
        state = await self.get_state()
        position = await self.get_position()
        duration = await self.get_duration()
        volume = await self.get_volume()

        return AudioStatus(
            state=state,
            track_id=self._current_track_id,
            source_type=self._current_source_type,
            source_uri=self._current_source_uri,
            position_ms=position,
            duration_ms=duration,
            volume=volume,
        )

    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        if not self._initialized or self._player is None:
            return False

        try:
            return self._player.get_state() == vlc.State.Playing
        except Exception:
            return False

    def set_track_metadata(
        self,
        track_id: str | None = None,
        source_type: str | None = None,
    ) -> None:
        """Set metadata for current track (for status reporting).

        Args:
            track_id: Track ID from backend
            source_type: Source type ("file" or "stream")
        """
        self._current_track_id = track_id
        self._current_source_type = source_type
