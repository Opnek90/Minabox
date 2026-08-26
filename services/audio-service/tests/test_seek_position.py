"""A seek has to be confirmed before the status that reports it goes out.

Seeking is not its own command: the backend publishes a play command carrying
start_position_ms, and _handle_play publishes the status unconditionally the
moment play() returns. That message is the only one that reaches subscribers
with a position - it is excluded from the fingerprint on purpose - so if VLC
has not applied set_time() yet, everything counting down from that number is
wrong for the rest of the track.
"""

from __future__ import annotations

import asyncio
import sys
import time
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

from audio_service.infrastructure.vlc_backend import (  # noqa: E402
    _SEEK_TOLERANCE_MS,
    VLCBackend,
)


class _LaggingPlayer:
    """Reports the old position for *lag* polls, the way libVLC actually does."""

    def __init__(self, before: int, after: int, lag: int) -> None:
        self._before, self._after, self._lag = before, after, lag
        self.polls = 0

    def get_time(self) -> int:
        self.polls += 1
        return self._before if self.polls <= self._lag else self._after


def _backend(player) -> VLCBackend:
    backend = object.__new__(VLCBackend)
    backend._player = player
    return backend


@pytest.mark.asyncio
async def test_it_waits_until_vlc_reports_the_new_position():
    player = _LaggingPlayer(before=2000, after=120_000, lag=3)
    await _backend(player)._wait_for_position(120_000)
    assert player.polls == 4


@pytest.mark.asyncio
async def test_it_returns_at_once_when_vlc_is_already_there():
    player = _LaggingPlayer(before=120_000, after=120_000, lag=0)
    await _backend(player)._wait_for_position(120_000)
    assert player.polls == 1


@pytest.mark.asyncio
async def test_playback_running_past_the_target_still_counts():
    """The track keeps playing while we wait, so the reported position drifts
    past the target rather than landing on it."""
    drifted = 120_000 + _SEEK_TOLERANCE_MS - 1
    player = _LaggingPlayer(before=2000, after=drifted, lag=1)
    await _backend(player)._wait_for_position(120_000)
    assert player.polls == 2


@pytest.mark.asyncio
async def test_it_gives_up_rather_than_blocking_playback():
    """A player that never confirms must not hold the play command open.

    The outer wait_for is what makes this a failing test rather than a hung
    suite: without the loop's own deadline it would poll forever.
    """
    player = _LaggingPlayer(before=2000, after=2000, lag=99)
    await asyncio.wait_for(
        _backend(player)._wait_for_position(120_000, timeout_sec=0.2), timeout=3.0
    )
    assert player.polls >= 2


@pytest.mark.asyncio
async def test_an_unknown_position_is_not_mistaken_for_the_target():
    """libVLC returns -1 while it does not know, and -1 must never satisfy
    a seek to a position near zero."""
    player = _LaggingPlayer(before=-1, after=0, lag=2)
    await _backend(player)._wait_for_position(0, timeout_sec=0.2)
    assert player.polls == 3


# ---------------------------------------------------------------------------
# The wiring: play() has to actually do the waiting
# ---------------------------------------------------------------------------


class _SeekingPlayer:
    """Applies set_time only after a few get_time polls, like libVLC."""

    def __init__(self) -> None:
        self.position = 0
        self.requested: int | None = None
        self.polls = 0
        self.volume = 30
        self.muted = 0
        # What PipeWire hands the stream when it opens the output. A fresh
        # player reports 0 up to that moment, which is exactly why checking
        # before play() finds nothing wrong.
        self.remembered_mute = 0

    def set_media(self, media) -> None:
        pass

    def play(self) -> int:
        self.muted = self.remembered_mute
        return 0

    def get_state(self):
        return sys.modules["vlc"].State.Playing

    def set_time(self, ms: int) -> None:
        self.requested = ms

    def get_time(self) -> int:
        self.polls += 1
        if self.requested is not None and self.polls > 2:
            self.position = self.requested
        return self.position

    def audio_set_volume(self, v: int) -> int:
        self.volume = v
        return 0

    def audio_get_mute(self) -> int:
        return self.muted

    def audio_set_mute(self, muted: bool) -> None:
        self.muted = 1 if muted else 0


class _FakeInstance:
    @staticmethod
    def media_new(uri: str):
        return object()


def _playable_backend(player) -> VLCBackend:
    backend = object.__new__(VLCBackend)
    backend._initialized = True
    backend._player = player
    backend._instance = _FakeInstance()
    backend._pending_volume = None
    backend._muted = False
    backend._current_source_uri = None
    # Recent enough that the cold-pipeline prewarm is skipped.
    backend._last_stop_time = time.monotonic()
    return backend


@pytest.mark.asyncio
async def test_play_does_not_return_before_the_seek_has_landed():
    """The status published right after play() is the only one that carries a
    position, so play() must not return while VLC still reports the old one."""
    player = _SeekingPlayer()
    backend = _playable_backend(player)

    await asyncio.wait_for(
        backend.play("https://example.invalid/track.mp3", start_position_ms=120_000),
        timeout=5.0,
    )

    assert player.requested == 120_000
    assert player.get_time() == 120_000, "play() returned before the seek landed"


@pytest.mark.asyncio
async def test_an_ordinary_track_start_does_not_pay_the_wait():
    """Only seeks and resumes wait; a normal start passes 0 and skips it."""
    player = _SeekingPlayer()
    backend = _playable_backend(player)

    await asyncio.wait_for(
        backend.play("https://example.invalid/track.mp3"), timeout=5.0
    )

    assert player.requested is None
    assert player.polls == 0


@pytest.mark.asyncio
async def test_play_unmutes_a_stream_pipewire_handed_back_muted():
    """A muted box that nobody muted (docs/services/Offene-Punkte.md 1.6).

    WirePlumber remembers mute per media role and pushes it onto every stream
    the moment it opens the output - after play(), not before. The service
    believed it was unmuted and never corrected it, so no restart of the
    container and no reboot of the box brought the sound back.
    """
    player = _SeekingPlayer()
    backend = _playable_backend(player)
    player.remembered_mute = 1

    await asyncio.wait_for(
        backend.play("https://example.invalid/track.mp3"), timeout=5.0
    )

    assert player.muted == 0, "play() left the stream on PipeWire's remembered mute"


@pytest.mark.asyncio
async def test_play_keeps_a_mute_the_user_asked_for():
    """The correction must not undo a real mute - it forces the state the
    service asked for, in both directions."""
    player = _SeekingPlayer()
    backend = _playable_backend(player)
    await backend.set_muted(True)
    player.remembered_mute = 0

    await asyncio.wait_for(
        backend.play("https://example.invalid/track.mp3"), timeout=5.0
    )

    assert player.muted == 1, "play() dropped the mute the user asked for"
