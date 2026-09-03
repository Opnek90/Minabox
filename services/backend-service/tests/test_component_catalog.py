"""Tests for the catalogue of optional components (#181).

Three things decide whether the catalogue is any use: it describes a component
that this box does *not* have, it keeps working without the internet, and it
never offers a component that the local Compose file has no profile for.
"""

from __future__ import annotations

import json

import pytest

from backend_service.core import capabilities, component_catalog, general_settings

# The list the Host-Helper sends: a box that was installed with the card
# reader only.
HELPER_PAYLOAD = {
    "components": [
        {"profile": "rfid", "service": "rfid", "installed": True},
        {"profile": "media", "service": "media-downloader", "installed": False},
    ],
    "profiles": ["rfid"],
    "busy": False,
}

CONTAINERS = [
    {
        "service": "rfid",
        "version": "0.2.4",
        "docker_status": "running",
        "state": "online",
    },
]


@pytest.fixture(autouse=True)
def _data_path(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    return tmp_path


def _by_id(result: dict) -> dict[str, dict]:
    return {c["id"]: c for c in result["components"]}


def _profiles(result: dict) -> set[str]:
    """The addons that are a compose profile - the setting ones have none."""
    return {c["id"] for c in result["components"] if c["profile"]}


def test_describes_a_component_that_is_not_installed():
    # The whole point: media import is not on this box, and the entry still
    # says what it is for and that it needs the network.
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    media = _by_id(result)["media"]
    assert media["installed"] is False
    assert media["summary"]["de"] and media["summary"]["en"]
    assert media["network"] is True
    # Nothing to attach to the box for it.
    assert media["hardware"] is None


def test_the_name_travels_with_the_entry():
    # Without it, a component that the WebUI release on the box has never
    # heard of would appear under a raw translation key - and every new
    # component would need a WebUI release to be listed properly.
    listed = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )
    assert listed["media"]["name"] == {"de": "Medien-Import", "en": "Media import"}


def test_hardware_and_state_of_an_installed_component():
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    rfid = _by_id(result)["rfid"]
    assert "I2C" in rfid["hardware"]["en"]
    assert rfid["running"] is True and rfid["healthy"] is True
    # Its running version comes from the container, not from the manifest.
    assert rfid["version"] == "0.2.4"


def test_no_manifest_still_describes_everything():
    # A box that has never reached the internet has no remembered manifest.
    # The descriptions come out of the image, only the published version is
    # unknown.
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    for entry in result["components"]:
        assert entry["summary"] is not None
        assert entry["latest"] is None


def test_manifest_wins_over_the_bundled_text():
    component_catalog.remember(
        {
            "components": {
                "media": {
                    "service": "media-downloader",
                    "summary": {"de": "Neu beschrieben", "en": "Described anew"},
                    "hardware": None,
                    "network": True,
                }
            },
            "services": {"media-downloader": {"latest": "0.2.2"}},
        }
    )
    media = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["media"]
    assert media["summary"]["en"] == "Described anew"
    # And what switching it on would install.
    assert media["latest"] == "0.2.2"


def test_beta_names_the_candidate_stable_does_not():
    component_catalog.remember(
        {
            "components": {},
            "services": {
                "media-downloader": {"latest": "0.2.2", "latest_beta": "0.3.0-rc.1"}
            },
        }
    )
    stable = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["media"]
    beta = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="beta", entries=CONTAINERS)
    )["media"]
    assert stable["latest"] == "0.2.2"
    assert beta["latest"] == "0.3.0-rc.1"


def test_a_component_this_box_does_not_know_is_not_offered():
    # A newer manifest may describe something the local docker-compose.yml has
    # no profile for. Switching it on would write a profile that starts
    # nothing, so it stays out of the answer.
    component_catalog.remember(
        {
            "components": {
                "camera": {
                    "service": "camera",
                    "summary": {"de": "Kamera", "en": "Camera"},
                    "hardware": None,
                    "network": False,
                }
            },
            "services": {},
        }
    )
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    assert "camera" not in _by_id(result)


def test_without_the_host_helper_the_catalogue_still_lists_everything():
    # The maintenance page must still say what exists; only changing it is out
    # of reach, and `unreachable` is what says so.
    payload = {"components": [], "profiles": [], "busy": False, "unreachable": True}
    result = component_catalog.merge(payload, channel="stable", entries=CONTAINERS)
    listed = _by_id(result)
    assert _profiles(result) == set(capabilities.PROFILE_TO_FEATURE)
    assert listed["rfid"]["installed"] is True
    assert listed["display"]["installed"] is False
    assert result["unreachable"] is True


def test_a_broken_cache_costs_nothing(_data_path):
    (_data_path / component_catalog.CACHE_NAME).write_text("{ not json", encoding="utf-8")
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    assert _by_id(result)["rfid"]["summary"] is not None


