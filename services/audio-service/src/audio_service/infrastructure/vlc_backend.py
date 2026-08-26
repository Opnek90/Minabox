"""VLC-based audio backend implementation.

Uses python-vlc to provide audio playback functionality.
"""

import asyncio
import os
import subprocess
import time
from pathlib import Path

import structlog
import vlc

from ..config_schema import AudioConfig, OutputDeviceType
from ..exceptions import (
    AudioFileNotFoundError,
    PlaybackError,
    VLCError,
)
from .audio_backend import AudioBackend, AudioStatus, PlaybackState

logger = structlog.get_logger(__name__)

# Seconds of idle after which PipeWire/PulseAudio suspends the ALSA sink.
# We prewarm slightly below this threshold.
_PIPELINE_SUSPEND_THRESHOLD_SEC = 4.0

# How close VLC has to report being to a requested position before we call the
# seek done, and how long we are willing to wait for it.
_SEEK_TOLERANCE_MS = 1000
_SEEK_CONFIRM_TIMEOUT_SEC = 1.0


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
        # The last level we asked libVLC for. It is the answer to "how loud is
        # this box" whenever libVLC cannot say: after stop() the player has no
        # media and audio_get_volume() returns -1, and reporting 0 for that
        # made every subscriber believe the volume had been turned down to the
        # minimum the moment a figure was lifted off the reader.
        self._last_volume: int = getattr(config, "default_volume", 40) or 40
        self._current_track_id: str | None = None
        self._current_source_type: str | None = None
        self._current_source_uri: str | None = None
        # Monotonic timestamp of the last time the audio stream was closed
        # (stop() or service start).  Used to decide whether a pacat prewarm
        # is needed before the next play().
        self._last_stop_time: float = float("-inf")

    @property
    def is_initialized(self) -> bool:
        """True once the VLC backend has been successfully initialized."""
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
        """Initialize VLC instance and media player."""
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
                await self._set_pulse_default_sink(sink_name)

            vlc_args = self._build_vlc_args()
            self._instance = vlc.Instance(vlc_args)

            if self._instance is None:
                raise VLCError("Failed to create VLC instance")

            self._player = self._instance.media_player_new()

            if self._player is None:
                raise VLCError("Failed to create VLC media player")

            min_vol = getattr(self._config, "min_volume", 0)
            initial_volume = getattr(self._config, "default_volume", 40)
            if initial_volume is None:
                initial_volume = 40
            initial_volume = min(initial_volume, self._config.max_volume)
            initial_volume = max(initial_volume, min_vol)

            logger.debug("setting_initial_volume", volume=initial_volume)
            self._last_volume = initial_volume
            result = self._player.audio_set_volume(initial_volume)
            if result == -1:
                logger.warning(
                    "initial_volume_set_returned_error", requested=initial_volume
                )
            else:
                logger.debug("initial_volume_set_success", volume=initial_volume)

            self._initialized = True

        except Exception as e:
            logger.error("vlc_backend_initialization_failed", error=str(e))
            raise VLCError(f"VLC backend initialization failed: {e}") from e

        # Best-effort: disable PulseAudio suspend-on-idle on the server.
        # This helps on pure PulseAudio hosts; on PipeWire hosts it may be
        # a no-op, which is why play() has its own time-based prewarm.
        await self._disable_pulse_suspend_on_idle()

        # Pre-warm the pipeline at service start (pipeline has never been
        # opened). Marks _last_stop_time so the first play() skips an
        # extra prewarm.
        await self._prewarm_audio_pipeline()
        self._last_stop_time = time.monotonic()

    def _build_vlc_args(self) -> list[str]:
        return [
            "--quiet",
            "--no-video",
            "--aout=pulse",
        ]

    def _set_pulse_default_sink_blocking(self, sink_name: str) -> bool:
        """Set Pulse default sink so VLC uses the configured device.

        Blocking - call via :meth:`_set_pulse_default_sink`.
        """
        if not os.environ.get("PULSE_SERVER"):
            return False
        try:
            subprocess.run(
                ["pactl", "suspend-sink", sink_name, "0"],
                capture_output=True, timeout=5,
            )
            result = subprocess.run(
                ["pactl", "set-default-sink", sink_name],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("pulse_set_default_sink_error", sink=sink_name, error=str(e))
            return False

    async def _set_pulse_default_sink(self, sink_name: str) -> bool:
        """Set the Pulse default sink without stalling the event loop.

        Two pactl calls at 5 s timeout each: run inline they would freeze MQTT
        dispatch and the REST API for as long as the Pulse server takes to
        answer - exactly when the user is switching output and expects the UI
        to react.
        """
        return await asyncio.to_thread(
            self._set_pulse_default_sink_blocking, sink_name
        )

    def _disable_pulse_suspend_on_idle_blocking(self) -> None:
        """Blocking half of :meth:`_disable_pulse_suspend_on_idle`."""
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
                    hint="no-op on PipeWire or module already unloaded",
                    stderr=result.stderr.strip(),
                )
        except Exception as e:
            logger.warning("pulse_suspend_on_idle_error", error=str(e))

    async def _disable_pulse_suspend_on_idle(self) -> None:
        """Best-effort: unload module-suspend-on-idle from PulseAudio server.

        Effective on pure PulseAudio hosts.  On PipeWire hosts this is usually
        a no-op (PipeWire has its own suspend mechanism); in that case the
        time-based prewarm in play() handles the stutter.
        """
        if not os.environ.get("PULSE_SERVER"):
            return
        await asyncio.to_thread(self._disable_pulse_suspend_on_idle_blocking)

    async def _prewarm_audio_pipeline(self) -> None:
        """Write 300 ms of silence via pacat to open the ALSA hardware buffers.

        When the ALSA device is suspended (cold after idle), hardware buffer
        allocation takes ~100-300 ms.  Writing silence first lets that
        allocation complete so the subsequent VLC play() starts on a warm sink.

        pacat (pulseaudio-utils) is installed in the Dockerfile.
        """
        if not os.environ.get("PULSE_SERVER"):
            return

        cmd = [
            "pacat", "--playback",
            "--rate=48000", "--channels=2", "--format=float32le",
        ]
        sink_name = (self._config.output_device_name or "").strip()
        if sink_name:
            cmd += ["--device", sink_name]

        # 300 ms of silence: 48000 * 2 ch * 4 bytes * 0.3 s = 115 200 bytes
        silence = bytes(115_200)

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

        Cold-start stutter fix (issue #65):
        If the audio pipeline has been idle for longer than
        _PIPELINE_SUSPEND_THRESHOLD_SEC
        seconds, PipeWire/PulseAudio will have suspended the ALSA device.  We
        detect this via the elapsed time since the last stop() and run a pacat
        prewarm to re-open the hardware before VLC writes its first sample.

        Warm plays (consecutive tracks, < 4 s idle) take the fast path with no
        added latency.
        """
        if not self._initialized or self._player is None:
            raise PlaybackError("VLC backend not initialized")

        try:
            await self._validate_source(source_uri)

            # --- Cold-pipeline guard -------------------------------------------
            idle_sec = time.monotonic() - self._last_stop_time
            if idle_sec > _PIPELINE_SUSPEND_THRESHOLD_SEC:
                logger.debug(
                    "pipeline_cold_prewarming",
                    idle_sec=round(idle_sec, 1),
                )
                await self._prewarm_audio_pipeline()
                # Update timestamp so consecutive plays skip prewarm
                self._last_stop_time = time.monotonic()
            # ------------------------------------------------------------------

            media = self._instance.media_new(source_uri)
            self._player.set_media(media)

            result = self._player.play()
            if result == -1:
                raise PlaybackError("VLC player.play() returned error")

            await self._wait_for_state(vlc.State.Playing)

            if self._pending_volume is not None:
                min_vol = getattr(self._config, "min_volume", 0)
                applied = min(
                    max(self._pending_volume, min_vol), self._config.max_volume
                )
                self._player.audio_set_volume(applied)
                self._pending_volume = None

            if start_position_ms > 0:
                await asyncio.sleep(0.2)
                self._player.set_time(start_position_ms)
                await self._wait_for_position(start_position_ms)

            self._current_source_uri = source_uri
        except Exception as e:
            # "from e" keeps the original cause in the traceback: without it a
            # missing file, a dead stream and a codec failure all arrive
            # outside as the same generic playback_error.
            raise PlaybackError(f"Playback failed: {e}") from e

    async def _validate_source(self, source_uri: str) -> None:
        if source_uri.startswith(("http://", "https://")):
            return
        if not Path(source_uri).exists():
            raise AudioFileNotFoundError(f"Audio file not found: {source_uri}")

    async def _wait_for_state(
        self, expected_state: vlc.State, timeout_sec: float = 5.0
    ) -> None:
        elapsed = 0.0
        while elapsed < timeout_sec:
            if self._player.get_state() == expected_state:
                return
            await asyncio.sleep(0.1)
            elapsed += 0.1
        raise PlaybackError(f"Timeout waiting for {expected_state}")

    async def _wait_for_position(
        self, target_ms: int, timeout_sec: float = _SEEK_CONFIRM_TIMEOUT_SEC
    ) -> None:
        """Wait until VLC reports being near *target_ms*.

        ``set_time()`` is asynchronous, like ``play()`` and ``pause()``. The
        status published straight afterwards would otherwise carry the position
        from *before* the jump - and this is the only moment the position
        reaches anyone: it is deliberately excluded from the status fingerprint
        so a playing track does not publish every two seconds. Subscribers
        therefore count down from what arrives here, and a wrong number here
        stays wrong for the rest of the track.

        Only seeks and resumes pay this wait; an ordinary track start passes
        ``start_position_ms=0`` and never gets here.
        """
        elapsed = 0.0
        while elapsed < timeout_sec:
            current = self._player.get_time()
            # Playback keeps running while we wait, so the reported position
            # drifts past the target rather than landing on it.
            if current >= 0 and abs(current - target_ms) <= _SEEK_TOLERANCE_MS:
                return
            await asyncio.sleep(0.05)
            elapsed += 0.05
        logger.debug(
            "seek_position_not_confirmed",
            target_ms=target_ms,
            reported_ms=self._player.get_time(),
        )

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

        self._player.pause()  # Toggle: Paused -> Playing

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
            # Clear all three together: leaving track_id behind made the status
            # report "stopped" while still naming a track, which the WebUI then
            # showed as the current title.
            self._current_source_uri = None
            self._current_track_id = None
            self._current_source_type = None
        # Record when the audio stream closed so play() can decide whether
        # to prewarm the pipeline before the next VLC play.
        self._last_stop_time = time.monotonic()

    async def set_muted(self, muted: bool) -> None:
        """Mute or unmute through libVLC, leaving the volume untouched.

        Muting must not go through set_volume(0): that clamps to min_volume,
        so on a box with min_volume=15 "mute" only turned the music down to 15
        and kept playing. libVLC's own mute is independent of the volume, so
        unmuting also restores the previous level by itself.
        """
        if not self._player:
            return
        self._player.audio_set_mute(muted)

    async def is_muted(self) -> bool:
        """Report libVLC's mute state (False when unknown)."""
        if not self._player:
            return False
        return self._player.audio_get_mute() == 1

    async def set_volume(self, volume: int) -> None:
        if not self._player:
            return
        min_vol = getattr(self._config, "min_volume", 0)
        clamped = min(max(volume, min_vol), self._config.max_volume)
        self._last_volume = clamped
        if self._player.audio_set_volume(clamped) == -1:
            self._pending_volume = clamped
        else:
            self._pending_volume = None

    async def get_volume(self) -> int:
        """Report the running level, falling back to the last one we set.

        libVLC has two ways of saying "ask me later" and neither is a level:
        -1 with no player or after stop() has released the media, and 0 in the
        moment after play() while the audio output is still coming up. Passing
        either on told every subscriber the volume had moved - once to the
        minimum when playback ended, and once to zero and back at the start of
        every track, which on the panel was a full-screen volume overlay for
        putting a figure on the reader.

        What makes the second case decidable is that every write goes through
        the clamp in set_volume(), so the box cannot be at a level outside the
        configured range. Anything outside it is libVLC not knowing yet.
        """
        if not self._player:
            return self._last_volume
        reported = self._player.audio_get_volume()
        if self._is_plausible(reported):
            return reported
        if self._pending_volume is not None:
            return self._pending_volume
        return self._last_volume

    def _is_plausible(self, reported: int) -> bool:
        """True if *reported* is a level this box could actually be at."""
        if reported < 0:
            return False
        min_volume = getattr(self._config, "min_volume", 0)
        return min_volume <= reported <= self._config.max_volume

    async def get_position(self) -> int:
        return self._player.get_time() if self._player else 0

    async def get_duration(self) -> int | None:
        if not self._player:
            return None
        d = self._player.get_length()
        return d if d > 0 else None

    async def get_state(self) -> PlaybackState:
        if not self._player:
            return PlaybackState.STOPPED
        v = self._player.get_state()
        if v == vlc.State.Playing:
            return PlaybackState.PLAYING
        if v == vlc.State.Paused:
            return PlaybackState.PAUSED
        if v == vlc.State.Error:
            return PlaybackState.ERROR
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

    def set_track_metadata(
        self,
        track_id: str | None = None,
        source_type: str | None = None,
    ) -> None:
        self._current_track_id = track_id
        self._current_source_type = source_type
