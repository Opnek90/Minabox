"""Language handling: what an unknown language does, and a missing voice file."""

from __future__ import annotations

from tts_service import voices


def test_a_regional_tag_is_still_that_language():
    assert voices.normalize_language("de-DE") == "de"
    assert voices.normalize_language("en_US") == "en"
    assert voices.normalize_language("DE") == "de"


def test_an_unknown_language_falls_back_rather_than_failing():
    """A settings field can hold anything; a silent box is the worse answer."""
    assert voices.normalize_language("fr") == voices.FALLBACK_LANGUAGE
    assert voices.normalize_language(None) == voices.FALLBACK_LANGUAGE
    assert voices.normalize_language("") == voices.FALLBACK_LANGUAGE


def test_a_missing_voice_file_is_reported_as_absent(tmp_path):
    assert voices.voice_path("de", tmp_path) is None
    assert voices.available_languages(tmp_path) == []


def test_only_the_languages_whose_file_is_there(tmp_path):
    (tmp_path / voices.DEFAULT_VOICES["de"]).write_bytes(b"x")
    assert voices.available_languages(tmp_path) == ["de"]


def test_the_environment_can_name_a_different_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_VOICE_DE", "de_DE-kerstin-low.onnx")
    (tmp_path / "de_DE-kerstin-low.onnx").write_bytes(b"x")
    assert voices.voice_path("de", tmp_path) == tmp_path / "de_DE-kerstin-low.onnx"
