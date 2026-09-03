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


# ── Rollback: was zurueckgenommen werden darf ────────────────────────────────

# The history is written by the Host-Helper, the decision is made here: only
# this service knows the database schema its own build expects.


def _history(schema_version: int | None) -> list[dict]:
    return [
        {
            "id": "2026-08-30T10:00:00+00:00",
            "started_at": "2026-08-30T10:00:00+00:00",
            "kind": "update",
            "previous": {"backend": "0.2.12", "audio": "0.2.3"},
            "targets": {"backend": "0.2.13", "audio": "0.2.4"},
            "schema_version": schema_version,
        }
    ]


def test_rollback_candidate_is_the_version_before_the_last_change():
    candidates = rh._rollback_candidates(
        _history(rh.SCHEMA_VERSION), {"backend": "0.2.13", "audio": "0.2.4"}
    )
    assert {c["service"]: c["target"] for c in candidates} == {
        "backend": "0.2.12",
        "audio": "0.2.3",
    }
    assert all(c["allowed"] for c in candidates)


def test_no_candidate_for_a_service_that_did_not_move():
    """The recorded version is the running one - there is nothing to go back to."""
    candidates = rh._rollback_candidates(
        _history(rh.SCHEMA_VERSION), {"backend": "0.2.12"}
    )
    assert candidates == []


def test_a_service_without_history_is_not_offered():
    candidates = rh._rollback_candidates(_history(rh.SCHEMA_VERSION), {"led": "0.2.3"})
    assert candidates == []


def test_the_first_matching_entry_wins():
    """Two steps back is a different promise about the data written since."""
    entries = [
        {"started_at": "b", "previous": {"backend": "0.2.12"}, "schema_version": rh.SCHEMA_VERSION},
        {"started_at": "a", "previous": {"backend": "0.2.11"}, "schema_version": rh.SCHEMA_VERSION},
    ]
    candidates = rh._rollback_candidates(entries, {"backend": "0.2.13"})
    assert [c["target"] for c in candidates] == ["0.2.12"]


def test_a_migrated_database_blocks_the_backend():
    """The older code would look for its data where the newer one no longer puts it."""
    candidates = rh._rollback_candidates(
        _history(rh.SCHEMA_VERSION - 1), {"backend": "0.2.13", "audio": "0.2.4"}
    )
    backend = next(c for c in candidates if c["service"] == "backend")
    assert backend["allowed"] is False
    assert backend["reason"] == "schema_changed"
    # Only the backend reads the database; a version per service is the point.
    audio = next(c for c in candidates if c["service"] == "audio")
    assert audio["allowed"] is True


def test_history_without_a_schema_version_does_not_block():
    """Recorded before this field existed - unknown is not the same as changed."""
    candidates = rh._rollback_candidates(_history(None), {"backend": "0.2.13"})
    assert candidates[0]["allowed"] is True


@pytest.mark.asyncio
async def test_rollback_refuses_a_service_with_no_recorded_version(api_key, fake_helper, monkeypatch):
    fake_helper(lambda r: httpx.Response(200, json={"entries": [], "running": {}}))
    with pytest.raises(HTTPException) as exc:
        await rh.rollback(rh.RollbackBody(services=["backend"]))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_rollback_refuses_across_a_migration(api_key, fake_helper):
    fake_helper(
        lambda r: httpx.Response(
            200,
            json={
                "entries": _history(rh.SCHEMA_VERSION - 1),
                "running": {"backend": "0.2.13"},
            },
        )
    )
    with pytest.raises(HTTPException) as exc:
        await rh.rollback(rh.RollbackBody(services=["backend"]))
    assert exc.value.status_code == 409
    assert "migrated" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_rollback_sends_the_recorded_tags(api_key, fake_helper):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/update-history"):
            return httpx.Response(
                200,
                json={
                    "entries": _history(rh.SCHEMA_VERSION),
                    "running": {"backend": "0.2.13", "audio": "0.2.4"},
                },
            )
        return httpx.Response(200, json={"ok": True})

    state = fake_helper(handler)
    got = await rh.rollback(rh.RollbackBody(services=["audio"]))

    assert got == {"ok": True}
    started = [r for r in state["requests"] if r.url.path.endswith("/update-minabox")]
    assert len(started) == 1
    import json as _json

    body = _json.loads(started[0].content)
    # Exactly the one service, on exactly the recorded tag - and labelled, so
    # the history says what kind of run it was.
    assert body["targets"] == {"audio": "0.2.3"}
    assert body["kind"] == "rollback"
    assert body["schema_version"] == rh.SCHEMA_VERSION


@pytest.mark.asyncio
async def test_rollback_without_a_service_is_rejected(api_key):
    with pytest.raises(HTTPException) as exc:
        await rh.rollback(rh.RollbackBody(services=[]))
    assert exc.value.status_code == 400


# ── Optional components ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_components_are_answered_as_a_catalogue(api_key, fake_helper):
    """The Host-Helper says which profiles are set; the answer says what they are."""
    payload = {
        "components": [{"profile": "rfid", "service": "rfid", "installed": True}],
        "profiles": ["rfid"],
        "busy": False,
    }
    fake_helper(lambda r: httpx.Response(200, json=payload))

    got = await rh.get_components()

    assert got["profiles"] == ["rfid"] and got["busy"] is False
    entry = got["components"][0]
    assert entry["profile"] == "rfid" and entry["installed"] is True
    # What the catalogue adds: what it is for, and what it needs (#181).
    assert entry["summary"]["en"]
    assert entry["hardware"]["en"]
    assert entry["network"] is False


@pytest.mark.asyncio
async def test_components_without_the_helper_do_not_break_the_page(no_api_key):
    """The maintenance page has to open even when nothing can be changed there.

    The catalogue is still worth reading then - only the switches are out of
    reach, which is what `unreachable` says.
    """
    got = await rh.get_components()
    assert {c["profile"] for c in got["components"]} == {
        "rfid",
        "led",
        "button",
        "display",
        "media",
        "voice",
    }
    assert got["unreachable"] is True


@pytest.mark.asyncio
async def test_put_components_sends_the_profiles(api_key, fake_helper):
    state = fake_helper(lambda r: httpx.Response(200, json={"ok": True, "changed": True}))

    got = await rh.put_components(rh.ComponentsBody(profiles=["rfid", "media"]))

    assert got["changed"] is True
    import json as _json

    sent = [r for r in state["requests"] if r.url.path.endswith("/system/components")]
    assert len(sent) == 1
    assert sent[0].method == "PUT"
    assert _json.loads(sent[0].content) == {"profiles": ["rfid", "media"]}


@pytest.mark.asyncio
async def test_components_status_survives_the_restart(no_api_key):
    """The run recreates this very service - a failed poll is not an error."""
    got = await rh.get_components_status()
    assert got["running"] is True
    assert got["unreachable"] is True
