"""Tests for the release-manifest builder, and the guard it grew after #180.

The announcements went out as a beta bundle and the release that followed
promoted only half of it. Audio and host-helper kept their candidate, so CI -
which takes the tag from the VERSION file - never built a stable image of
either, and a box on the stable channel got a feature it could not reach.
Nothing said a word. These pin down the two things that say it now.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_manifest as bm  # noqa: E402


@pytest.fixture
def versions(monkeypatch):
    """Point the VERSION lookup at a dict instead of the working tree."""

    def install(mapping: dict[str, str]):
        monkeypatch.setattr(bm, "known_services", lambda: set(mapping))
        monkeypatch.setattr(bm, "current_version", lambda service: mapping[service])
        return set(mapping)

    return install


def tree(**services: dict[str, str]) -> dict:
    """A parsed changelog: {service: {version: {"date": ...}}}."""
    return {
        name: {version: {"date": date} for version, date in entries.items()}
        for name, entries in services.items()
    }


# ── The report ──────────────────────────────────────────────────────────────


def test_a_candidate_is_named_with_the_day_it_went_out(versions) -> None:
    known = versions({"audio": "0.3.0-rc.1", "backend": "0.7.0"})
    parsed = tree(
        audio={"0.3.0-rc.1": "2026-09-03", "0.2.4": "2026-08-28"},
        backend={"0.7.0": "2026-09-03"},
    )

    assert bm.parked_candidates(parsed, known) == [
        ("audio", "0.3.0-rc.1", "2026-09-03")
    ]


def test_nothing_to_report_when_everything_is_finished(versions) -> None:
    known = versions({"audio": "0.3.0", "backend": "0.7.0"})
    parsed = tree(audio={"0.3.0": "2026-09-03"}, backend={"0.7.0": "2026-09-03"})
    assert bm.parked_candidates(parsed, known) == []


def test_the_version_file_decides_not_the_changelog(versions) -> None:
    """Promoting is written both ways - as a second entry and as a replacement.

    The changelog therefore does not reliably say which candidates are still
    open. Here the candidate is still described, but the service has moved on;
    it must not be reported.
    """
    known = versions({"audio": "0.3.0"})
    parsed = tree(audio={"0.3.0": "2026-09-03", "0.3.0-rc.1": "2026-09-03"})
    assert bm.parked_candidates(parsed, known) == []


# ── The refusal ─────────────────────────────────────────────────────────────


def test_a_candidate_in_flight_is_not_an_error(versions) -> None:
    """One release day of grace: the bundle went out today, and so did its
    promotion. Crying wolf here is what gets a check ignored."""
    known = versions({"audio": "0.3.0-rc.1", "backend": "0.6.0", "tts": "0.1.0"})
    parsed = tree(
        audio={"0.3.0-rc.1": "2026-09-03"},
        backend={"0.6.0": "2026-09-03", "0.6.0-rc.1": "2026-09-03"},
        tts={"0.1.0": "2026-09-03"},
    )
    assert bm.check_parked_candidates(parsed, known) == []


def test_a_candidate_the_project_released_past_is_refused(versions) -> None:
    """The real incident, one release day later: everyone moved on, this one
    did not, and its image is never going to be built."""
    known = versions({"audio": "0.3.0-rc.1", "led": "0.2.4"})
    parsed = tree(
        audio={"0.3.0-rc.1": "2026-09-03"},
        led={"0.2.4": "2026-09-04", "0.2.3": "2026-08-20"},
    )

    problems = bm.check_parked_candidates(parsed, known)

    assert len(problems) == 1
    assert "audio is still on 0.3.0-rc.1 from 2026-09-03" in problems[0]
    assert "2026-09-04" in problems[0]


def test_another_candidate_published_later_does_not_count(versions) -> None:
    """Only a *finished* release means the project moved on. Two betas in
    flight are two betas in flight."""
    known = versions({"audio": "0.3.0-rc.1", "backend": "0.8.0-rc.1"})
    parsed = tree(
        audio={"0.3.0-rc.1": "2026-09-03"},
        backend={"0.8.0-rc.1": "2026-09-10"},
    )
    assert bm.check_parked_candidates(parsed, known) == []


def test_a_candidate_without_a_date_is_not_guessed_about(versions) -> None:
    known = versions({"audio": "0.3.0-rc.1", "led": "0.2.4"})
    parsed = tree(audio={}, led={"0.2.4": "2026-09-04"})
    assert bm.check_parked_candidates(parsed, known) == []
