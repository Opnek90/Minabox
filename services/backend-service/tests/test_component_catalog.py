"""Tests for the catalogue of optional components (#181).

Three things decide whether the catalogue is any use: it describes a component
that this box does *not* have, it keeps working without the internet, and it
never offers a component that the local Compose file has no profile for.
"""

from __future__ import annotations

import json

import pytest

from backend_service.core import capabilities, component_catalog

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


def _by_profile(result: dict) -> dict[str, dict]:
    return {c["profile"]: c for c in result["components"]}


def test_describes_a_component_that_is_not_installed():
    # The whole point: media import is not on this box, and the entry still
    # says what it is for and that it needs the network.
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    media = _by_profile(result)["media"]
    assert media["installed"] is False
    assert media["summary"]["de"] and media["summary"]["en"]
    assert media["network"] is True
    # Nothing to attach to the box for it.
    assert media["hardware"] is None


def test_hardware_and_state_of_an_installed_component():
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    rfid = _by_profile(result)["rfid"]
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
    media = _by_profile(
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
    stable = _by_profile(
        component_catalog.merge(HELPER_PAYLOAD, channel="stable", entries=CONTAINERS)
    )["media"]
    beta = _by_profile(
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
    assert "camera" not in _by_profile(result)


def test_without_the_host_helper_the_catalogue_still_lists_everything():
    # The maintenance page must still say what exists; only changing it is out
    # of reach, and `unreachable` is what says so.
    payload = {"components": [], "profiles": [], "busy": False, "unreachable": True}
    result = component_catalog.merge(payload, channel="stable", entries=CONTAINERS)
    listed = _by_profile(result)
    assert set(listed) == set(capabilities.PROFILE_TO_FEATURE)
    assert listed["rfid"]["installed"] is True
    assert listed["display"]["installed"] is False
    assert result["unreachable"] is True


def test_a_broken_cache_costs_nothing(_data_path):
    (_data_path / component_catalog.CACHE_NAME).write_text("{ not json", encoding="utf-8")
    result = component_catalog.merge(
        HELPER_PAYLOAD, channel="stable", entries=CONTAINERS
    )
    assert _by_profile(result)["rfid"]["summary"] is not None


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
