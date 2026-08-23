"""Smoke tests that exercise the REST layer through a real ASGI app.

Everything else in this suite tests functions in isolation. Nothing started the
FastAPI application, so the routing, the response models, the error handler and
the auth middleware were never covered - and neither were the paths where a
route touches the filesystem. Both defects these tests pin down (deleting a
track without a stored file, and an unbounded upload) lived in exactly that gap.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import backend_service.core.db_manager as db_module
from backend_service.api import api_router, routes_config, routes_tracks
from backend_service.api.routes_auth import COOKIE_NAME
from backend_service.core import auth as auth_module
from backend_service.core.api_errors import ApiError, api_error_handler
from backend_service.middleware.auth import web_auth_middleware


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
    monkeypatch.setattr(routes_config, "STATIC_DIR", static)
    monkeypatch.setattr(routes_config, "GENERAL_SETTINGS_PATH", data / "general_settings.json")
    monkeypatch.setattr(auth_module, "AUTH_SETTINGS_PATH", data / "auth_settings.json")

    return {"data": data, "audio": audio, "static": static}


@pytest.fixture
def client(env):
    """A TestClient over the real router stack, on a fresh database."""
    db_module.init_db(str(env["data"] / "minabox.db"))

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_middleware(BaseHTTPMiddleware, dispatch=web_auth_middleware)
    app.include_router(api_router)

    with TestClient(app) as test_client:
        yield test_client

    if db_module.db_manager is not None:
        db_module.db_manager.disconnect()
    db_module.db_manager = None


def _make_track(client, **overrides) -> dict:
    body = {
        "title": "Test track",
        "source_type": "file",
        "source_uri": "/tmp/does-not-matter.mp3",
    }
    body.update(overrides)
    response = client.post("/api/v1/tracks", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- Routing and error shape ------------------------------------------------


def test_health_reports_the_service(client):
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "backend"
    assert body["database_connected"] is True


def test_unknown_id_returns_detail_and_code(client):
    response = client.get("/api/v1/tracks/999999")
    assert response.status_code == 404
    body = response.json()
    # The WebUI translates `code`; `detail` is the developer-facing text.
    assert body["code"] == "track_not_found"
    assert "999999" in body["detail"]


def test_folder_route_is_not_swallowed_by_the_id_route(client):
    """`/tracks/folders` must not be matched as `/tracks/{track_id}`."""
    response = client.get("/api/v1/tracks/folders")
    assert response.status_code == 200
    assert response.json() == []


# --- Tags -------------------------------------------------------------------


def test_tag_crud_roundtrip(client):
    created = client.post(
        "/api/v1/tags",
        json={"tag_id": "04A224BC19", "name": "Bibi", "content_type": "track", "content_id": 1},
    )
    assert created.status_code == 201, created.text

    listed = client.get("/api/v1/tags")
    assert [t["tag_id"] for t in listed.json()] == ["04A224BC19"]

    updated = client.put("/api/v1/tags/04A224BC19", json={"name": "Bibi Blocksberg"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Bibi Blocksberg"

    duplicate = client.post(
        "/api/v1/tags",
        json={"tag_id": "04A224BC19", "content_type": "track", "content_id": 1},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "tag_already_exists"

    assert client.delete("/api/v1/tags/04A224BC19").status_code == 204
    assert client.get("/api/v1/tags/04A224BC19").status_code == 404


# --- Deleting tracks (regression: A1) ---------------------------------------


def test_delete_track_without_stored_file_leaves_the_working_directory(client, tmp_path):
    """A track whose `source_uri` is empty must not take the CWD with it.

    `Path("").parent` is `Path(".")`, so the old code called
    `shutil.rmtree(".")` - inside the container that is /app, the service's own
    source. Such a row is created by an upload that fails after the record was
    written.
    """
    track = _make_track(client, source_uri="")

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / "canary.txt").write_text("still here")
    previous = os.getcwd()
    os.chdir(workdir)
    try:
        response = client.delete(f"/api/v1/tracks/{track['id']}")
    finally:
        os.chdir(previous)

    assert response.status_code == 204
    assert (workdir / "canary.txt").exists()
    assert client.get(f"/api/v1/tracks/{track['id']}").status_code == 404


def test_delete_track_ignores_a_source_uri_outside_the_audio_storage(client, tmp_path):
    """A URL import keeps the source URL in `source_uri` until it finishes."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")

    for uri in ("https://www.youtube.com/watch?v=abc", str(outside / "keep.txt")):
        track = _make_track(client, source_uri=uri)
        assert client.delete(f"/api/v1/tracks/{track['id']}").status_code == 204

    assert (outside / "keep.txt").exists()


