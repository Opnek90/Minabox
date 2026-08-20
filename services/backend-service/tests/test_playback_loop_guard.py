"""Tests for the end-of-content behaviour and its loop guard.

Covers the three configurable outcomes once the last track has finished
(`stop`, `repeat`, `repeat_while_tag`) and the safety net that keeps a card
left on the reader from playing for hours.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_service.core import playback_settings as ps
from backend_service.core.handlers.button_handler import ButtonHandler
from backend_service.core.session_manager import SessionManager


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the settings readers at a throwaway general_settings.json."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    def write(**values: object) -> None:
        (tmp_path / "general_settings.json").write_text(
            json.dumps(values), encoding="utf-8"
        )

    return write


class FakeTrack:
    """Stands in for the ORM Track that create_session snapshots."""

    def __init__(self, track_id: int) -> None:
        self.id = track_id
        self.source_type = "file"
        self.source_uri = f"/music/{track_id}.mp3"
        self.title = f"Track {track_id}"
        self.artist = ""
        self.album = ""


class FakeRFIDHandler:
    def __init__(self, tag_present: bool) -> None:
        self.tag_present = tag_present


class FakeDispatcher:
    def __init__(self, tag_present: bool = True) -> None:
        self.rfid_handler = FakeRFIDHandler(tag_present)


# ---------------------------------------------------------------------------
# Settings parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("repeat", "repeat"),
        ("repeat_while_tag", "repeat_while_tag"),
        ("stop", "stop"),
        ("nonsense", "stop"),
        (None, "stop"),
        (7, "stop"),
    ],
)
def test_clamp_end_behavior(raw: object, expected: str) -> None:
    assert ps.clamp_end_behavior(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),
        (-5, 0),
        (1, ps.MIN_LOOP_GUARD_MINUTES),
        (60, 60),
        (99999, ps.MAX_LOOP_GUARD_MINUTES),
        ("abc", ps.DEFAULT_LOOP_GUARD_MINUTES),
    ],
)
def test_clamp_loop_guard_minutes(raw: object, expected: int) -> None:
    assert ps.clamp_loop_guard_minutes(raw) == expected


def test_settings_default_to_stop_without_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    assert ps.read_playback_end_behavior() == "stop"
    assert ps.read_loop_guard_minutes() == ps.DEFAULT_LOOP_GUARD_MINUTES


def test_settings_are_read_fresh(settings_file) -> None:
    settings_file(playback_end_behavior="repeat", playback_loop_guard_minutes=90)
    assert ps.read_playback_end_behavior() == "repeat"
    assert ps.read_loop_guard_minutes() == 90
    # A change in the WebUI must take effect without a restart.
    settings_file(playback_end_behavior="stop", playback_loop_guard_minutes=0)
    assert ps.read_playback_end_behavior() == "stop"
    assert ps.read_loop_guard_minutes() == 0


# ---------------------------------------------------------------------------
# Session picks up the configured default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("behavior", "repeat_mode", "requires_tag"),
    [
        ("stop", "none", False),
        ("repeat", "all", False),
        ("repeat_while_tag", "all", True),
    ],
)
def test_create_session_applies_end_behavior(
    settings_file, behavior: str, repeat_mode: str, requires_tag: bool
) -> None:
    settings_file(playback_end_behavior=behavior)
    manager = SessionManager()
    session = manager.create_session(tracks=[FakeTrack(1), FakeTrack(2)])
    assert session.repeat_mode == repeat_mode
    assert session.loop_requires_tag is requires_tag
    assert session.loop_started_at is None


def test_manual_repeat_overrides_the_card_rule(settings_file) -> None:
    settings_file(playback_end_behavior="repeat_while_tag")
    manager = SessionManager()
    manager.create_session(tracks=[FakeTrack(1)])
    manager.session.mark_loop_started()

    manager.set_repeat_mode("all")

    assert manager.session.loop_requires_tag is False
    assert manager.session.loop_started_at is None


# ---------------------------------------------------------------------------
# The decision at the end of the last track
# ---------------------------------------------------------------------------


def _session_for(settings_file, behavior: str):
    settings_file(playback_end_behavior=behavior, playback_loop_guard_minutes=60)
    manager = SessionManager()
    manager.create_session(tracks=[FakeTrack(1)])
    return manager.session


def test_stop_behavior_does_not_loop(settings_file) -> None:
    handler = ButtonHandler(FakeDispatcher())
    session = _session_for(settings_file, "stop")
    assert handler._loop_decision(session) == (False, "no_repeat")


def test_repeat_behavior_loops(settings_file) -> None:
    handler = ButtonHandler(FakeDispatcher(tag_present=False))
    session = _session_for(settings_file, "repeat")
    # Plain repeat does not care about the card.
    assert handler._loop_decision(session) == (True, "")


def test_repeat_while_tag_needs_the_card(settings_file) -> None:
    session = _session_for(settings_file, "repeat_while_tag")

    on_reader = ButtonHandler(FakeDispatcher(tag_present=True))
    assert on_reader._loop_decision(session) == (True, "")

    taken_off = ButtonHandler(FakeDispatcher(tag_present=False))
    assert taken_off._loop_decision(session) == (False, "tag_removed")


def test_loop_guard_stops_an_overlong_loop(settings_file, monkeypatch) -> None:
    handler = ButtonHandler(FakeDispatcher())
    session = _session_for(settings_file, "repeat")

    # First pass: the guard window has not even started yet.
    assert handler._loop_decision(session) == (True, "")

    session.mark_loop_started()
    monkeypatch.setattr(session, "loop_elapsed_seconds", lambda: 59 * 60)
    assert handler._loop_decision(session) == (True, "")

    monkeypatch.setattr(session, "loop_elapsed_seconds", lambda: 61 * 60)
    assert handler._loop_decision(session) == (False, "loop_guard")


def test_loop_guard_can_be_switched_off(settings_file, monkeypatch) -> None:
    settings_file(playback_end_behavior="repeat", playback_loop_guard_minutes=0)
    manager = SessionManager()
    session = manager.create_session(tracks=[FakeTrack(1)])
    session.mark_loop_started()
    monkeypatch.setattr(session, "loop_elapsed_seconds", lambda: 100 * 3600)

    handler = ButtonHandler(FakeDispatcher())
    assert handler._loop_decision(session) == (True, "")
