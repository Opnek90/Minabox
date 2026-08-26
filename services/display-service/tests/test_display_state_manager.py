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
        "track_id": None,
        "volume": 0,
        "min_volume": 0,
        "max_volume": 100,
        "volume_step": 0,
        "position_ms": 0,
        "duration_ms": None,
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
        "track_id": None,
        "volume": 42,
        # Absent from this payload, so the defaults stand.
        "min_volume": 0,
        "max_volume": 100,
        "volume_step": 0,
        "position_ms": 0,
        "duration_ms": None,
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


def test_the_error_expires_on_its_own():
    """The case that kept the icon up forever: an error, then nothing at all.

    The clock is injected rather than patched onto the time module: asyncio
    reads its event loop clock from there, so freezing it stops every await in
    the process and the render loop tests hang instead of failing.
    """
    clock = [1000.0]
    sm = _sm(error_timeout=300.0, clock=lambda: clock[0])

    sm.set_error()
    assert sm.has_error() is True

    clock[0] += 299.0
    assert sm.has_error() is True

    clock[0] += 2.0
    assert sm.has_error() is False


def test_a_new_error_restarts_the_timeout():
    clock = [1000.0]
    sm = _sm(error_timeout=300.0, clock=lambda: clock[0])

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
    sm.update_session("all", True, "Ein Lama in Yokohama")
    assert sm.get_session() == {
        "repeat_mode": "all",
        "shuffle": True,
        "current_title": "Ein Lama in Yokohama",
    }


# ---------------------------------------------------------------------------
# Volume bounds
# ---------------------------------------------------------------------------


def _status(**fields) -> str:
    return json.dumps({"state": "playing", "volume": 40, **fields})


def test_volume_bounds_come_from_the_status():
    sm = _sm()
    payload = _status(min_volume=0, max_volume=40, volume_step=5)
    sm.update_audio(STATUS, payload.encode())
    view = sm.get_volume_view()
    assert (view.min_volume, view.max_volume, view.step) == (0, 40, 5)
    assert view.percent == 100


def test_without_bounds_the_volume_is_read_as_a_percentage():
    """An audio service that does not send them yet must not break the HUD."""
    sm = _sm()
    sm.update_audio(STATUS, _status().encode())
    view = sm.get_volume_view()
    assert view.percent == 40
    assert not view.use_blocks  # step unknown, so a bar rather than wrong blocks


def test_a_narrower_maximum_changes_what_the_same_volume_means():
    sm = _sm()
    sm.update_audio(STATUS, _status(max_volume=80, volume_step=5).encode())
    assert sm.get_volume_view().percent == 50
    sm.update_audio(STATUS, _status(max_volume=40, volume_step=5).encode())
    assert sm.get_volume_view().percent == 100


def test_mute_reaches_the_view():
    sm = _sm()
    sm.update_audio(STATUS, _status(muted=True).encode())
    assert sm.get_volume_view().muted
