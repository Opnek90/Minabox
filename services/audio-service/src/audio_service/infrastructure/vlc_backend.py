"""VLC-based audio backend implementation.

Uses python-vlc to provide audio playback functionality.
"""

import asyncio
import os
import subprocess
from pathlib import Path

import structlog
import vlc

from .audio_backend import AudioBackend, AudioStatus, PlaybackState
from ..config_schema import AudioConfig, OutputDeviceType
from ..exceptions import (
    FileNotFoundError,
    PlaybackError,
    VLCError,
)

logger = structlog.get_logger(__name__)


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
        self._pending_volume: int | None = None
        self._current_track_id: str | None = None
        self._current_source_type: str | None = None
        self._current_source_uri: str | None = None

    @property
    def is_initialized(self) -> bool:
        """Returns True if the VLC backend has been successfully initialized (issue #35)."""
        return self._initialized

    def update_config(self, config: AudioConfig) -> None:
        """Update audio config at runtime."""
        self._config = config

    async def reinitialize(self, config: AudioConfig) -> dict:
        """Shutdown VLC, apply new config, and re-initialize."""
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

        Also disables PulseAudio suspend-on-idle and pre-warms the ALSA
        pipeline so that the very first play() is stutter-free (issue #65).
        """
        logger.debug("vlc_backend_initializing")

        try:
            pulse_server = os.environ.get("PULSE_SERVER")
            if not pulse_server:
                logger.warning("pulse_server_not_set_vlc_may_fail")

            if self._config.output_device_type != OutputDeviceType.PULSEAUDIO:
                logger.warning(
                    "coercing_output_device_type_to_pulseaudio",
                    previous=str(self._config.output_device_type),
                )
                self._config.output_device_type = OutputDeviceType.PULSEAUDIO

            sink_name = (self._config.output_device_name or "").strip()
            if sink_name:
                self._set_pulse_default_sink(sink_name)

            vlc_args = self._build_vlc_args()
            self._instance = vlc.Instance(vlc_args)

            if self._instance is None:
                raise VLCError("Failed to create VLC instance")

            self._player = self._instance.media_player_new()

            if self._player is None:
                raise VLCError("Failed to create VLC media player")

            initial_volume = getattr(self._config, "default_volume", 40)
            if initial_volume is None:
                initial_volume = 40
            initial_volume = min(initial_volume, self._config.max_volume)
            initial_volume = max(initial_volume, 0)

            logger.debug("setting_initial_volume", volume=initial_volume)
            result = self._player.audio_set_volume(initial_volume)
            if result == -1:
                logger.warning("initial_volume_set_returned_error", requested=initial_volume)
            else:
                logger.debug("initial_volume_set_success", volume=initial_volume)

            self._initialized = True

        except Exception as e:
            logger.error("vlc_backend_initialization_failed", error=str(e))
            raise VLCError(f"VLC backend initialization failed: {e}") from e

        # --- Audio pipeline setup (non-fatal: service continues if these fail) ---

        # 1. Disable PulseAudio suspend-on-idle so the ALSA device is never
        #    closed between plays (cold-start stutter fix, issue #65).
        await self._disable_pulse_suspend_on_idle()

        # 2. Pre-warm the pipeline with 500 ms of silence so ALSA hardware
        #    buffers are allocated before the first real play() call.
        await self._prewarm_audio_pipeline()

    def _build_vlc_args(self) -> list[str]:
        return [
            "--quiet",
            "--no-video",
            "--aout=pulse",
        ]

    def _set_pulse_default_sink(self, sink_name: str) -> bool:
        """Set Pulse default sink so VLC uses the configured device."""
        if not os.environ.get("PULSE_SERVER"):
            return False
        try:
            subprocess.run(["pactl", "suspend-sink", sink_name, "0"], capture_output=True, timeout=5)

            if "platform-soc_sound" in sink_name or "soc_sound" in sink_name:
                self._unmute_alsa_for_sink(sink_name)

            result = subprocess.run(
                ["pactl", "set-default-sink", sink_name],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("pulse_set_default_sink_error", sink=sink_name, error=str(e))
            return False

    def _unmute_alsa_for_sink(self, sink_name: str) -> None:
        for card in ("0", "1"):
            for control in ("Master", "Speaker", "PCM"):
                try:
                    subprocess.run(
                        ["amixer", "-c", card, "sset", control, "unmute"],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass

    async def _disable_pulse_suspend_on_idle(self) -> None:
        """Unload module-suspend-on-idle from the host PulseAudio daemon.

        module-suspend-on-idle closes the ALSA device after ~5 s of silence.
        When the device is closed, the next player.play() writes audio before
        ALSA has finished re-opening (~100–300 ms) — causing the cold-start
        stutter.  Unloading the module keeps the ALSA device permanently open.

        Note: PULSE_PROP_module-suspend-on-idle.timeout=0 in docker-compose.yml
        is a client stream property and does NOT affect the server-side module.
        """
        if not os.environ.get("PULSE_SERVER"):
            return
        try:
            result = subprocess.run(
                ["pactl", "unload-module", "module-suspend-on-idle"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info("pulse_suspend_on_idle_disabled")
            else:
                logger.debug(
                    "pulse_suspend_on_idle_unload_skipped",
                    hint="module may not be loaded or already unloaded",
                    stderr=result.stderr.strip(),
                )
        except Exception as e:
            logger.warning("pulse_suspend_on_idle_error", error=str(e))

    async def _prewarm_audio_pipeline(self) -> None:
        """Write 500 ms of silence via pacat to force ALSA hardware open.

        When the ALSA device is cold (never opened, or just re-opened after
        suspend), hardware buffer allocation takes ~100–300 ms.  Writing silence
        once at service start lets that allocation complete before the first
        real play() call, so VLC always finds a ready sink.

        pacat (pulseaudio-utils) is installed in the Dockerfile.
        """
        if not os.environ.get("PULSE_SERVER"):
            return

        cmd = ["pacat", "--playback", "--rate=48000", "--channels=2", "--format=float32le"]
        sink_name = (self._config.output_device_name or "").strip()
        if sink_name:
            cmd += ["--device", sink_name]

        # 500 ms of silence: 48000 * 2 ch * 4 bytes * 0.5 s = 192 000 bytes
        silence = bytes(192_000)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                proc.stdin.write(silence)
                await proc.stdin.drain()
                proc.stdin.close()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except Exception:
                proc.kill()
                await proc.wait()
                raise
            logger.debug("audio_pipeline_prewarmed")
        except Exception as e:
            logger.warning("audio_pipeline_prewarm_failed", error=str(e))

    async def play(self, source_uri: str, start_position_ms: int = 0) -> None:
        """Play audio from source URI.

        Pipeline is always warm after initialize() (suspend-on-idle disabled +
        pacat pre-warm).  No cold-start handling needed here.
        """
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        try:
            await self._validate_source(source_uri)
            media = self._instance.media_new(source_uri)
            self._player.set_media(media)

            result = self._player.play()
            if result == -1:
                raise PlaybackError("VLC player.play() returned error")

            await self._wait_for_state(vlc.State.Playing)

            if self._pending_volume is not None:
                applied = min(max(self._pending_volume, 0), self._config.max_volume)
                self._player.audio_set_volume(applied)
                self._pending_volume = None

            if start_position_ms > 0:
                await asyncio.sleep(0.2)
                self._player.set_time(start_position_ms)

            self._current_source_uri = source_uri
        except Exception as e:
            raise PlaybackError(f"Playback failed: {e}")

    async def _validate_source(self, source_uri: str) -> None:
        if source_uri.startswith(("http://", "https://")):
            return
        if not Path(source_uri).exists():
            raise FileNotFoundError(f"Audio file not found: {source_uri}")

    async def _wait_for_state(self, expected_state: vlc.State, timeout_sec: float = 5.0) -> None:
        elapsed = 0.0
        while elapsed < timeout_sec:
            if self._player.get_state() == expected_state:
                return
            await asyncio.sleep(0.1)
            elapsed += 0.1
        raise PlaybackError(f"Timeout waiting for {expected_state}")

    async def pause(self) -> None:
        """Pause playback and wait for state transition.

        Fixes issue #65: VLC's pause() is asynchronous and takes ~1s to complete.
        Waiting for State.Paused prevents race conditions where resume() is called
        before the pause has fully taken effect.
        """
        if not self._player:
            return

        self._player.pause()

        try:
            await self._wait_for_state(vlc.State.Paused, timeout_sec=2.0)
        except PlaybackError:
            logger.warning("pause_state_transition_timeout")

    async def resume(self) -> None:
        """Resume playback from pause.

        Fixes issue #65: VLC discards its audio buffer after ~5-10 seconds of pause.
        For short pauses, uses VLC's internal buffer (toggle-resume).
        For long pauses, detects buffer loss via position jump and does full re-play.
        """
        if not self._player:
            return

        current_state = self._player.get_state()
        if current_state != vlc.State.Paused:
            logger.warning("resume_called_but_not_paused", state=current_state)
            return

        saved_position = self._player.get_time()
        if saved_position < 0:
            saved_position = 0

        self._player.pause()  # Toggle: Paused → Playing

        await asyncio.sleep(0.3)

        current_position = self._player.get_time()
        if current_position < 0:
            current_position = 0

        position_jump = abs(current_position - saved_position)

        if position_jump > 100:
            logger.info(
                "resume_buffer_lost_replaying",
                saved_position=saved_position,
                current_position=current_position,
                jump_ms=position_jump,
            )

            self._player.stop()
            await asyncio.sleep(0.1)

            if self._current_source_uri:
                media = self._instance.media_new(self._current_source_uri)
                self._player.set_media(media)
                self._player.play()

                try:
                    await self._wait_for_state(vlc.State.Playing, timeout_sec=3.0)
                except PlaybackError as e:
                    logger.error("resume_replay_failed", error=str(e))
                    raise

                self._player.set_time(saved_position)
                logger.debug("resume_replay_success", position=saved_position)
            else:
                logger.error("resume_replay_no_source_uri")
                raise PlaybackError("Cannot resume: no source URI stored")
        else:
            logger.debug("resume_toggle_success", position_jump=position_jump)
            try:
                await self._wait_for_state(vlc.State.Playing, timeout_sec=2.0)
            except PlaybackError:
                logger.warning("resume_state_transition_timeout")

    async def stop(self) -> None:
        if self._player:
            self._player.stop()
            self._current_source_uri = None
        # module-suspend-on-idle is disabled, so PulseAudio keeps the ALSA
        # sink open after stop() — no cold-start handling needed on next play().

    async def set_volume(self, volume: int) -> None:
        if not self._player: return
        clamped = min(max(volume, 0), self._config.max_volume)
        if self._player.audio_set_volume(clamped) == -1:
            self._pending_volume = clamped
        else:
            self._pending_volume = None

    async def get_volume(self) -> int:
        if not self._player: return 0
        vol = self._player.audio_get_volume()
        return vol if vol >= 0 else (self._pending_volume or 0)

    async def get_position(self) -> int:
        return self._player.get_time() if self._player else 0

    async def get_duration(self) -> int | None:
        if not self._player: return None
        d = self._player.get_length()
        return d if d > 0 else None

    async def get_state(self) -> PlaybackState:
        if not self._player: return PlaybackState.STOPPED
        v = self._player.get_state()
        if v == vlc.State.Playing: return PlaybackState.PLAYING
        if v == vlc.State.Paused: return PlaybackState.PAUSED
        if v == vlc.State.Error: return PlaybackState.ERROR
        return PlaybackState.STOPPED

    async def get_status(self) -> AudioStatus:
        return AudioStatus(
            state=await self.get_state(),
            track_id=self._current_track_id,
            source_type=self._current_source_type,
            source_uri=self._current_source_uri,
            position_ms=await self.get_position(),
            duration_ms=await self.get_duration(),
            volume=await self.get_volume(),
        )

    async def shutdown(self) -> None:
        if self._player:
            self._player.stop()
            self._player.release()
        if self._instance:
            self._instance.release()
        self._initialized = False

    def is_playing(self) -> bool:
        return self._player.get_state() == vlc.State.Playing if self._player else False

    def set_track_metadata(self, track_id: str | None = None, source_type: str | None = None) -> None:
        self._current_track_id = track_id
        self._current_source_type = source_type