def test_remember_keeps_only_the_versions(_data_path):
    # The release notes are the update check's business; carrying them here
    # would grow the file to the size of the manifest for nothing.
    component_catalog.remember(
        {
            "components": {},
            "services": {
                "rfid": {
                    "latest": "0.2.4",
                    "releases": [{"version": "0.2.4", "notes": {"added": {}}}],
                }
            },
        }
    )
    stored = json.loads(
        (_data_path / component_catalog.CACHE_NAME).read_text(encoding="utf-8")
    )
    assert stored["services"]["rfid"] == {"latest": "0.2.4", "latest_beta": None}


# ── Addons that are a setting, not a container ───────────────────────────────
#
# The container is a decision about how we build, not about what the user gets
# (see the module docstring). These check that the difference stays in the
# `install` field and does not leak into the shape of an entry.


def test_a_setting_addon_is_listed_like_any_other(_data_path):
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    metadata = _by_id(result)["metadata"]
    assert metadata["install"] == {
        "type": "setting",
        "field": "online_metadata_lookup_enabled",
    }
    assert metadata["summary"]["de"] and metadata["summary"]["en"]
    assert metadata["category"] == "software"
    assert metadata["network"] is True
    # Nothing to pull and nothing to update: it travels inside the backend.
    assert metadata["profile"] is None
    assert metadata["service"] is None
    assert metadata["version"] is None
    assert metadata["update_available"] is False


def test_a_setting_addon_reads_its_state_from_the_settings(_data_path):
    assert _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["metadata"]["installed"] is False

    (_data_path / "general_settings.json").write_text(
        json.dumps({"online_metadata_lookup_enabled": True}), encoding="utf-8"
    )
    general_settings.invalidate()
    entry = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["metadata"]
    assert entry["installed"] is True
    # No container that could be down, so being on is the whole state.
    assert entry["running"] is True
    assert entry["healthy"] is True


def test_a_setting_addon_whose_field_cannot_be_written_is_not_offered(_data_path):
    """A switch that springs back is worse than an addon that is not there."""
    component_catalog.remember(
        {
            "components": {
                "invented": {
                    "service": None,
                    "category": "software",
                    "install": {"type": "setting", "field": "not_a_real_setting"},
                    "name": {"en": "Invented"},
                    "summary": {"en": "From a newer manifest."},
                }
            },
            "services": {},
        }
    )
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    assert "invented" not in _by_id(result)


def test_the_category_falls_back_to_whether_an_accessory_is_named(_data_path):
    """A catalogue written before the field existed still sorts correctly."""
    component_catalog.remember(
        {
            "components": {
                "rfid": {
                    "service": "rfid",
                    "name": {"en": "Card reader"},
                    "summary": {"en": "Reads cards."},
                    "hardware": {"en": "A PN532 on the I2C pins."},
                },
                "media": {
                    "service": "media-downloader",
                    "name": {"en": "Media import"},
                    "summary": {"en": "Downloads audio."},
                    "hardware": None,
                },
            },
            "services": {},
        }
    )
    listed = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )
    assert listed["rfid"]["category"] == "hardware"
    assert listed["media"]["category"] == "software"


def test_an_update_is_only_offered_for_what_is_running(_data_path):
    component_catalog.remember(
        {
            "components": {},
            "services": {
                # Newer than the 0.2.4 the container reports.
                "rfid": {"latest": "0.3.0", "latest_beta": None},
                # Not on this box at all, so there is nothing to update.
                "media-downloader": {"latest": "0.9.9", "latest_beta": None},
            },
        }
    )
    listed = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )
    assert listed["rfid"]["update_available"] is True
    assert listed["rfid"]["latest"] == "0.3.0"
    assert listed["media"]["installed"] is False
    assert listed["media"]["update_available"] is False


def test_no_update_when_the_running_version_is_the_published_one(_data_path):
    component_catalog.remember(
        {"components": {}, "services": {"rfid": {"latest": "0.2.4"}}}
    )
    listed = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )
    assert listed["rfid"]["update_available"] is False


def test_a_manifest_does_not_blank_the_fields_it_predates(_data_path):
    """The manifest corrects a description; it does not replace an entry.

    Every box that has run an update check holds a remembered block from an
    older release. If that block replaced the bundled entry wholesale, it would
    blank every field the older release did not know yet - which is exactly
    what happened to `settings_section` on all six compose addons at once.
    """
    component_catalog.remember(
        {
            "components": {
                "rfid": {
                    "service": "rfid",
                    "name": {"de": "Kartenleser", "en": "Card reader"},
                    "summary": {"de": "Korrigiert", "en": "Corrected"},
                    "hardware": {"en": "A PN532 on the I2C pins."},
                    "network": False,
                }
            },
            "services": {},
        }
    )
    entry = _by_id(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["rfid"]
    # What the manifest says wins ...
    assert entry["summary"]["en"] == "Corrected"
    # ... and what it says nothing about survives from the bundled catalogue.
    assert entry["settings_section"] == "rfid"
    assert entry["category"] == "hardware"
    assert entry["install"] == {"type": "profile"}
