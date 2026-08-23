"""Tests for the version comparison behind the update button.

The focus is on the two promises the module makes: it never claims an update
that nobody could verify, and it hides no release that was skipped along the
way.
"""

from __future__ import annotations

import pytest

from backend_service.core import update_check as uc

# ── Versionsvergleich ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("candidate", "installed", "expected"),
    [
        ("0.1.1", "0.1.0", True),
        ("0.2.0", "0.1.9", True),
        ("1.0.0", "0.9.9", True),
        ("0.1.0", "0.1.0", False),
        ("0.1.0", "0.1.1", False),
        # Two-digit numbers must not be compared as text,
        # otherwise 0.9.0 would count as newer than 0.10.0.
        ("0.10.0", "0.9.0", True),
        ("0.9.0", "0.10.0", False),
        # A pre-release is older than the finished version of the same number.
        ("0.2.0-rc.1", "0.2.0", False),
        ("0.2.0", "0.2.0-rc.1", True),
    ],
)
def test_is_newer(candidate: str, installed: str, expected: bool) -> None:
    assert uc.is_newer(candidate, installed) is expected


def test_parse_version_survives_nonsense() -> None:
    """A broken version string must not blow up the comparison."""
    assert uc.parse_version("keine-version") < uc.parse_version("0.0.1")


# ── Shape of the answer ────────────────────────────────────────────────────


def _manifest() -> dict:
    return {
        "schema": 1,
        "registry": "ghcr.io/opnek90",
        "services": {
            "backend": {
                "latest": "0.1.3",
                "releases": [
                    {"version": "0.1.3", "date": "2026-08-22", "notes": {}},
                    {"version": "0.1.2", "date": "2026-08-21", "notes": {}},
                    {"version": "0.1.1", "date": "2026-08-20", "notes": {}},
                ],
            },
            "audio": {
                "latest": "0.1.0",
                "releases": [{"version": "0.1.0", "date": "2026-08-20", "notes": {}}],
            },
        },
    }


def test_lists_every_skipped_release() -> None:
    """Skipping two releases has to show both of them."""
    entries = uc._build_entries(_manifest(), {"backend": "0.1.1"})
    backend = next(e for e in entries if e["service"] == "backend")
    assert backend["update_available"] is True
    assert [r["version"] for r in backend["releases"]] == ["0.1.3", "0.1.2"]


def test_current_service_reports_nothing_to_do() -> None:
    entries = uc._build_entries(_manifest(), {"audio": "0.1.0"})
    assert entries[0]["update_available"] is False
    assert entries[0]["releases"] == []


def test_unmanaged_service_is_shown_but_never_stale() -> None:
    """The MQTT broker comes from a third-party image and is not in the manifest."""
    entries = uc._build_entries(_manifest(), {"mqtt": "2.1.2"})
    assert entries[0]["managed"] is False
    assert entries[0]["update_available"] is False
    assert entries[0]["latest"] is None


def test_newer_installed_than_published_is_not_an_update() -> None:
    """A development Pi sometimes runs more than has been published."""
    entries = uc._build_entries(_manifest(), {"backend": "0.2.0"})
    assert entries[0]["update_available"] is False
    assert entries[0]["releases"] == []


# ── Ausfallverhalten ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_network_failure_never_claims_an_update(monkeypatch, tmp_path) -> None:
    """No network means no update hint - only a named failure."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")

    result = await uc.check({"backend": "0.1.0"}, force=True)

    assert result["update_available"] is False
    assert result["error"]
    assert [s["service"] for s in result["services"]] == ["backend"]


@pytest.mark.asyncio
async def test_failure_falls_back_to_the_last_known_state(monkeypatch, tmp_path) -> None:
    """An earlier result stays visible, but marked as a failure."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    uc._write_cache(
        {
            "cached_at": 0,  # expired, forces a fresh attempt
            "result": {
                "checked_at": "2026-08-21T10:00:00+00:00",
                "from_cache": False,
                "update_available": True,
                "error": None,
                "services": [{"service": "backend", "installed": "0.1.0"}],
            },
        }
    )
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")

    result = await uc.check({"backend": "0.1.0"}, force=False)

    assert result["from_cache"] is True
    assert result["error"]
    # The old state is kept - it was true at the time it was fetched.
    assert result["update_available"] is True
