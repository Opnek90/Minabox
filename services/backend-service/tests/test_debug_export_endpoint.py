"""Endpoint tests for the debug export, including the auth middleware.

These cover the promises from docs/DebugExport.md 4.5, which are the reason the
route may live outside the password gate at all: private networks only, rate
limited, and the elevated tiers unreachable without a session.
"""

from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from backend_service.api import routes_debug
from backend_service.core.api_errors import ApiError, api_error_handler
from backend_service.middleware.auth import web_auth_middleware


@pytest.fixture
def app(monkeypatch):
    """Minimal app with the real middleware and the real route."""
    application = FastAPI()
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_middleware(BaseHTTPMiddleware, dispatch=web_auth_middleware)
    application.include_router(routes_debug.router, prefix="/api/v1/system")

    class _Config:
        device_id = "box1"

    monkeypatch.setattr(routes_debug, "get_config", lambda: _Config())
    # Keep the rate limiter from leaking between tests.
    monkeypatch.setattr(routes_debug, "_last_export_at", 0.0)
    return application


@pytest.fixture
def password_protected(monkeypatch):
    """Auth is on and covers the admin area - the locked-out user's situation."""
    settings = {
        "web_password_hash": "$2b$12$dummydummydummy",
        "protected_areas": ["admin"],
    }
    monkeypatch.setattr(routes_debug, "read_auth_settings", lambda: settings)
    monkeypatch.setattr(
        "backend_service.middleware.auth.read_auth_settings", lambda: settings
    )
    monkeypatch.setattr(routes_debug, "verify_session_token", lambda token: False)


