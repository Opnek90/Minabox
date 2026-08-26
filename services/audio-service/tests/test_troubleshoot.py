"""The sound-repair chain behind the "Fix sound problem" button.

docs/services/Offene-Punkte.md 1.7. Two properties matter more than the
individual steps, and both are easy to lose in a later edit:

- **Idempotent.** The UI offers the button again after a "no, still nothing",
  so a second run must not undo the first one's work.
- **Only what is demonstrably wrong.** A box someone deliberately turned down
  quietly must come out of this exactly as quiet as it went in. A button that
  changes state has to be trusted, and one loud surprise is enough to lose
  that.
"""

from __future__ import annotations

import sys
import types

import pytest

# python-vlc is not installed in the test environment (it needs libVLC).
if "vlc" not in sys.modules:  # pragma: no cover - import shim
    _vlc = types.ModuleType("vlc")
    _vlc.Instance = object
    _vlc.MediaPlayer = object
    _vlc.State = types.SimpleNamespace(
        Playing="Playing", Paused="Paused", Error="Error", Stopped="Stopped"
    )
    sys.modules["vlc"] = _vlc

from audio_service.config_schema import AudioConfig  # noqa: E402
from audio_service.core import troubleshoot as ts  # noqa: E402


class _FakeService:
    """An AudioService with only what the chain touches."""

    def __init__(
        self,
        *,
        configured: str = "wm8960",
        sinks: list[str] | None = None,
        muted: bool = False,
        volume: int = 40,
        min_volume: int = 10,
        default_volume: int = 40,
        enabled: list[str] | None = None,
    ) -> None:
        self._audio_config = AudioConfig(
            output_device_name=configured,
            min_volume=min_volume,
            max_volume=100,
            default_volume=default_volume,
            enabled_output_devices=enabled or [],
        )
        self._sinks = ["wm8960"] if sinks is None else sinks
        self._muted = muted
        self._volume = volume
        self.switched_to: str | None = None
        self.switch_allowed_disabled = False
        self.tone_played = 0

    def _get_audio_config(self):
        return self._audio_config

    async def get_audio_devices(
        self, enabled_only: bool = False, *, force_refresh: bool = False
    ):
        return [{"id": s, "name": s} for s in self._sinks]

    async def switch_output_device(
        self, sink_name=None, direction=None, *, allow_disabled: bool = False
    ):
        enabled = self._audio_config.enabled_output_devices
        if enabled and not allow_disabled and sink_name not in enabled:
            raise ValueError(f"Device not available or not enabled: {sink_name!r}")
        self.switched_to = sink_name
        self.switch_allowed_disabled = allow_disabled
        self._audio_config.output_device_name = sink_name

    async def set_muted(self, muted: bool) -> None:
        self._muted = muted

    async def get_volume(self) -> int:
        return self._volume

    async def set_volume(self, volume: int) -> None:
        self._volume = volume

    async def play_troubleshoot_tone(self) -> None:
        self.tone_played += 1


class _FakeMixer:
    """Stands in for pactl: a sink with a mute flag and a level."""

    def __init__(self, muted: bool = False, volume: int = 60) -> None:
        self.muted = muted
        self.volume = volume
        self.muted_streams: list[str] = []
        self.calls: list[list[str]] = []

    def install(self, monkeypatch) -> None:
        def _pactl(args: list[str]):
            self.calls.append(args)
            if args[:1] == ["set-sink-mute"]:
                self.muted = args[2] != "0"
            elif args[:1] == ["set-sink-volume"]:
                self.volume = int(args[2].rstrip("%"))
            elif args[:1] == ["set-sink-input-mute"]:
                self.muted_streams = [i for i in self.muted_streams if i != args[1]]
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(ts, "_pactl", _pactl)
        monkeypatch.setattr(
            ts, "_sink_mute_and_volume", lambda sink: (self.muted, self.volume)
        )
        monkeypatch.setattr(
            ts, "_muted_sink_input_indices", lambda: list(self.muted_streams)
        )


def _steps(result: dict) -> dict[str, dict]:
    return {s["id"]: s for s in result["steps"]}


@pytest.mark.asyncio
async def test_a_healthy_box_is_left_exactly_as_it_was(monkeypatch):
    service = _FakeService(volume=40)
    mixer = _FakeMixer(muted=False, volume=60)
    mixer.install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert result["fixed"] == []
    assert result["cause"] is None
    assert mixer.volume == 60, "turned up a sink that was fine"
    assert service._volume == 40
    assert service.switched_to is None
    assert service.tone_played == 1, "the tone is the whole point of the chain"


@pytest.mark.asyncio
async def test_a_quiet_box_stays_quiet(monkeypatch):
    """30 % is quiet, not broken. Nobody asked for it to be turned up."""
    service = _FakeService(volume=15, min_volume=10)
    mixer = _FakeMixer(muted=False, volume=30)
    mixer.install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert result["fixed"] == []
    assert mixer.volume == 30
    assert service._volume == 15


