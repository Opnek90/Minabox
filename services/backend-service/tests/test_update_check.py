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


# ── Abhaengigkeiten zwischen Diensten (#194) ────────────────────────────────


def _requiring_manifest() -> dict:
    """media-downloader 0.2.2 needs backend 0.4.0; the backend is on offer."""
    return {
        "schema": 4,
        "registry": "ghcr.io/opnek90",
        "services": {
            "backend": {
                "latest": "0.4.0",
                "releases": [
                    {"version": "0.4.0", "date": "2026-09-01", "notes": {}},
                    {"version": "0.3.0", "date": "2026-08-30", "notes": {}},
                ],
            },
            "media-downloader": {
                "latest": "0.2.2",
                "releases": [
                    {
                        "version": "0.2.2",
                        "date": "2026-09-01",
                        "requires": {"backend": ">=0.4.0"},
                        "notes": {},
                    },
                    {"version": "0.2.1", "date": "2026-08-30", "notes": {}},
                ],
            },
        },
    }


def _settled(manifest: dict, installed: dict[str, str]) -> dict[str, dict]:
    entries = uc._build_entries(manifest, installed)
    uc._apply_requirements(manifest, entries, installed)
    return {e["service"]: e for e in entries}


def test_requirement_met_by_what_runs_says_nothing() -> None:
    """A box that is already new enough must not be told about a requirement."""
    entries = _settled(
        _requiring_manifest(), {"backend": "0.4.0", "media-downloader": "0.2.1"}
    )

    assert entries["media-downloader"]["update_available"] is True
    assert "requires_pull" not in entries["media-downloader"]
    assert "requires_unmet" not in entries["media-downloader"]


def test_the_required_service_is_taken_along() -> None:
    """Both are behind: the backend has to move in the same run."""
    entries = _settled(
        _requiring_manifest(), {"backend": "0.3.0", "media-downloader": "0.2.1"}
    )

    assert entries["media-downloader"]["update_available"] is True
    assert entries["media-downloader"]["requires_pull"] == [
        {"service": "backend", "version": "0.4.0"}
    ]


def test_a_requirement_nothing_can_meet_holds_the_update_back() -> None:
    """No newer backend on offer - so the candidate is not offered either."""
    manifest = _requiring_manifest()
    # The backend the box runs is the newest there is; it cannot go higher.
    manifest["services"]["backend"]["latest"] = "0.3.0"
    manifest["services"]["backend"]["releases"] = [
        {"version": "0.3.0", "date": "2026-08-30", "notes": {}}
    ]

    entries = _settled(manifest, {"backend": "0.3.0", "media-downloader": "0.2.1"})

    assert entries["media-downloader"]["update_available"] is False
    assert entries["media-downloader"]["requires_unmet"] == [
        {"service": "backend", "minimum": "0.4.0", "installed": "0.3.0"}
    ]
    # Same reasoning as pending_publish: no notes about what is not coming.
    assert entries["media-downloader"]["releases"] == []


def test_a_backend_held_back_by_the_registry_takes_its_dependant_with_it() -> None:
    """The pull-along only counts while the other update is real."""
    manifest = _requiring_manifest()
    installed = {"backend": "0.3.0", "media-downloader": "0.2.1"}
    entries = uc._build_entries(manifest, installed)
    by_service = {e["service"]: e for e in entries}
    # What the registry check does when CI has not pushed the image yet.
    by_service["backend"]["update_available"] = False
    by_service["backend"]["pending_publish"] = True

    uc._apply_requirements(manifest, entries, installed)

    assert by_service["media-downloader"]["update_available"] is False
    assert by_service["media-downloader"]["requires_unmet"][0]["service"] == "backend"


def test_a_requirement_on_a_service_the_box_lacks_is_met() -> None:
    """No container, no combination that could be split."""
    entries = _settled(_requiring_manifest(), {"media-downloader": "0.2.1"})

    assert entries["media-downloader"]["update_available"] is True
    assert "requires_unmet" not in entries["media-downloader"]


def test_an_unreadable_requirement_is_ignored_not_guessed_at() -> None:
    """A manifest from a future that writes ranges must not block this box."""
    manifest = _requiring_manifest()
    manifest["services"]["media-downloader"]["releases"][0]["requires"] = {
        "backend": "^0.4.0"
    }

    entries = _settled(manifest, {"backend": "0.3.0", "media-downloader": "0.2.1"})

    assert entries["media-downloader"]["update_available"] is True
    assert "requires_unmet" not in entries["media-downloader"]


def test_the_running_version_reports_what_it_needs() -> None:
    """The rollback lock reads this, so it is about the running build."""
    entries = _settled(
        _requiring_manifest(), {"backend": "0.4.0", "media-downloader": "0.2.2"}
    )

    assert entries["media-downloader"]["requires"] == {"backend": "0.4.0"}
    assert entries["backend"]["requires"] == {}


def test_companions_walk_the_chain(tmp_path, monkeypatch) -> None:
    """A service pulled in brings its own requirement along."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    uc._write_cache(
        {
            "cached_at": 0,
            "result": {
                "services": [
                    {
                        "service": "webui",
                        "requires_pull": [
                            {"service": "media-downloader", "version": "0.2.2"}
                        ],
                    },
                    {
                        "service": "media-downloader",
                        "requires_pull": [{"service": "backend", "version": "0.4.0"}],
                    },
                    {"service": "backend"},
                ]
            },
        }
    )

    assert uc.companions({"webui": "0.6.0"}) == {
        "media-downloader": "0.2.2",
        "backend": "0.4.0",
    }


def test_companions_without_a_cached_answer_add_nothing(tmp_path, monkeypatch) -> None:
    """Before the first check there is no requirement this box knows of."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    assert uc.companions({"webui": "0.6.0"}) == {}


def test_declared_requirements_reads_the_running_versions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    uc._write_cache(
        {
            "cached_at": 0,
            "result": {
                "services": [
                    {"service": "media-downloader", "requires": {"backend": "0.4.0"}},
                    {"service": "backend", "requires": {}},
                ]
            },
        }
    )

    assert uc.declared_requirements() == {"media-downloader": {"backend": "0.4.0"}}
