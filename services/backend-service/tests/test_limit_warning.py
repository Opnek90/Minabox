"""How long is left, and when the box says so.

The limits themselves have a moment to hang off - a card scan, a track
boundary. A *warning* does not: it has to arrive while the music is still
playing, which is what the timer this covers is for.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend_service.core.usage_limits import minutes_until_usage_window_ends

MONDAY_15_00 = datetime(2026, 9, 7, 15, 0)


def _slot(weekday: int, start: str, end: str) -> dict:
    return {"weekday": weekday, "start": start, "end": end}


def test_no_slots_means_no_end_in_sight():
    assert minutes_until_usage_window_ends(MONDAY_15_00, []) is None


def test_outside_every_window_there_is_nothing_to_count_down():
    """The card was already refused; a countdown would be nonsense."""
    slots = [_slot(0, "07:00", "12:00")]
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) is None


def test_inside_a_window_counts_to_its_end():
    slots = [_slot(0, "07:00", "19:00")]
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) == 240


def test_a_window_on_another_weekday_does_not_count():
    slots = [_slot(0, "07:00", "19:00"), _slot(1, "07:00", "23:00")]
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) == 240


def test_a_window_past_midnight_ends_the_next_day():
    slots = [_slot(0, "14:00", "02:00")]
    # 15:00 -> 02:00 is nine hours and, from here, eleven.
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) == 11 * 60


def test_two_touching_windows_are_one_stretch():
    """To the child in the room they are; the longer one decides."""
    slots = [_slot(0, "07:00", "16:00"), _slot(0, "14:00", "19:00")]
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) == 240


def test_a_malformed_slot_is_skipped_not_raised():
    slots = [{"weekday": 0, "start": "nonsense", "end": "19:00"}]
    assert minutes_until_usage_window_ends(MONDAY_15_00, slots) is None


# --- the timer itself -------------------------------------------------------


class _Dispatcher:
    def __init__(self) -> None:
        self.playback_intent_active = True
        self.mqtt_client = object()


@pytest.fixture
def handler(monkeypatch, tmp_path):
    from backend_service.core import general_settings
    from backend_service.core.handlers.timer_handler import TimerHandler

    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("COMPOSE_PROFILES", "voice")
    general_settings.invalidate()
    yield TimerHandler(_Dispatcher())
    general_settings.invalidate()


def _settings(tmp_path, **values):
    import json

    from backend_service.core import general_settings

    (tmp_path / "general_settings.json").write_text(
        json.dumps({"announcements_enabled": True, **values}), encoding="utf-8"
    )
    general_settings.invalidate()


def test_no_limits_means_no_warning(handler, tmp_path, monkeypatch):
    _settings(tmp_path)
    handler.start_limit_warning()
    assert handler.limit_warning_task is None


@pytest.mark.asyncio
async def test_the_warning_is_scheduled_while_time_is_left(
    handler, tmp_path, monkeypatch
):
    """Whatever is left, it is the smaller of the two limits - see
    minutes_of_listening_left, stood in for here."""
    _settings(tmp_path)
    monkeypatch.setattr(handler, "minutes_of_listening_left", lambda now: 5)
    handler.start_limit_warning()
    assert handler.limit_warning_task is not None
    handler.cancel_limit_warning()
    assert handler.limit_warning_task is None


def test_an_announcement_switched_off_schedules_nothing(handler, tmp_path):
    _settings(tmp_path, announce_usage_limit=False)
    handler.start_limit_warning()
    assert handler.limit_warning_task is None


def test_a_lead_time_of_zero_switches_the_warning_off(handler, tmp_path):
    _settings(tmp_path, announce_limit_warning_minutes=0)
    handler.start_limit_warning()
    assert handler.limit_warning_task is None


def test_nothing_is_scheduled_once_the_time_is_already_up(
    handler, tmp_path, monkeypatch
):
    """Past the limit is not a warning any more - it is the limit itself."""
    _settings(tmp_path)
    monkeypatch.setattr(handler, "minutes_of_listening_left", lambda now: 0)
    handler.start_limit_warning()
    assert handler.limit_warning_task is None