@pytest.fixture(autouse=True)
def preview_in_tmp(monkeypatch, tmp_path):
    """Keep the preview cache out of the real data directory."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    routes_debug._drop_preview()
    yield
    routes_debug._drop_preview()


@pytest.fixture
def tiny_export(monkeypatch):
    """Replace the collector run with a stub - this file tests the guards."""

    async def fake_create_export(
        *, options, device_id, client_payload=None, versions=None, **kw
    ):
        buffer = io.BytesIO()
        manifest = {
            "options": options.as_manifest(),
            "secret_tripwire": {"blocked": []},
            "files": [
                {"path": "system/power.json", "bytes": 210},
                {"path": "services/audio/logs.txt", "bytes": 4096},
            ],
            "collectors": [{"name": "system.power", "status": "ok"}],
        }
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
        return buffer.getvalue(), manifest

    monkeypatch.setattr(routes_debug, "create_export", fake_create_export)


def _client(app, ip: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 51234))
    return httpx.AsyncClient(transport=transport, base_url="http://box.local")


def _manifest(payload: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return json.loads(archive.read("manifest.json"))


@pytest.mark.asyncio
async def test_export_works_without_login_from_the_local_network(
    app, password_protected, tiny_export
):
    """The whole point: reachable when the password itself is the problem."""
    async with _client(app, "192.168.1.42") as client:
        response = await client.get("/api/v1/system/debug-export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_is_refused_from_a_public_address(app, tiny_export):
    async with _client(app, "8.8.8.8") as client:
        response = await client.post("/api/v1/system/debug-export", json={})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_forwarded_for_header_cannot_fake_a_private_client(app, tiny_export):
    """The header is caller-controlled; only the peer address counts."""
    async with _client(app, "8.8.8.8") as client:
        response = await client.post(
            "/api/v1/system/debug-export",
            json={},
            headers={"X-Forwarded-For": "192.168.1.10"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_second_export_is_rate_limited(app, tiny_export):
    async with _client(app, "192.168.1.42") as client:
        first = await client.post("/api/v1/system/debug-export", json={})
        second = await client.post("/api/v1/system/debug-export", json={})
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_rate_limited_429_is_machine_readable(app, tiny_export):
    """The WebUI must tell the two 429 reasons apart without parsing German."""
    async with _client(app, "192.168.1.42") as client:
        await client.post("/api/v1/system/debug-export", json={})
        second = await client.post("/api/v1/system/debug-export", json={})
    assert second.status_code == 429
    body = second.json()
    assert body["code"] == "export_rate_limited"
    assert body["retry_after"] >= 0
    assert second.headers["Retry-After"]


@pytest.mark.asyncio
async def test_concurrent_export_reports_in_progress(app, tiny_export, monkeypatch):
    """Double-click: the second request must say "already running", not "just made one"."""

    class _HeldLock:
        def locked(self) -> bool:
            return True

    monkeypatch.setattr(routes_debug, "_export_lock", _HeldLock())
    async with _client(app, "192.168.1.42") as client:
        response = await client.post("/api/v1/system/debug-export", json={})
    assert response.status_code == 429
    assert response.json()["code"] == "export_in_progress"


@pytest.mark.asyncio
async def test_without_session_the_elevated_tiers_are_stripped(
    app, password_protected, tiny_export
):
    """A caller may ask for history and the database - and must not get them."""
    async with _client(app, "192.168.1.42") as client:
        response = await client.post(
            "/api/v1/system/debug-export",
            json={
                "options": {
                    "preset": "full",
                    "history": True,
                    "include_db": True,
                    "media": "filenames",
                }
            },
        )
    assert response.status_code == 200
    options = _manifest(response.content)["options"]
    assert options["history"] is False
    assert options["include_db"] is False
    assert options["media"] == "counts"


@pytest.mark.asyncio
async def test_with_valid_session_the_elevated_tiers_survive(
    app, monkeypatch, tiny_export
):
    settings = {
        "web_password_hash": "$2b$12$dummydummydummy",
        "protected_areas": ["admin"],
    }
    monkeypatch.setattr(routes_debug, "read_auth_settings", lambda: settings)
    monkeypatch.setattr(
        "backend_service.middleware.auth.read_auth_settings", lambda: settings
    )
    monkeypatch.setattr(routes_debug, "verify_session_token", lambda token: True)

    async with _client(app, "192.168.1.42") as client:
        client.cookies.set("minabox_session", "gueltig")
        response = await client.post(
            "/api/v1/system/debug-export",
            json={"options": {"preset": "full", "history": True}},
        )
    assert response.status_code == 200
    assert _manifest(response.content)["options"]["history"] is True


@pytest.mark.asyncio
async def test_options_endpoint_reports_the_callers_tier(app, password_protected):
    async with _client(app, "192.168.1.42") as client:
        response = await client.get("/api/v1/system/debug-export/options")
    assert response.status_code == 200
    payload = response.json()
    assert payload["elevated"] is False
    assert {"minimal", "recommended", "full"} == set(payload["presets"])


# ── Vorschau ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_lists_every_file_in_plain_language(app, tiny_export):
    async with _client(app, "192.168.1.42") as client:
        response = await client.post("/api/v1/system/debug-export/preview", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["export_id"]
    paths = {entry["path"]: entry for entry in payload["files"]}
    assert "system/power.json" in paths
    # Every entry carries a sentence a non-technical user can read.
    assert paths["system/power.json"]["description"] == "Stromversorgung und Temperatur"
    assert paths["services/audio/logs.txt"]["description"] == "Ablaufprotokoll von „audio“"
    assert paths["system/power.json"]["bytes"] == 210


@pytest.mark.asyncio
async def test_preview_hands_out_the_same_archive_without_rebuilding(app, tiny_export, monkeypatch):
    builds = {"count": 0}
    original = routes_debug.create_export

    async def counting(**kwargs):
        builds["count"] += 1
        return await original(**kwargs)

    monkeypatch.setattr(routes_debug, "create_export", counting)

    async with _client(app, "192.168.1.42") as client:
        preview = await client.post("/api/v1/system/debug-export/preview", json={})
        export_id = preview.json()["export_id"]
        download = await client.get(f"/api/v1/system/debug-export/download/{export_id}")

    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert builds["count"] == 1, "Download darf das Paket nicht erneut bauen"


@pytest.mark.asyncio
async def test_download_with_unknown_id_is_not_found(app):
    async with _client(app, "192.168.1.42") as client:
        response = await client.get("/api/v1/system/debug-export/download/gibtsnicht")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_is_refused_from_a_public_address(app, tiny_export):
    async with _client(app, "192.168.1.42") as client:
        preview = await client.post("/api/v1/system/debug-export/preview", json={})
        export_id = preview.json()["export_id"]
    async with _client(app, "8.8.8.8") as client:
        response = await client.get(f"/api/v1/system/debug-export/download/{export_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_preview_file_is_removed_after_download(app, tiny_export, tmp_path):
    async with _client(app, "192.168.1.42") as client:
        preview = await client.post("/api/v1/system/debug-export/preview", json={})
        export_id = preview.json()["export_id"]
        assert list((tmp_path / "tmp").glob("debug-export-*.zip"))
        await client.get(f"/api/v1/system/debug-export/download/{export_id}")
    # The archive must not linger on the SD card after it was handed out.
    assert not list((tmp_path / "tmp").glob("debug-export-*.zip"))
