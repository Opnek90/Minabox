"""Tests for the go-live hardening of the audio service.

Each test here pins down one defect found while reviewing the service for
production. They are deliberately narrow: the point is that the specific
failure cannot come back unnoticed.
"""

from __future__ import annotations

import sys
import types

import pytest

# python-vlc is not installed in the test environment (it needs libVLC).
# The backend only touches vlc.State and the two factory calls, so a stub is
# enough to import the module and exercise the pure-Python parts.
if "vlc" not in sys.modules:  # pragma: no cover - import shim
    _vlc = types.ModuleType("vlc")
    _vlc.Instance = object
    _vlc.MediaPlayer = object
    _vlc.State = types.SimpleNamespace(
        Playing="Playing", Paused="Paused", Error="Error", Stopped="Stopped"
    )
    sys.modules["vlc"] = _vlc

from audio_service.config_schema import AppConfig, AudioConfig, EnvConfig  # noqa: E402
from audio_service.core.state_manager import AudioState  # noqa: E402
from audio_service.infrastructure.audio_backend import PlaybackState  # noqa: E402
from audio_service.infrastructure.vlc_backend import VLCBackend  # noqa: E402


def _app_config(**audio_overrides) -> AppConfig:
    audio = AudioConfig(**{"min_volume": 15, "max_volume": 35,
                           "default_volume": 25, **audio_overrides})
    env = EnvConfig(
        mqtt_broker="mqtt",
        mqtt_port=1883,
        minabox_device_id="testbox",
        log_level="INFO",
    )
    return AppConfig(env=env, audio=audio)


class _FakePlayer:
    """Stands in for vlc.MediaPlayer, recording what the backend asks of it."""

    def __init__(self) -> None:
        self.volume = 0
        self.stopped = False
        self.muted = 0

    def audio_set_mute(self, m: bool) -> None:
        self.muted = 1 if m else 0

    def audio_get_mute(self) -> int:
        return self.muted

    def audio_set_volume(self, v: int) -> int:
        self.volume = v
        return 0

    def audio_get_volume(self) -> int:
        return self.volume

    def stop(self) -> None:
        self.stopped = True

    def get_state(self):
        return "Stopped"

    def get_time(self) -> int:
        return 0

    def get_length(self) -> int:
        return 0


# --- startup volume ---------------------------------------------------------


def test_fresh_state_does_not_look_like_a_remembered_volume():
    """A box that never played must fall through to default_volume.

    The state model used to default last_volume to 40. The service checks
    `last_volume > 0` to decide whether a volume was remembered, so that
    default was mistaken for a real one: a freshly set up box started at
    max_volume instead of default_volume - loudest exactly on first use.
    """
    assert AudioState().last_volume == 0


def test_remembered_volume_still_wins_over_default():
    """The fix must not break resuming the volume the user last chose."""
    state = AudioState(last_volume=22)
    assert state.last_volume > 0


@pytest.mark.parametrize(
    ("last_volume", "expected"),
    [
        (0, 25),    # nothing remembered -> default_volume
        (22, 22),   # remembered, inside the bounds -> kept
        (99, 35),   # remembered, above max_volume -> clamped down
        (3, 15),    # remembered, below min_volume -> clamped up
    ],
)
def test_startup_volume_selection(last_volume, expected):
    """Mirrors the decision AudioService.start() makes on boot."""
    cfg = _app_config().audio
    state = AudioState(last_volume=last_volume)

    if state.last_volume > 0:
        volume = min(state.last_volume, cfg.max_volume)
    else:
        volume = min(cfg.default_volume, cfg.max_volume)
    volume = max(volume, cfg.min_volume)

    assert volume == expected


# --- status after stop ------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_clears_all_track_metadata():
    """stop() must not leave a track name behind.

    Only source_uri used to be cleared, so the status kept reporting
    track_id and source_type while state was already "stopped" - the WebUI
    showed a current title for a player that had stopped.
    """
    backend = VLCBackend(_app_config().audio)
    backend._player = _FakePlayer()
    backend._initialized = True
    backend.set_track_metadata(track_id="track_42", source_type="file")
    backend._current_source_uri = "/mnt/audio/x.mp3"

    await backend.stop()

    status = await backend.get_status()
    assert status.state == PlaybackState.STOPPED
    assert status.track_id is None
    assert status.source_type is None
    assert status.source_uri is None


# --- volume bounds ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0, 15), (10, 15), (25, 25), (35, 35), (80, 35), (100, 35)],
)
async def test_set_volume_is_clamped_to_configured_bounds(requested, expected):
    """Child protection: no command may leave [min_volume, max_volume].

    Note that 0 is raised to min_volume as well - which is why muting must not
    go through this path. See the mute tests below.
    """
    backend = VLCBackend(_app_config().audio)
    player = _FakePlayer()
    backend._player = player

    await backend.set_volume(requested)

    assert player.volume == expected


# --- mute -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mute_does_not_go_through_the_volume_clamp():
    """Pressing the knob must actually silence the box.

    Muting used to call set_volume(0), which clamps to min_volume: on a box
    with min_volume=15 the music merely dropped to 15 and kept playing, while
    the status already reported muted=true.
    """
    backend = VLCBackend(_app_config().audio)
    player = _FakePlayer()
    backend._player = player
    await backend.set_volume(30)

    await backend.set_muted(True)

    assert player.muted == 1, "libVLC mute was not engaged"
    assert player.volume == 30, "mute must not change the volume"
    assert await backend.is_muted() is True


@pytest.mark.asyncio
async def test_unmute_restores_the_previous_level_by_itself():
    """Because the volume was never touched, nothing has to be restored."""
    backend = VLCBackend(_app_config().audio)
    player = _FakePlayer()
    backend._player = player
    await backend.set_volume(28)

    await backend.set_muted(True)
    await backend.set_muted(False)

    assert player.muted == 0
    assert player.volume == 28
    assert await backend.is_muted() is False


@pytest.mark.asyncio
async def test_muting_is_a_no_op_without_a_player():
    """Called before initialize() it must not raise."""
    backend = VLCBackend(_app_config().audio)
    await backend.set_muted(True)
    assert await backend.is_muted() is False


# --- exception naming -------------------------------------------------------


def test_audio_file_not_found_does_not_shadow_the_builtin():
    """The service exception must not be called FileNotFoundError.

    vlc_backend imports it, and both routes.py and pulse_detector.py rely on
    catching the *builtin* FileNotFoundError when an external command is
    missing. A same-named service exception silently broke that.
    """
    from audio_service import exceptions

    assert not hasattr(exceptions, "FileNotFoundError")
    assert issubclass(exceptions.AudioFileNotFoundError, exceptions.AudioError)
    assert not issubclass(exceptions.AudioFileNotFoundError, FileNotFoundError)


# --- last will --------------------------------------------------------------


def test_mqtt_client_registers_a_stopped_status_will():
    """A crashed service must not leave a retained "playing" status behind.

    The status topic is retained, so without a last will every subscriber -
    LED ring, OLED, WebUI - would keep showing playback after the container
    died.
    """
    from audio_service.infrastructure.mqtt_client import MQTTClient

    config = _app_config()
    client = MQTTClient(config)

    will = client._will
    assert will is not None, "no last will registered"
    assert will.topic == "minabox/testbox/audio/status"
    assert will.retain is True
    assert will.qos == 1

    import json

    payload = json.loads(will.payload)
    assert payload["state"] == PlaybackState.STOPPED.value
    assert payload["track_id"] is None
