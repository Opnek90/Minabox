"""The clip cache: naming, and what pruning throws away."""

from __future__ import annotations

import os

from tts_service import cache


def test_same_text_and_voice_is_the_same_file():
    a = cache.clip_name("de_DE-thorsten-low.onnx", "Noch zehn Minuten.")
    b = cache.clip_name("de_DE-thorsten-low.onnx", "Noch zehn Minuten.")
    assert a == b
    assert a.endswith(".wav")


def test_the_voice_is_part_of_the_key():
    """The same sentence in two voices is two clips, not one overwritten one."""
    de = cache.clip_name("de_DE-thorsten-low.onnx", "Ten minutes left.")
    en = cache.clip_name("en_US-lessac-low.onnx", "Ten minutes left.")
    assert de != en


def test_a_name_with_slashes_stays_one_file(tmp_path):
    """Card names reach this from the database, so the file name is a hash."""
    path = cache.clip_path(tmp_path, "voice.onnx", "../../etc/passwd")
    assert path.parent == tmp_path


def _clip(directory, name: str, *, size: int, age_sec: float):
    path = directory / name
    path.write_bytes(b"\0" * size)
    stamp = path.stat().st_mtime - age_sec
    os.utime(path, (stamp, stamp))
    return path


def test_prune_drops_the_least_recently_used_first(tmp_path):
    old = _clip(tmp_path, "old.wav", size=10, age_sec=1000)
    fresh = _clip(tmp_path, "fresh.wav", size=10, age_sec=1)

    removed = cache.prune(tmp_path, max_files=1, max_bytes=10_000)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_prune_also_honours_the_byte_budget(tmp_path):
    _clip(tmp_path, "a.wav", size=100, age_sec=300)
    _clip(tmp_path, "b.wav", size=100, age_sec=200)
    keep = _clip(tmp_path, "c.wav", size=100, age_sec=100)

    cache.prune(tmp_path, max_files=100, max_bytes=100)

    assert keep.exists()
    assert sorted(p.name for p in tmp_path.glob("*.wav")) == ["c.wav"]


def test_prune_leaves_a_cache_that_fits_alone(tmp_path):
    _clip(tmp_path, "a.wav", size=10, age_sec=10)
    assert cache.prune(tmp_path, max_files=10, max_bytes=1000) == 0


def test_prune_survives_a_missing_directory(tmp_path):
    """A cache nobody created yet must not take an announcement down."""
    assert cache.prune(tmp_path / "gone", max_files=1, max_bytes=1) == 0


def test_touch_moves_a_clip_out_of_the_firing_line(tmp_path):
    old = _clip(tmp_path, "old.wav", size=10, age_sec=1000)
    _clip(tmp_path, "fresh.wav", size=10, age_sec=1)

    cache.touch(old)
    cache.prune(tmp_path, max_files=1, max_bytes=10_000)

    assert old.exists()
