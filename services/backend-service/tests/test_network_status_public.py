"""The network-status endpoint stays reachable when the admin area is locked.

The display service polls it without a session so it can show the address or
the fallback hotspot to reach the box on. If the auth middleware started
guarding it, the panel would go blank exactly when the user is locked out and
needs it most.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from backend_service.api import routes_host
from backend_service.middleware.auth import web_auth_middleware


@pytest.fixture
def app(monkeypatch):
    application = FastAPI()
    application.add_middleware(BaseHTTPMiddleware, dispatch=web_auth_middleware)
    application.include_router(routes_host.router, prefix="/api/v1/system")

    settings = {
        "web_password_hash": "$2b$12$dummydummydummy",
        "protected_areas": ["admin", "player", "media", "dashboard"],
    }
    monkeypatch.setattr(
        "backend_service.middleware.auth.read_auth_settings", lambda: settings
    )

    async def fake_proxy(*a, **k):
        return {"mode": "hotspot", "manage_url": "http://10.42.0.1"}

    monkeypatch.setattr(routes_host, "_proxy_optional", fake_proxy)
    return application


@pytest.mark.asyncio
async def test_network_status_is_reachable_without_a_session(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://box") as client:
        r = await client.get("/api/v1/system/network-status")
    assert r.status_code == 200
    assert r.json()["mode"] == "hotspot"


@pytest.mark.asyncio
async def test_a_sibling_system_route_still_requires_the_session(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://box") as client:
        r = await client.get("/api/v1/system/network")
    assert r.status_code == 401