def test_delete_track_removes_its_own_storage_directory(client, env):
    """The case the guard must still allow."""
    track = _make_track(client, source_uri="/placeholder.mp3")
    track_dir = env["audio"] / str(track["id"])
    track_dir.mkdir(parents=True)
    (track_dir / "original.mp3").write_bytes(b"audio")

    client.put(
        f"/api/v1/tracks/{track['id']}",
        json={"title": "Test track"},
    )
    # Point the record at the real file before deleting it.
    session = db_module.db_manager.get_session()
    try:
        from backend_service.models.database import Track

        row = session.query(Track).filter(Track.id == track["id"]).first()
        row.source_uri = str(track_dir / "original.mp3")
        session.commit()
    finally:
        session.close()

    assert client.delete(f"/api/v1/tracks/{track['id']}").status_code == 204
    assert not track_dir.exists()


# --- Upload limits (regression: A3) -----------------------------------------


def test_oversized_track_upload_is_refused_and_leaves_nothing_behind(
    client, env, monkeypatch
):
    monkeypatch.setattr(routes_tracks, "max_audio_upload_bytes", lambda: 1024)

    response = client.post(
        "/api/v1/tracks/upload",
        files={"file": ("big.mp3", b"x" * 5000, "audio/mpeg")},
        data={"title": "Too big"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "upload_too_large"
    # No half-written file and no unplayable placeholder row.
    assert list(env["audio"].rglob("original.*")) == []
    assert client.get("/api/v1/tracks").json() == []


def test_track_upload_within_the_limit_still_works(client, env, monkeypatch):
    monkeypatch.setattr(routes_tracks, "max_audio_upload_bytes", lambda: 1024)

    response = client.post(
        "/api/v1/tracks/upload",
        files={"file": ("small.mp3", b"x" * 512, "audio/mpeg")},
        data={"title": "Small"},
    )

    assert response.status_code == 201, response.text
    stored = Path(response.json()["source_uri"])
    assert stored.exists()
    assert stored.read_bytes() == b"x" * 512


def test_oversized_cover_upload_is_refused(client):
    playlist = client.post("/api/v1/playlists", json={"name": "Cover test"})
    assert playlist.status_code == 201, playlist.text
    playlist_id = playlist.json()["id"]

    response = client.post(
        f"/api/v1/playlists/{playlist_id}/cover",
        files={"file": ("huge.jpg", b"x" * (6 * 1024 * 1024), "image/jpeg")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "upload_too_large"


# --- The upload limit is a runtime setting ----------------------------------


def test_general_settings_expose_the_upload_limit(client):
    body = client.get("/api/v1/config/general").json()
    assert body["max_upload_size_mb"] == 100  # default from config/backend.json


def test_changing_the_limit_takes_effect_without_a_restart(client, env):
    """The whole point of putting the value in general_settings.json.

    No monkeypatching here: the setting is written through the API and the very
    next upload has to honour it, because `max_upload_size_mb()` re-reads the
    file on every call.
    """
    saved = client.put("/api/v1/config/general", json={"max_upload_size_mb": 1})
    assert saved.status_code == 200
    assert saved.json()["max_upload_size_mb"] == 1

    too_big = client.post(
        "/api/v1/tracks/upload",
        files={"file": ("big.mp3", b"x" * (2 * 1024 * 1024), "audio/mpeg")},
        data={"title": "Two megabytes"},
    )
    assert too_big.status_code == 413
    assert too_big.json()["code"] == "upload_too_large"

    small_enough = client.post(
        "/api/v1/tracks/upload",
        files={"file": ("ok.mp3", b"x" * 1024, "audio/mpeg")},
        data={"title": "One kilobyte"},
    )
    assert small_enough.status_code == 201, small_enough.text


@pytest.mark.parametrize(
    ("sent", "stored"),
    [(0, 1), (-5, 1), (250, 250), (999999, 2048), ("nonsense", 100)],
)
def test_the_upload_limit_is_clamped(client, sent, stored):
    response = client.put("/api/v1/config/general", json={"max_upload_size_mb": sent})
    assert response.status_code == 200
    assert response.json()["max_upload_size_mb"] == stored


# --- Auth middleware --------------------------------------------------------


def _enable_password(password: str, areas: list[str]) -> None:
    auth_module.write_auth_settings(
        {"web_password_hash": auth_module.hash_password(password), "protected_areas": areas}
    )


def test_without_a_password_every_route_is_open(client):
    assert client.get("/api/v1/config/general").status_code == 200


def test_protected_area_requires_a_session(client):
    _enable_password("geheim", ["admin"])

    assert client.get("/api/v1/config/general").status_code == 401
    # Media is not among the protected areas, so it stays reachable.
    assert client.get("/api/v1/tracks").status_code == 200

    login = client.post("/api/v1/auth/login", json={"password": "geheim"})
    assert login.status_code == 200
    assert client.cookies.get(COOKIE_NAME)
    assert client.get("/api/v1/config/general").status_code == 200


def test_wrong_password_is_rejected(client):
    _enable_password("geheim", ["admin"])

    response = client.post("/api/v1/auth/login", json={"password": "falsch"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_password"