@pytest.mark.asyncio
async def test_a_muted_sink_is_unmuted(monkeypatch):
    service = _FakeService()
    mixer = _FakeMixer(muted=True, volume=60)
    mixer.install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert mixer.muted is False
    assert _steps(result)["sink_level"]["fixed"] is True
    assert result["cause"] == "sink_level"


@pytest.mark.asyncio
async def test_a_sink_at_two_percent_is_raised(monkeypatch):
    """2 % is not a choice anyone makes with a volume control."""
    service = _FakeService()
    mixer = _FakeMixer(muted=False, volume=2)
    mixer.install(monkeypatch)

    await ts.AudioTroubleshooter(service).run()

    assert mixer.volume == ts._SINK_VOLUME_REPAIR_PERCENT


@pytest.mark.asyncio
async def test_a_vanished_sink_falls_back_to_one_that_exists(monkeypatch):
    service = _FakeService(configured="wm8960", sinks=["hdmi", "headphones"])
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert service.switched_to == "hdmi"
    assert _steps(result)["sink_present"]["fixed"] is True


@pytest.mark.asyncio
async def test_no_sink_at_all_is_reported_not_papered_over(monkeypatch):
    """The sound card is gone. Only a reboot fixes that, and pretending
    otherwise would be worse than saying so."""
    service = _FakeService(sinks=[])
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert _steps(result)["sink_present"]["ok"] is False
    assert service.switched_to is None


@pytest.mark.asyncio
async def test_the_service_mute_is_lifted(monkeypatch):
    service = _FakeService(muted=True)
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert service._muted is False
    assert _steps(result)["service_mute"]["fixed"] is True


@pytest.mark.asyncio
async def test_a_volume_below_the_minimum_is_lifted(monkeypatch):
    service = _FakeService(volume=3, min_volume=10, default_volume=40)
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert service._volume == 40
    assert _steps(result)["service_volume"]["fixed"] is True


@pytest.mark.asyncio
async def test_a_stream_muted_by_a_remembered_role_is_unmuted(monkeypatch):
    """The fault from 1.6, seen from the repair side: the mute only shows up
    on a running stream, and the test tone is that stream."""
    service = _FakeService()
    mixer = _FakeMixer()
    mixer.muted_streams = ["194"]
    mixer.install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert mixer.muted_streams == []
    assert _steps(result)["stream_state"]["fixed"] is True


@pytest.mark.asyncio
async def test_running_it_twice_changes_nothing_the_second_time(monkeypatch):
    """The UI offers the button again after "no, still nothing"."""
    service = _FakeService(muted=True, volume=3, min_volume=10)
    mixer = _FakeMixer(muted=True, volume=2)
    mixer.install(monkeypatch)

    first = await ts.AudioTroubleshooter(service).run()
    assert first["fixed"], "nothing repaired on a box that was broken in four ways"

    second = await ts.AudioTroubleshooter(service).run()
    assert second["fixed"] == [], "the second run undid or redid the first one's work"


@pytest.mark.asyncio
async def test_the_fallback_prefers_an_output_the_user_allowed(monkeypatch):
    """enabled_output_devices is a deliberate choice, not an obstacle."""
    service = _FakeService(
        configured="wm8960",
        sinks=["hdmi", "headphones"],
        enabled=["wm8960", "headphones"],
    )
    _FakeMixer().install(monkeypatch)

    await ts.AudioTroubleshooter(service).run()

    assert service.switched_to == "headphones", "ignored the allowed output list"
    assert service.switch_allowed_disabled is False


@pytest.mark.asyncio
async def test_it_reaches_past_the_list_only_when_nothing_allowed_is_left(monkeypatch):
    """At that point the alternative is a box that stays silent, and the user
    pressed a button asking for that to stop."""
    service = _FakeService(
        configured="wm8960", sinks=["hdmi"], enabled=["wm8960", "headphones"]
    )
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert service.switched_to == "hdmi"
    assert service.switch_allowed_disabled is True
    assert "no allowed output" in _steps(result)["sink_present"]["detail"]


@pytest.mark.asyncio
async def test_a_failing_step_does_not_cost_the_tone(monkeypatch):
    """The tone at the end is what the user is waiting for, and the steps
    after a failed one may well be the ones that fix it."""
    service = _FakeService(configured="wm8960", sinks=["hdmi"], muted=True)

    async def _boom(sink_name=None, direction=None, *, allow_disabled=False):
        raise RuntimeError("re-init failed")

    service.switch_output_device = _boom
    _FakeMixer().install(monkeypatch)

    result = await ts.AudioTroubleshooter(service).run()

    assert _steps(result)["sink_present"]["ok"] is False
    assert service._muted is False, "the chain stopped at the first failure"
    assert service.tone_played == 1
