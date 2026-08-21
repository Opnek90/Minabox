"""Tests fuer das gezielte Update: Tag-Namen, .env-Schreiben, Log-Auswertung.

Die Funktionen entscheiden, welche Version eine Box nach dem Update faehrt.
Ein Fehler hier faellt erst auf, wenn ein Container mit dem falschen Abbild
startet - deshalb sind sie einzeln abgesichert.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Der Dienst laeuft im Container mit src/ auf dem Pfad.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from host_helper.api import routes  # noqa: E402


# ── Namen der Umgebungsvariablen ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ("backend", "MINABOX_BACKEND_TAG"),
        ("webui", "MINABOX_WEBUI_TAG"),
        # Der Bindestrich muss zum Unterstrich werden, sonst entsteht ein
        # Variablenname, den keine Shell und kein Compose je aufloest.
        ("host-helper", "MINABOX_HOST_HELPER_TAG"),
        ("media-downloader", "MINABOX_MEDIA_DOWNLOADER_TAG"),
    ],
)
def test_tag_var(service: str, expected: str) -> None:
    assert routes._tag_var(service) == expected


# ── .env schreiben und lesen ────────────────────────────────────────────────


def test_write_env_tags_replaces_and_appends(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "MQTT_BROKER=mqtt\nMINABOX_BACKEND_TAG=0.1.0\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )

    routes._write_env_tags(env, {"backend": "0.1.4", "webui": "0.1.4"})

    lines = env.read_text(encoding="utf-8").splitlines()
    assert "MINABOX_BACKEND_TAG=0.1.4" in lines
    assert "MINABOX_WEBUI_TAG=0.1.4" in lines
    # Nur ein Eintrag je Dienst - sonst gewinnt die letzte Zeile und der
    # Zustand haengt von der Reihenfolge ab.
    assert sum(1 for line in lines if line.startswith("MINABOX_BACKEND_TAG=")) == 1
    # Alles andere bleibt unangetastet.
    assert "MQTT_BROKER=mqtt" in lines
    assert "LOG_LEVEL=INFO" in lines


def test_write_env_tags_creates_missing_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    routes._write_env_tags(env, {"audio": "0.2.0"})
    assert env.read_text(encoding="utf-8").strip() == "MINABOX_AUDIO_TAG=0.2.0"


def test_read_env_tags_ignores_comments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "_service_names", lambda: ["backend", "webui"])
    env = tmp_path / ".env"
    env.write_text(
        "#MINABOX_BACKEND_TAG=0.0.1\nMINABOX_WEBUI_TAG=0.1.4\nMINABOX_AUDIO_TAG=9.9.9\n",
        encoding="utf-8",
    )

    tags = routes._read_env_tags(env)

    # Auskommentiert zaehlt nicht, und ein Dienst, den es nicht gibt, auch nicht.
    assert tags == {"webui": "0.1.4"}


# ── Fortschritt aus dem Log lesen ───────────────────────────────────────────


def test_parse_update_log_reports_the_last_step() -> None:
    log = "\n".join(
        [
            "=== MINABOX-STEP 1/5 backup",
            "  Sicherung: data/backups/pre-update-20260821.zip",
            "=== MINABOX-STEP 2/5 repo",
            "=== MINABOX-STEP 3/5 pull",
        ]
    )
    assert routes._parse_update_log(log) == {
        "step": 3,
        "step_count": 5,
        "step_key": "pull",
        "exit_code": None,
    }


def test_parse_update_log_reads_the_result() -> None:
    parsed = routes._parse_update_log(
        "=== MINABOX-STEP 5/5 verify\n=== MINABOX-DONE 0\n"
    )
    assert parsed["exit_code"] == 0


def test_parse_update_log_reads_a_failure() -> None:
    parsed = routes._parse_update_log(
        "=== MINABOX-STEP 3/5 pull\nfehler\n=== MINABOX-DONE 1\n"
    )
    assert parsed["exit_code"] == 1
    assert parsed["step_key"] == "pull"


def test_parse_update_log_of_an_empty_run() -> None:
    """Vor dem ersten Marker gibt es noch keinen Schritt - aber auch keinen Absturz."""
    parsed = routes._parse_update_log("")
    assert parsed["step"] is None
    assert parsed["exit_code"] is None
