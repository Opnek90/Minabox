"""Tests for the version comparison behind the update button.

The focus is on the two promises the module makes: it never claims an update
that nobody could verify, and it hides no release that was skipped along the
way.
"""

from __future__ import annotations

import time

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


# ── Kanäle ──────────────────────────────────────────────────────────────────


def _channel_manifest() -> dict:
    """A service with a candidate open on top of a finished release."""
    return {
        "schema": 2,
        "registry": "ghcr.io/opnek90",
        "services": {
            "backend": {
                "latest": "0.1.3",
                "latest_beta": "0.2.0-rc.1",
                "releases": [
                    {
                        "version": "0.2.0-rc.1",
                        "date": "2026-08-24",
                        "channel": "beta",
                        "notes": {},
                    },
                    {
                        "version": "0.1.3",
                        "date": "2026-08-22",
                        "channel": "stable",
                        "notes": {},
                    },
                ],
            },
            # No candidate open - beta must still be offered the finished one.
            "audio": {
                "latest": "0.1.0",
                "releases": [
                    {
                        "version": "0.1.0",
                        "date": "2026-08-20",
                        "channel": "stable",
                        "notes": {},
                    }
                ],
            },
        },
    }


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.2.0", "stable"), ("0.2.0-rc.1", "beta"), ("", "stable")],
)
def test_channel_of(version: str, expected: str) -> None:
    assert uc.channel_of(version) == expected


@pytest.mark.parametrize(
    "value", ["", None, "Stable", "nightly", "  beta  ", 7]
)
def test_clamp_channel_only_ever_yields_a_known_channel(value: object) -> None:
    assert uc.clamp_channel(value) in uc.CHANNELS


def test_clamp_channel_reads_beta() -> None:
    assert uc.clamp_channel("beta") == "beta"
    assert uc.clamp_channel("BETA") == "beta"


def test_stable_never_sees_a_candidate() -> None:
    """The point of the stable channel: a release candidate does not exist."""
    entries = uc._build_entries(_channel_manifest(), {"backend": "0.1.2"}, "stable")

    backend = entries[0]
    assert backend["latest"] == "0.1.3"
    assert [r["version"] for r in backend["releases"]] == ["0.1.3"]


def test_beta_is_offered_the_candidate() -> None:
    entries = uc._build_entries(_channel_manifest(), {"backend": "0.1.2"}, "beta")

    backend = entries[0]
    assert backend["latest"] == "0.2.0-rc.1"
    assert backend["update_available"] is True
    # Both, and the candidate first - the notes of the skipped release matter
    # just as much on beta.
    assert [r["version"] for r in backend["releases"]] == ["0.2.0-rc.1", "0.1.3"]


def test_beta_falls_back_to_stable_where_no_candidate_is_open() -> None:
    """A service without a candidate must not drop off the beta list."""
    entries = uc._build_entries(_channel_manifest(), {"audio": "0.0.9"}, "beta")

    assert entries[0]["latest"] == "0.1.0"
    assert entries[0]["update_available"] is True


def test_beta_is_never_behind_stable() -> None:
    """A finished release published after the last candidate wins on beta too."""
    manifest = {
        "services": {
            "backend": {
                "latest": "0.2.0",
                "latest_beta": "0.2.0-rc.1",
                "releases": [],
            }
        }
    }
    entries = uc._build_entries(manifest, {"backend": "0.1.0"}, "beta")
    assert entries[0]["latest"] == "0.2.0"


def test_running_build_reports_its_own_channel() -> None:
    """A box that switched back to stable still shows its beta build as one."""
    entries = uc._build_entries(_channel_manifest(), {"backend": "0.2.0-rc.1"}, "stable")
    assert entries[0]["channel"] == "beta"


