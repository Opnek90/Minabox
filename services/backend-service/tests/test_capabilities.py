"""Tests for the optional-component capability contract.

Covers the three states the WebUI has to tell apart - not installed, installed
and healthy, installed but unavailable - plus the fail-open rule when
COMPOSE_PROFILES is missing, and the server-side guard that a direct API call
for an absent component is rejected consistently.
"""

from __future__ import annotations

import pytest

from backend_service.core import capabilities, container_registry
from backend_service.core.api_errors import ApiError

# --- installed_features() ---------------------------------------------------

def test_installed_features_from_profiles(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid,led,media")
    assert capabilities.installed_features() == {"rfid", "led", "media_downloader"}


def test_installed_features_ignores_whitespace_and_unknown(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", " rfid , , bogus ")
    assert capabilities.installed_features() == {"rfid"}


def test_installed_features_fail_open_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("COMPOSE_PROFILES", raising=False)
    assert capabilities.installed_features() == set(capabilities.OPTIONAL_FEATURES)


def test_installed_features_fail_open_when_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "   ")
    assert capabilities.installed_features() == set(capabilities.OPTIONAL_FEATURES)


# --- feature_states() ------------------------------------------------------

def _patch_discover(monkeypatch: pytest.MonkeyPatch, entries):
    async def fake_discover():
        return entries

    monkeypatch.setattr(container_registry, "discover", fake_discover)


@pytest.mark.asyncio
async def test_feature_states_not_installed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    _patch_discover(monkeypatch, [
        {"service": "rfid", "docker_status": "running", "state": "online"},
    ])
    states = await capabilities.feature_states()
    assert states["led"] == {"installed": False, "running": False, "healthy": False}
    assert states["media_downloader"]["installed"] is False


@pytest.mark.asyncio
async def test_feature_states_installed_and_healthy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    _patch_discover(monkeypatch, [
        {"service": "rfid", "docker_status": "running", "state": "online"},
    ])
    states = await capabilities.feature_states()
    assert states["rfid"] == {"installed": True, "running": True, "healthy": True}


@pytest.mark.asyncio
async def test_feature_states_installed_but_stopped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    _patch_discover(monkeypatch, [
        {"service": "rfid", "docker_status": "exited", "state": "error"},
    ])
    states = await capabilities.feature_states()
    assert states["rfid"] == {"installed": True, "running": False, "healthy": False}


@pytest.mark.asyncio
async def test_feature_states_installed_but_degraded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "led")
    _patch_discover(monkeypatch, [
        {"service": "led", "docker_status": "running", "state": "degraded"},
    ])
    states = await capabilities.feature_states()
    assert states["led"] == {"installed": True, "running": True, "healthy": False}


@pytest.mark.asyncio
async def test_feature_states_without_docker_mirrors_installed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid,button")
    _patch_discover(monkeypatch, None)
    states = await capabilities.feature_states()
    assert states["rfid"] == {"installed": True, "running": True, "healthy": True}
    assert states["led"] == {"installed": False, "running": False, "healthy": False}


# --- require_feature() ----------------------------------------------------

def test_require_feature_raises_409_when_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    with pytest.raises(ApiError) as exc_info:
        capabilities.require_feature("media_downloader")
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "feature_not_installed"


def test_require_feature_passes_when_installed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "media")
    capabilities.require_feature("media_downloader")  # must not raise


# --- endpoint & route guard ---------------------------------------------

def test_capabilities_endpoint_shape(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    _patch_discover(monkeypatch, [])
    resp = client.get("/api/v1/system/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == set(capabilities.OPTIONAL_FEATURES)
    assert body["rfid"]["installed"] is True
    assert body["display"]["installed"] is False


def test_validate_url_rejected_without_media_downloader(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "rfid")
    resp = client.get("/api/v1/tracks/validate-url", params={"url": "https://example.com/x"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "feature_not_installed"
