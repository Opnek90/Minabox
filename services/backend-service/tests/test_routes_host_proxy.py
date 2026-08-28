"""Tests for the Host-Helper proxy helpers in routes_host.

These cover the behaviour that 44 endpoints now share, so a mistake here shows
up everywhere at once. The lazy-config case at the bottom is a regression that
a smoke test against the real Host-Helper caught: the rewrite had pulled
get_config() into the happy path, where the original never called it.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from backend_service.api import routes_host as rh


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("HOST_HELPER_API_KEY", "test-key")
    monkeypatch.setenv("HOST_HELPER_URL", "http://host-helper:8000")


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.setenv("HOST_HELPER_API_KEY", "")


@pytest.fixture
def fake_helper(monkeypatch):
    """Install a mock Host-Helper; the handler is set per test."""
    state = {"handler": None, "requests": []}

    def transport_handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return state["handler"](request)

    def install(handler):
        state["handler"] = handler
        client = httpx.AsyncClient(transport=httpx.MockTransport(transport_handler))
        monkeypatch.setattr(rh, "_client", client)
        return state

    yield install
    monkeypatch.setattr(rh, "_client", None)


# ── _proxy: strict ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proxy_returns_payload(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(200, json={"ok": True}))
    got = await rh._proxy("POST", "/reboot", error_message="x", error_code="test_failed", log_event="e")
    assert got == {"ok": True}


@pytest.mark.asyncio
async def test_proxy_without_key_is_503(no_api_key):
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/reboot", error_message="x", error_code="test_failed", log_event="e")
    assert exc.value.status_code == 503
    assert "HOST_HELPER_API_KEY" in exc.value.detail


@pytest.mark.asyncio
async def test_helper_401_is_reported_as_503(api_key, fake_helper):
    """A 401 must not reach the WebUI, which reads it as an expired session."""
    fake_helper(lambda r: httpx.Response(401, json={"detail": "bad key"}))
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/reboot", error_message="x", error_code="test_failed", log_event="e")
    assert exc.value.status_code == 503
    assert exc.value.detail == "Host-Helper authentication failed"


@pytest.mark.asyncio
async def test_client_errors_keep_their_status(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(400, json={"detail": "Invalid path"}))
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("PUT", "/system/network", error_message="fallback", error_code="test_failed", log_event="e")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid path"


@pytest.mark.asyncio
async def test_server_errors_are_capped_at_502(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(504, json={"detail": "timed out"}))
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/system/docker-prune", error_message="x", error_code="test_failed", log_event="e")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_error_message_is_used_when_body_is_empty(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(500))
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/x", error_message="Reboot failed", error_code="host_reboot_failed", log_event="e")
    assert exc.value.detail == "Reboot failed"


@pytest.mark.asyncio
async def test_non_json_error_body_does_not_explode(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(500, text="<html>nginx</html>"))
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/x", error_message="fallback", error_code="test_failed", log_event="e")
    assert "nginx" in exc.value.detail


@pytest.mark.asyncio
async def test_unreachable_helper_is_503(api_key, fake_helper):
    def boom(request):
        raise httpx.ConnectError("connection refused", request=request)

    fake_helper(boom)
    with pytest.raises(HTTPException) as exc:
        await rh._proxy("POST", "/reboot", error_message="x", error_code="test_failed", log_event="e")
    assert exc.value.status_code == 503


# ── _proxy_optional: soft ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_optional_returns_payload(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(200, json={"hostname": "phoniebox"}))
    got = await rh._proxy_optional("/system/hostname", fallback={"hostname": None}, log_event="e")
    assert got == {"hostname": "phoniebox"}


@pytest.mark.asyncio
async def test_optional_falls_back_without_key(no_api_key):
    got = await rh._proxy_optional("/system/hostname", fallback={"hostname": None}, log_event="e")
    assert got == {"hostname": None}


@pytest.mark.asyncio
async def test_optional_falls_back_on_error_status(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(503))
    got = await rh._proxy_optional("/system/ssh-status", fallback={"enabled": False}, log_event="e")
    assert got == {"enabled": False}


@pytest.mark.asyncio
async def test_optional_falls_back_when_unreachable(api_key, fake_helper):
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    fake_helper(boom)
    got = await rh._proxy_optional("/usb/devices", fallback={"devices": []}, log_event="e")
    assert got == {"devices": []}


@pytest.mark.asyncio
async def test_optional_fallback_is_copied_not_shared(api_key, no_api_key):
    """Callers must not be able to mutate the fallback for the next request."""
    fallback = {"devices": []}
    first = await rh._proxy_optional("/usb/devices", fallback=fallback, log_event="e")
    first["devices"].append("mutated")
    second = await rh._proxy_optional("/usb/devices", fallback=fallback, log_event="e")
    assert second == {"devices": []}


@pytest.mark.asyncio
async def test_network_status_passes_the_helper_payload_through(api_key, fake_helper):
    state = fake_helper(
        lambda r: httpx.Response(
            200,
            json={
                "mode": "hotspot",
                "hotspot": {"active": True, "ssid": "Minabox-Setup", "password": "pw"},
                "manage_url": "http://10.42.0.1",
            },
        )
    )
    got = await rh.get_network_status()
    assert got["mode"] == "hotspot"
    assert got["hotspot"]["password"] == "pw"
    assert state["requests"][0].url.path == "/network/status"


@pytest.mark.asyncio
async def test_network_status_falls_back_when_helper_is_down(api_key, fake_helper):
    fake_helper(lambda r: httpx.Response(503))
    got = await rh.get_network_status()
    assert got["mode"] == "unknown"
    assert got["stale"] is True


# ── Regression: config must stay lazy ────────────────────────────────────────


@pytest.mark.asyncio
async def test_audio_path_does_not_need_config_when_helper_answers(api_key, fake_helper, monkeypatch):
    """The happy path must not depend on the service config being loadable."""
    fake_helper(lambda r: httpx.Response(200, json={"audio_files_path": "/mnt/usb/musik"}))

    def exploding_get_config():
        raise AssertionError("get_config() must not be called on the happy path")

    monkeypatch.setattr(rh, "get_config", exploding_get_config)
    got = await rh.get_audio_path()
    assert got == {"path": "/mnt/usb/musik"}


@pytest.mark.asyncio
async def test_audio_path_uses_config_when_helper_has_none(api_key, fake_helper, monkeypatch):
    fake_helper(lambda r: httpx.Response(200, json={"audio_files_path": None}))

    class FakeConfig:
        class env:
            audio_storage_path = "/mnt/audio/tracks"

    monkeypatch.setattr(rh, "get_config", lambda: FakeConfig)
    got = await rh.get_audio_path()
    assert got == {"path": "/mnt/audio/tracks"}
