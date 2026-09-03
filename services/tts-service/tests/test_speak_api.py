"""The /speak endpoint: caching, refusals and what a broken Piper does to it."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tts_service import main, voices
from tts_service.synthesizer import VoicePool

# A stand-in for Piper in --json-input mode: one JSON line in, the file it
# names written, its path echoed back - which is how the real one says "done".
FAKE_PIPER = r"""#!/bin/sh
while IFS= read -r line; do
  out=$(printf '%s' "$line" | sed 's/.*"output_file": *"\([^"]*\)".*/\1/')
  printf 'RIFFdummy' > "$out"
  echo "$out"
done
"""


def _fake_piper(tmp_path, body=FAKE_PIPER):
    tmp_path.mkdir(parents=True, exist_ok=True)
    binary = tmp_path / "piper"
    binary.write_text(body)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return binary


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A service whose Piper is a shell script and whose cache is disposable."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    for name in voices.DEFAULT_VOICES.values():
        (voices_dir / name).write_bytes(b"x")

    monkeypatch.setattr(main.config, "voices_dir", voices_dir)
    monkeypatch.setattr(main.config, "cache_dir", tmp_path / "clips")
    # The pool is wired from the config at import, so it is replaced rather
    # than patched - the same wiring the app itself does.
    monkeypatch.setattr(
        main,
        "voices_pool",
        VoicePool(
            binary=_fake_piper(tmp_path),
            espeak_data=tmp_path / "espeak",
            timeout_sec=5.0,
        ),
    )
    with TestClient(main.app) as test_client:
        yield test_client


def test_a_phrase_is_synthesized_once_and_then_reused(client):
    first = client.post("/speak", json={"text": "Noch zehn Minuten.", "language": "de"})
    second = client.post("/speak", json={"text": "Noch zehn Minuten.", "language": "de"})

    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["path"] == first.json()["path"]
    assert Path(first.json()["path"]).exists()


def test_the_same_words_in_two_languages_are_two_clips(client):
    de = client.post("/speak", json={"text": "Hello", "language": "de"}).json()
    en = client.post("/speak", json={"text": "Hello", "language": "en"}).json()
    assert de["path"] != en["path"]
    assert de["voice"] != en["voice"]


def test_an_unknown_language_is_spoken_in_the_fallback(client):
    body = client.post("/speak", json={"text": "Bonjour", "language": "fr"}).json()
    assert body["language"] == voices.FALLBACK_LANGUAGE


def test_empty_text_is_refused(client):
    assert client.post("/speak", json={"text": "   "}).status_code == 422


def test_an_overlong_text_is_refused(client):
    """The API has no authentication, so the cap is enforced here as well."""
    long_text = "a" * (main.config.max_text_length + 1)
    assert client.post("/speak", json={"text": long_text}).status_code == 422


def test_a_missing_voice_answers_503_rather_than_500(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main.config, "voices_dir", tmp_path / "no-voices")
    response = client.post("/speak", json={"text": "Hallo", "language": "de"})
    assert response.status_code == 503


def test_a_broken_piper_answers_503(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        main,
        "voices_pool",
        VoicePool(
            binary=_fake_piper(tmp_path / "broken-dir", "#!/bin/sh\nexit 1\n"),
            espeak_data=tmp_path / "espeak",
            timeout_sec=5.0,
        ),
    )

    response = client.post("/speak", json={"text": "Kaputt", "language": "de"})
    assert response.status_code == 503


def test_health_says_degraded_without_a_voice(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main.config, "voices_dir", tmp_path / "empty")
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["languages"] == []


def test_voices_lists_what_is_installed(client):
    body = client.get("/voices").json()
    assert sorted(v["language"] for v in body["voices"]) == ["de", "en"]
