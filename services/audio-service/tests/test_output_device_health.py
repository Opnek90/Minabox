"""/health has to notice when the configured output is gone.

From a real fault: the PN532 held the I2C
bus after a restart, the wm8960 codec probed once, failed and gave up, and the
sound card was simply no longer there. No sound came out of the box - while
/health reported

    {"status": "healthy", "mqtt_connected": true, "vlc_initialized": true}

and docker ps showed all ten containers green. Both conditions the endpoint
knew about were true; the one that mattered was never asked.
"""

from __future__ import annotations

import asyncio
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
from audio_service.core.service import AudioService  # noqa: E402


def _service(configured: str, detected: list[str]) -> AudioService:
    """An AudioService with only the parts check_output_device() touches."""
    service = object.__new__(AudioService)
    service._audio_config = AudioConfig(output_device_name=configured)
    service._get_audio_config = lambda: service._audio_config

    async def _devices(enabled_only: bool = False, *, force_refresh: bool = False):
        return [{"id": sink, "name": sink} for sink in detected]

    service.get_audio_devices = _devices
    return service


@pytest.mark.asyncio
async def test_the_configured_sink_is_there():
    service = _service("alsa_output.wm8960", ["alsa_output.wm8960"])
    available, name = await service.check_output_device()
    assert available is True
    assert name == "alsa_output.wm8960"


@pytest.mark.asyncio
async def test_the_sound_card_vanished():
    """The actual fault: only HDMI and the headphone jack were left."""
    service = _service(
        "alsa_output.wm8960",
        ["alsa_output.platform-bcm2835_audio.stereo-fallback", "alsa_output.hdmi"],
    )
    available, name = await service.check_output_device()
    assert available is False, "a missing sink must not pass as available"
    assert name == "alsa_output.wm8960"


@pytest.mark.asyncio
async def test_no_configured_output_cannot_be_missing():
    """An empty output_device_name means "host default sink" - nothing is
    pinned down, so nothing can be missing. Not a fault report."""
    available, name = await _service("", []).check_output_device()
    assert available is True
    assert name is None


@pytest.mark.asyncio
async def test_a_failed_lookup_is_not_a_missing_device():
    """Not being able to ask is not the same as the answer being no.

    Otherwise every hiccup in the sink detector would show up in the WebUI as
    a broken box.
    """
    service = _service("alsa_output.wm8960", [])

    async def _boom(enabled_only: bool = False, *, force_refresh: bool = False):
        raise RuntimeError("pactl not reachable")

    service.get_audio_devices = _boom

    available, name = await service.check_output_device()
    assert available is True
    assert name == "alsa_output.wm8960"


@pytest.mark.asyncio
async def test_a_slow_sink_lookup_does_not_hold_up_health():
    """The container health check gives /health 5 s, and the sink detector
    gives pactl 10 s. Without a cap of its own, a hung pactl would make Docker
    restart a service whose only problem was a slow sound server."""
    service = _service("alsa_output.wm8960", [])

    async def _hangs(enabled_only: bool = False, *, force_refresh: bool = False):
        await asyncio.sleep(30)
        return []

    service.get_audio_devices = _hangs

    started = asyncio.get_running_loop().time()
    available, name = await service.check_output_device()
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 5.0, "check_output_device() outlasted the container health check"
    assert available is True
    assert name == "alsa_output.wm8960"
