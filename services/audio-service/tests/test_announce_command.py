"""Spoken announcements: ducking the music, and getting the level back.

The one thing that must never happen is a box left quiet. A phrase that does
not come out is a missed courtesy; music stuck at 30 % afterwards looks like a
broken speaker and becomes a support case.
"""

from __future__ import annotations

import asyncio
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

from audio_service.core.mqtt_handler import (  # noqa: E402
    AnnounceCommand,
    MQTTMessageHandler,
)
from audio_service.core.service import AudioService  # noqa: E402


class _Backend:
    """Stands in for the VLC backend: remembers every volume it was given."""

    def __init__(self, *, playing: bool = True, volume: int = 60, fails: bool = False):
        self._playing = playing
        self.volume = volume
        self.volumes: list[int] = []
        self.fails = fails
        self.played: list[dict] = []

    def is_playing(self) -> bool:
        return self._playing

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, volume: int) -> None:
        self.volume = volume
        self.volumes.append(volume)

    async def play_announcement(
        self, clip_path, sink_name=None, *, volume_percent=100, timeout_sec=20.0
    ):
        if self.fails:
            raise RuntimeError("paplay failed")
        self.played.append(
            {
                "path": clip_path,
                "sink": sink_name,
                "volume_percent": volume_percent,
                # The level the music sat at while the phrase ran.
                "music_volume": self.volume,
            }
        )


def _service(
    backend: _Backend, *, output_device_name: str | None = None
) -> AudioService:
    """An AudioService with only the parts an announcement touches."""
    service = AudioService.__new__(AudioService)
    service._vlc_backend = backend
    service._announce_lock = asyncio.Lock()
    service._ducking = False
    service._get_audio_config = lambda: types.SimpleNamespace(
        output_device_name=output_device_name
    )
    return service


def test_the_music_is_turned_down_and_back_up():
    backend = _Backend(volume=60)
    service = _service(backend)

    asyncio.run(
        service._handle_announce(
            AnnounceCommand(source_uri="/announcements/a.wav", duck_percent=25)
        )
    )

    assert backend.played[0]["music_volume"] == 15
    assert backend.volume == 60
    assert backend.volumes == [15, 60]
    assert service._ducking is False


def test_a_failed_clip_still_gives_the_music_back():
    backend = _Backend(volume=60, fails=True)
    service = _service(backend)

    asyncio.run(
        service._handle_announce(AnnounceCommand(source_uri="/announcements/a.wav"))
    )

    assert backend.volume == 60
    assert service._ducking is False


def test_nothing_playing_means_nothing_to_duck():
    """set_volume() would publish a change nobody made."""
    backend = _Backend(playing=False, volume=60)
    service = _service(backend)

    asyncio.run(
        service._handle_announce(AnnounceCommand(source_uri="/announcements/a.wav"))
    )

    assert backend.volumes == []
    assert len(backend.played) == 1


def test_duck_percent_100_leaves_the_music_alone():
    backend = _Backend(volume=60)
    service = _service(backend)

    asyncio.run(
        service._handle_announce(
            AnnounceCommand(source_uri="/announcements/a.wav", duck_percent=100)
        )
    )

    assert backend.volumes == []


def test_the_configured_sink_is_named():
    """A different media role must not decide where the phrase comes out."""
    backend = _Backend()
    service = _service(backend, output_device_name="alsa_output.hdmi")

    asyncio.run(
        service._handle_announce(AnnounceCommand(source_uri="/announcements/a.wav"))
    )

    assert backend.played[0]["sink"] == "alsa_output.hdmi"


def test_announcements_do_not_overlap():
    """Two phrases at once are unintelligible, and their ducks would fight."""
    backend = _Backend(volume=60)
    service = _service(backend)
    order: list[str] = []

    async def slow(clip_path, sink_name=None, *, volume_percent=100, timeout_sec=20.0):
        order.append(f"start {clip_path}")
        await asyncio.sleep(0.05)
        order.append(f"end {clip_path}")

    backend.play_announcement = slow

    async def both():
        await asyncio.gather(
            service._handle_announce(AnnounceCommand(source_uri="a")),
            service._handle_announce(AnnounceCommand(source_uri="b")),
        )

    asyncio.run(both())

    assert order in (
        ["start a", "end a", "start b", "end b"],
        ["start b", "end b", "start a", "end a"],
    )


def test_the_periodic_status_is_held_off_while_ducking():
    """Otherwise the WebUI slider dips and jumps back for every phrase."""
    backend = _Backend()
    service = _service(backend)
    service._ducking = True

    published: list[bool] = []

    async def spy(*, force=True):
        # The real method returns before doing anything when ducking.
        if not force and service._ducking:
            return
        published.append(force)

    asyncio.run(spy(force=False))
    assert published == []

    asyncio.run(spy(force=True))
    assert published == [True]


@pytest.mark.parametrize(
    "payload",
    [
        {},  # no source_uri
        {"source_uri": 5},
        {"source_uri": "/a.wav", "duck_percent": "loud"},
    ],
)
def test_a_malformed_announce_command_is_dropped(payload):
    """The topic is unauthenticated; a bad payload must not raise."""
    calls: list = []

    async def on_announce(command):
        calls.append(command)

    handler = MQTTMessageHandler(config=None, on_announce=on_announce)
    asyncio.run(handler._handle_announce(payload))

    assert calls == []


def test_a_well_formed_announce_command_reaches_the_callback():
    calls: list[AnnounceCommand] = []

    async def on_announce(command):
        calls.append(command)

    handler = MQTTMessageHandler(config=None, on_announce=on_announce)
    asyncio.run(
        handler._handle_announce(
            {"source_uri": "/announcements/a.wav", "duck_percent": 40}
        )
    )

    assert calls[0].source_uri == "/announcements/a.wav"
    assert calls[0].duck_percent == 40
    # The defaults are the contract with the backend, which may omit them.
    assert calls[0].volume_percent == 100
