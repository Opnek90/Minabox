"""What audio/status carries, and when it is republished.

The volume bounds are in the payload because max_volume is a hard clamp: at
the stop this service reports the configured maximum, not 100. Without the
bounds a subscriber cannot tell "40" at max from "40" halfway up a box
configured to 80.
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
from audio_service.core.mqtt_handler import DEFAULT_VOLUME_STEP  # noqa: E402
from audio_service.core.service import AudioService  # noqa: E402
from audio_service.infrastructure.audio_backend import (  # noqa: E402
    AudioStatus,
    PlaybackState,
)


class _FakeBackend:
    def __init__(self, status: AudioStatus) -> None:
        self._status = status

    async def get_status(self) -> AudioStatus:
        return self._status


class _FakeMQTT:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic, payload, **kwargs) -> None:
        self.published.append((topic, payload))


class _FakeConfig:
    @staticmethod
    def get_mqtt_topic(service: str, leaf: str) -> str:
        return f"minabox/{service}/{leaf}"


def _service(volume: int = 40, **audio_overrides) -> tuple[AudioService, _FakeMQTT]:
    """An AudioService with only the parts _publish_status actually touches."""
    audio = AudioConfig(
        **{"min_volume": 0, "max_volume": 40, "default_volume": 20, **audio_overrides}
    )
    status = AudioStatus(
        state=PlaybackState.PLAYING,
        track_id="t1",
        source_type="file",
        source_uri="/music/a.mp3",
        position_ms=1000,
        duration_ms=60000,
        volume=volume,
    )
    mqtt = _FakeMQTT()
    service = object.__new__(AudioService)
    service._vlc_backend = _FakeBackend(status)
    service._mqtt_client = mqtt
    service._config = _FakeConfig()
    service._muted = False
    service._last_published_fingerprint = None
    service._audio_config = audio
    service._get_audio_config = lambda: service._audio_config

    async def _no_devices(enabled_only: bool = False):
        return []

    service.get_audio_devices = _no_devices
    return service, mqtt


@pytest.mark.asyncio
async def test_bounds_and_step_are_published():
    service, mqtt = _service(volume=40)
    await service._publish_status()

    _, payload = mqtt.published[-1]
    assert payload["volume"] == 40
    assert payload["min_volume"] == 0
    assert payload["max_volume"] == 40
    assert payload["volume_step"] == DEFAULT_VOLUME_STEP


@pytest.mark.asyncio
async def test_the_raw_volume_alone_is_ambiguous():
    """Same reported volume, different meaning - only the bounds separate them."""
    at_max, mqtt_max = _service(volume=40, max_volume=40)
    await at_max._publish_status()
    halfway, mqtt_half = _service(volume=40, max_volume=80)
    await halfway._publish_status()

    assert mqtt_max.published[-1][1]["volume"] == mqtt_half.published[-1][1]["volume"]
    assert mqtt_max.published[-1][1]["max_volume"] != (
        mqtt_half.published[-1][1]["max_volume"]
    )


@pytest.mark.asyncio
async def test_an_unchanged_status_is_not_republished():
    service, mqtt = _service()
    await service._publish_status()
    await service._publish_status(force=False)
    assert len(mqtt.published) == 1


@pytest.mark.asyncio
async def test_a_new_maximum_reaches_subscribers_immediately():
    """Without the bounds in the fingerprint this would wait for the next track."""
    service, mqtt = _service(volume=40)
    await service._publish_status()

    service._audio_config = AudioConfig(
        min_volume=0, max_volume=80, default_volume=20
    )
    await service._publish_status(force=False)

    assert len(mqtt.published) == 2
    assert mqtt.published[-1][1]["max_volume"] == 80
