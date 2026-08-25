"""The cached state behind every rendered frame.

The error flag is the part worth pinning down. It used to be cleared by exactly
one thing -- an incoming audio/status -- and the audio service only publishes
that when the status actually changed. So an error on an otherwise idle box left
the icon on the panel indefinitely.
"""

from __future__ import annotations

import json

from display_service.core.state_manager import StateManager


def _sm(**kwargs) -> StateManager:
    return StateManager("box1", **kwargs)


STATUS = "minabox/box1/audio/status"


# ---------------------------------------------------------------------------
# Audio state
# ---------------------------------------------------------------------------


def test_defaults_are_safe_to_render():
    audio = _sm().get_audio()
    assert audio == {
        "state": "stopped",
        "volume": 0,
        "muted": False,
        "multiple_output_devices": False,
        "bluetooth_sink_available": False,
    }


def test_audio_status_is_cached():
    sm = _sm()
    sm.update_audio(
        STATUS,
        json.dumps(
            {
                "state": "playing",
                "volume": 42,
                "muted": True,
                "multiple_output_devices": True,
                "bluetooth_sink_available": True,
            }
        ).encode(),
    )
    assert sm.get_audio() == {
        "state": "playing",
        "volume": 42,
        "muted": True,
        "multiple_output_devices": True,
        "bluetooth_sink_available": True,
    }


def test_other_topics_are_ignored():
    sm = _sm()
    sm.update_audio("minabox/box1/audio/error", b'{"volume": 99}')
    assert sm.get_audio()["volume"] == 0


def test_a_malformed_payload_leaves_the_cache_intact():
    sm = _sm()
    sm.update_audio(STATUS, b'{"volume": 42, "state": "playing"}')
    sm.update_audio(STATUS, b"not json at all")
    assert sm.get_audio()["volume"] == 42
    assert sm.get_audio()["state"] == "playing"


def test_a_partial_payload_falls_back_to_defaults():
    sm = _sm()
    sm.update_audio(STATUS, b'{"state": "paused"}')
    audio = sm.get_audio()
    assert audio["state"] == "paused"
    assert audio["volume"] == 0
    assert audio["muted"] is False


def test_the_returned_dict_is_a_copy():
    sm = _sm()
    sm.get_audio()["volume"] = 99
    assert sm.get_audio()["volume"] == 0


# ---------------------------------------------------------------------------
# The error flag
# ---------------------------------------------------------------------------


def test_no_error_by_default():
    assert _sm().has_error() is False


def test_set_error_raises_the_flag():
    sm = _sm()
    sm.set_error()
    assert sm.has_error() is True


def test_an_audio_status_clears_the_error():
    sm = _sm()
    sm.set_error()
    sm.update_audio(STATUS, b'{"state": "playing"}')
    assert sm.has_error() is False


def test_a_malformed_status_still_clears_the_error():
    """The flag is cleared before parsing - a status arrived, whatever it said."""
    sm = _sm()
    sm.set_error()
    sm.update_audio(STATUS, b"not json")
    assert sm.has_error() is False


def test_the_error_expires_on_its_own(monkeypatch):
    """The case that kept the icon up forever: an error, then nothing at all."""
    clock = [1000.0]
    monkeypatch.setattr(
        "display_service.core.state_manager.time.monotonic", lambda: clock[0]
    )
    sm = _sm(error_timeout=300.0)

    sm.set_error()
    assert sm.has_error() is True

    clock[0] += 299.0
    assert sm.has_error() is True

    clock[0] += 2.0
    assert sm.has_error() is False


def test_a_new_error_restarts_the_timeout(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(
        "display_service.core.state_manager.time.monotonic", lambda: clock[0]
    )
    sm = _sm(error_timeout=300.0)

    sm.set_error()
    clock[0] += 299.0
    sm.set_error()
    clock[0] += 299.0
    assert sm.has_error() is True


# ---------------------------------------------------------------------------
# Sleep timer and session
# ---------------------------------------------------------------------------


def test_sleep_timer_round_trip():
    sm = _sm()
    sm.update_sleep_timer(True, 120_000)
    assert sm.get_sleep_timer() == {"active": True, "remaining_ms": 120_000}


def test_sleep_timer_can_go_inactive():
    sm = _sm()
    sm.update_sleep_timer(True, 120_000)
    sm.update_sleep_timer(False, None)
    assert sm.get_sleep_timer() == {"active": False, "remaining_ms": None}


def test_session_round_trip():
    sm = _sm()
    sm.update_session("all", True)
    assert sm.get_session() == {"repeat_mode": "all", "shuffle": True}