@pytest.mark.asyncio
async def test_cached_answer_of_another_channel_is_not_reused(
    monkeypatch, tmp_path
) -> None:
    """After a switch the cache names the versions of the channel left behind."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")
    monkeypatch.setattr(uc, "read_update_channel", lambda: "beta")
    uc._write_cache(
        {
            "cached_at": time.time(),  # fresh, so only the channel can reject it
            "result": {
                "checked_at": "2026-08-21T10:00:00+00:00",
                "from_cache": False,
                "update_available": False,
                "channel": "stable",
                "error": None,
                "services": [],
            },
        }
    )

    result = await uc.check({"backend": "0.1.0"}, force=False)

    # The fetch was attempted and failed - which is the proof that the fresh
    # cache entry was not simply handed back.
    assert result["error"]


# ── Wahlkomponenten ─────────────────────────────────────────────────────────
#
# Switching a component off removes its container, so it drops out of the
# `installed` map. The cache lives six hours and does not notice on its own -
# it kept listing the component and kept offering an update that "compose
# pull" could no longer carry out, because the profile is gone.


@pytest.mark.asyncio
async def test_cached_answer_for_other_components_is_not_reused(
    monkeypatch, tmp_path
) -> None:
    """A component switched off must not linger in the list for six hours."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")
    monkeypatch.setattr(uc, "read_update_channel", lambda: "stable")
    uc._write_cache(
        {
            "cached_at": time.time(),  # fresh, so only the service set can reject it
            "result": {
                "checked_at": "2026-08-21T10:00:00+00:00",
                "from_cache": False,
                "update_available": True,
                "channel": "stable",
                "error": None,
                "services": [
                    {"service": "backend", "installed": "0.1.0"},
                    {"service": "display", "installed": "0.3.0"},
                ],
            },
        }
    )

    result = await uc.check({"backend": "0.1.0"}, force=False)

    # The fetch was attempted and failed - which is the proof that the fresh
    # cache entry was not simply handed back.
    assert result["error"]
    # And the fallback drops what the box no longer has.
    assert [s["service"] for s in result["services"]] == ["backend"]


@pytest.mark.asyncio
async def test_a_component_switched_back_on_is_not_read_from_the_cache(
    monkeypatch, tmp_path
) -> None:
    """The other direction: a component that is back has no cached entry."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")
    monkeypatch.setattr(uc, "read_update_channel", lambda: "stable")
    uc._write_cache(
        {
            "cached_at": time.time(),
            "result": {
                "checked_at": "2026-08-21T10:00:00+00:00",
                "from_cache": False,
                "update_available": False,
                "channel": "stable",
                "error": None,
                "services": [{"service": "backend", "installed": "0.1.0"}],
            },
        }
    )

    result = await uc.check({"backend": "0.1.0", "display": "0.3.0"}, force=False)

    assert result["error"]


@pytest.mark.asyncio
async def test_an_unchanged_box_still_answers_from_the_cache(
    monkeypatch, tmp_path
) -> None:
    """The check must not turn into a fetch on every call."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("MINABOX_MANIFEST_URL", "http://127.0.0.1:9/manifest.json")
    monkeypatch.setattr(uc, "read_update_channel", lambda: "stable")
    uc._write_cache(
        {
            "cached_at": time.time(),
            "result": {
                "checked_at": "2026-08-21T10:00:00+00:00",
                "from_cache": False,
                "update_available": False,
                "channel": "stable",
                "error": None,
                "services": [{"service": "backend", "installed": "0.1.0"}],
            },
        }
    )

    result = await uc.check({"backend": "0.1.0"}, force=False)

    assert result["from_cache"] is True
    assert result["error"] is None


def test_dropping_a_component_withdraws_its_update(tmp_path) -> None:
    """The header hint hangs off update_available, so it has to be recomputed."""
    result = {
        "update_available": True,
        "services": [
            {"service": "backend", "installed": "0.1.0", "update_available": False},
            {"service": "display", "installed": "0.3.0", "update_available": True},
        ],
    }

    trimmed = uc._only_installed(result, {"backend": "0.1.0"})

    assert [s["service"] for s in trimmed["services"]] == ["backend"]
    # Without this the box would keep pointing at an update for a component it
    # no longer has.
    assert trimmed["update_available"] is False
