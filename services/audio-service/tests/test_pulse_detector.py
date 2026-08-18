"""Tests for Pulse sink detection and its cache.

detect_sinks() used to shell out to `pactl` on every call, and the audio status
loop calls it every 2 seconds - forever. The cache keeps that off the CPU while
still letting explicit queries and device switches see fresh data.
"""

from __future__ import annotations

import pytest

from audio_service.infrastructure import pulse_detector as pd
from audio_service.infrastructure.pulse_detector import PulseSink, PulseSinkDetector

PACTL_OUTPUT = """Sink #0
\tName: alsa_output.platform-soc_sound.stereo-fallback
\tDescription: Built-in Audio
\tProperties:
\t\tnode.nick = "WM8960"
\t\talsa.card_name = "wm8960-soundcard"
Sink #1
\tName: bluez_output.AA_BB_CC_DD_EE_FF.1
\tDescription: JBL Speaker
\tProperties:
\t\tnode.nick = "JBL Go"
"""


@pytest.fixture
def detector(monkeypatch):
    monkeypatch.setenv("PULSE_SERVER", "unix:/run/pulse/native")
    return PulseSinkDetector()


def _count_calls(monkeypatch, detector, output=PACTL_OUTPUT):
    calls = {"n": 0}

    def fake_blocking():
        calls["n"] += 1
        return detector._parse_pactl_output(output)

    monkeypatch.setattr(detector, "_detect_sinks_blocking", fake_blocking)
    return calls


def test_parses_name_and_prefers_nick(detector):
    sinks = detector._parse_pactl_output(PACTL_OUTPUT)
    assert [s.sink_name for s in sinks] == [
        "alsa_output.platform-soc_sound.stereo-fallback",
        "bluez_output.AA_BB_CC_DD_EE_FF.1",
    ]
    assert sinks[0].name == "WM8960"
    assert sinks[1].name == "JBL Go"


def test_returns_empty_without_pulse_server(monkeypatch):
    monkeypatch.delenv("PULSE_SERVER", raising=False)
    assert __import__("asyncio").run(PulseSinkDetector().detect_sinks()) == []


@pytest.mark.asyncio
async def test_second_call_is_served_from_cache(detector, monkeypatch):
    calls = _count_calls(monkeypatch, detector)
    first = await detector.detect_sinks()
    second = await detector.detect_sinks()
    assert calls["n"] == 1, "pactl must run once, not per call"
    assert [s.sink_name for s in first] == [s.sink_name for s in second]


@pytest.mark.asyncio
async def test_status_loop_pattern_runs_pactl_once(detector, monkeypatch):
    """Simulates the 2s status loop: many calls, one subprocess."""
    calls = _count_calls(monkeypatch, detector)
    for _ in range(30):
        await detector.detect_sinks()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_force_bypasses_the_cache(detector, monkeypatch):
    calls = _count_calls(monkeypatch, detector)
    await detector.detect_sinks()
    await detector.detect_sinks(force=True)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_invalidate_forces_a_refresh(detector, monkeypatch):
    calls = _count_calls(monkeypatch, detector)
    await detector.detect_sinks()
    detector.invalidate()
    await detector.detect_sinks()
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_cache_expires_after_ttl(detector, monkeypatch):
    calls = _count_calls(monkeypatch, detector)
    await detector.detect_sinks()
    # Pretend the cache was filled longer ago than the TTL allows.
    detector._cached_at -= pd.CACHE_TTL_SECONDS + 1
    await detector.detect_sinks()
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_caller_cannot_mutate_the_cache(detector, monkeypatch):
    _count_calls(monkeypatch, detector)
    first = await detector.detect_sinks()
    first.append(PulseSink("x", "x", "x", 99))
    second = await detector.detect_sinks()
    assert len(second) == 2
