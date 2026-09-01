"""Shared fixtures for backend-service tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import backend_service.core.db_manager as db_module
from backend_service.api import api_router, routes_auth, routes_config, routes_tracks
from backend_service.api.websocket import websocket_endpoint
from backend_service.core import auth as auth_module
from backend_service.core import general_settings, system_alerts
from backend_service.core import track_metadata as track_metadata_module
from backend_service.core.api_errors import ApiError, api_error_handler
from backend_service.middleware.auth import web_auth_middleware


@pytest.fixture(autouse=True)
def _reset_current_alert():
    """The alert store is module-level state; keep tests independent."""
    system_alerts.clear_all()
    general_settings.invalidate()
    routes_tracks._backfill_status.update(
        running=False, total=0, processed=0, updated=0, online_used=0,
        finished_at=None, error=None,
    )
    yield
    system_alerts.clear_all()
    general_settings.invalidate()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point every filesystem and MQTT setting at a throwaway directory.

    Some paths are module-level constants evaluated at import time, so setting
    the environment variable alone is not enough - those are patched directly.
    """
    data = tmp_path / "data"
    audio = tmp_path / "audio"
    static = tmp_path / "static"
    for directory in (data, audio, static):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("MQTT_BROKER", "localhost")
    monkeypatch.setenv("MQTT_PORT", "1883")
    monkeypatch.setenv("MINABOX_DEVICE_ID", "testbox")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("DATA_PATH", str(data))
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(audio))
    monkeypatch.setenv("STATIC_DIR", str(static))
    monkeypatch.setenv("DATABASE_PATH", str(data / "minabox.db"))

    monkeypatch.setattr(routes_tracks, "STATIC_DIR", static)
    monkeypatch.setattr(routes_tracks, "COVERS_DIR", static / "covers")
    monkeypatch.setattr(routes_tracks, "AUDIO_STORAGE_PATH", audio)
    monkeypatch.setattr(track_metadata_module, "STATIC_DIR", static)
    monkeypatch.setattr(track_metadata_module, "COVERS_DIR", static / "covers")
    monkeypatch.setattr(routes_config, "STATIC_DIR", static)
    monkeypatch.setattr(routes_config, "GENERAL_SETTINGS_PATH", data / "general_settings.json")
    monkeypatch.setattr(auth_module, "AUTH_SETTINGS_PATH", data / "auth_settings.json")

    return {"data": data, "audio": audio, "static": static}


@pytest.fixture
def client(env):
    """A TestClient over the real router stack, on a fresh database."""
    db_module.init_db(str(env["data"] / "minabox.db"))

    # Login failures are module-level state keyed by client address, and every
    # test here arrives as the same "testclient" - without this a lockout in one
    # test would leak into the next.
    routes_auth.reset_login_failures()

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_middleware(BaseHTTPMiddleware, dispatch=web_auth_middleware)
    app.include_router(api_router)
    app.add_websocket_route("/ws", websocket_endpoint)

    with TestClient(app) as test_client:
        yield test_client

    routes_auth.reset_login_failures()

    if db_module.db_manager is not None:
        db_module.db_manager.disconnect()
    db_module.db_manager = None
