"""Tests for audio state persistence.

The box is designed to be unplugged at any moment, so a half-written state
file must never be possible: save() writes to a temp file and renames it.
"""

from __future__ import annotations

import json

import pytest

from audio_service.core.state_manager import AudioState, StateManager
from audio_service.exceptions import StateError


def test_save_creates_parent_directory(tmp_path):
    sm = StateManager(tmp_path / "nested" / "deeper" / "audio_state.json")
    sm.save(AudioState(last_track_id="7"))
    assert (tmp_path / "nested" / "deeper" / "audio_state.json").exists()


def test_save_leaves_no_temp_files_behind(tmp_path):
    target = tmp_path / "audio_state.json"
    sm = StateManager(target)
    for i in range(5):
        sm.save(AudioState(last_track_id=str(i)))
    assert [p.name for p in tmp_path.iterdir()] == ["audio_state.json"]


def test_saved_file_is_always_complete_json(tmp_path):
    target = tmp_path / "audio_state.json"
    sm = StateManager(target)
    sm.save(AudioState(last_track_id="42", last_position_ms=90_000, last_volume=55))
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["last_track_id"] == "42"
    assert data["last_position_ms"] == 90_000
    assert data["last_volume"] == 55


def test_overwrite_never_truncates_the_previous_file(tmp_path):
    """os.replace is atomic, so a reader sees either the old or the new file."""
    target = tmp_path / "audio_state.json"
    sm = StateManager(target)
    sm.save(AudioState(last_track_id="old", last_position_ms=1))
    before = target.read_text(encoding="utf-8")
    sm.save(AudioState(last_track_id="new", last_position_ms=2))
    after = target.read_text(encoding="utf-8")
    assert json.loads(before)["last_track_id"] == "old"
    assert json.loads(after)["last_track_id"] == "new"


def test_load_falls_back_to_defaults_on_corrupt_file(tmp_path):
    target = tmp_path / "audio_state.json"
    target.write_text('{"last_track_id": "trunc', encoding="utf-8")
    state = StateManager(target).load()
    assert state.last_track_id is None
    assert state.last_state == "stopped"


def test_round_trip(tmp_path):
    target = tmp_path / "audio_state.json"
    StateManager(target).save(AudioState(last_track_id="9", last_volume=33))
    loaded = StateManager(target).load()
    assert loaded.last_track_id == "9"
    assert loaded.last_volume == 33


def test_save_reports_failure_as_state_error(tmp_path):
    # A path whose parent cannot be created (a file sits where a dir must go).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    sm = StateManager(blocker / "audio_state.json")
    with pytest.raises(StateError):
        sm.save(AudioState())
