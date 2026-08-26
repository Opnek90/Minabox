"""What the box reports as its volume when libVLC cannot say.

libVLC answers -1 whenever it does not know - with no player, and after stop()
has released the media. Passing that on as 0 told every subscriber the volume
had been turned down to the minimum the instant playback ended, which on the
display looked like the box quietening itself the moment a figure was lifted
off the reader.
"""

from __future__ import annotations

import sys
import types

import pytest

if "vlc" not in sys.modules:  # pragma: no cover - import shim
    _vlc = types.ModuleType("vlc")
    _vlc.Instance = object
    _vlc.MediaPlayer = object
    _vlc.State = types.SimpleNamespace(
        Playing="Playing", Paused="Paused", Error="Error", Stopped="Stopped"
    )
    sys.modules["vlc"] = _vlc

from audio_service.config_schema import AudioConfig  # noqa: E402
from audio_service.infrastructure.vlc_backend import VLCBackend  # noqa: E402


class _Player:
    """A player that forgets the volume once the media is released."""

    def __init__(self, volume: int = 30) -> None:
        self.volume = volume
        self.accepts = True
        self.stopped = False

    def audio_set_volume(self, v: int) -> int:
        if not self.accepts:
            return -1
        self.volume = v
        return 0

    def audio_get_volume(self) -> int:
        return -1 if self.stopped else self.volume

    def stop(self) -> None:
        self.stopped = True


def _backend(player=None, **overrides) -> VLCBackend:
    config = AudioConfig(
        **{"min_volume": 20, "max_volume": 40, "default_volume": 30, **overrides}
    )
    backend = VLCBackend(config)
    backend._player = player
    return backend


@pytest.mark.asyncio
async def test_a_running_player_is_the_source_of_truth():
    assert await _backend(_Player(35)).get_volume() == 35


@pytest.mark.asyncio
async def test_stopping_does_not_look_like_turning_the_volume_down():
    """The reported bug: lift the figure, and the box claims to be at its
    quietest setting."""
    player = _Player(30)
    backend = _backend(player)
    await backend.set_volume(30)

    await backend.stop()

    assert await backend.get_volume() == 30


@pytest.mark.asyncio
async def test_the_level_survives_a_stop_and_a_further_change():
    player = _Player(30)
    backend = _backend(player)
    await backend.set_volume(35)
    await backend.stop()
    assert await backend.get_volume() == 35


@pytest.mark.asyncio
async def test_without_a_player_it_reports_the_configured_default():
    """Not zero: the box has never been silent, it just is not running yet."""
    assert await _backend(None).get_volume() == 30


@pytest.mark.asyncio
async def test_a_rejected_change_is_still_what_we_asked_for():
    """libVLC refuses while the pipeline is not ready; the level we asked for
    is what will be applied, so it is what we report."""
    player = _Player(30)
    player.accepts = False
    backend = _backend(player)
    await backend.set_volume(40)
    player.stopped = True
    assert await backend.get_volume() == 40


@pytest.mark.asyncio
async def test_the_reported_level_stays_inside_the_configured_range():
    backend = _backend(_Player(30))
    await backend.set_volume(100)
    await backend.stop()
    assert await backend.get_volume() == 40
