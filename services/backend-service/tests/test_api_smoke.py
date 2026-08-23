"""Smoke tests that exercise the REST layer through a real ASGI app.

Everything else in this suite tests functions in isolation. Nothing started the
FastAPI application, so the routing, the response models, the error handler and
the auth middleware were never covered - and neither were the paths where a
route touches the filesystem. Both defects these tests pin down (deleting a
track without a stored file, and an unbounded upload) lived in exactly that gap.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import backend_service.core.db_manager as db_module
from backend_service.api import routes_auth, routes_config, routes_tracks
from backend_service.api.routes_auth import COOKIE_NAME
from backend_service.core import auth as auth_module


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


# --- Playlist order is a setting now (C4) -----------------------------------


def test_playlists_shuffle_by_default(client):
    """Unchanged behaviour: the box has always randomised playlists."""
    assert client.get("/api/v1/config/general").json()["playlist_shuffle"] is True


def test_turning_shuffle_off_keeps_the_playlist_order(client, env):
    """An audio play in chapters has to run in the order it was put together.

    `PlaylistTrack.position` kept that order all along - it was simply never
    used, because the call site passed shuffle=True unconditionally.
    """
    from backend_service.core.session_manager import SessionManager
    from backend_service.models.database import Track

    saved = client.put("/api/v1/config/general", json={"playlist_shuffle": False})
    assert saved.status_code == 200
    assert saved.json()["playlist_shuffle"] is False

    tracks = [
        Track(id=i, title=f"Chapter {i}", source_type="file", source_uri=f"/x/{i}.mp3")
        for i in range(1, 21)
    ]
    session = SessionManager().create_session(tracks=tracks, playlist_id=1)

    assert session.shuffle is False
    assert [t.id for t in session.tracks] == list(range(1, 21))


def test_shuffle_stays_on_when_the_setting_says_so(client, env):
    from backend_service.core.session_manager import SessionManager
    from backend_service.models.database import Track

    client.put("/api/v1/config/general", json={"playlist_shuffle": True})
    tracks = [
        Track(id=i, title=str(i), source_type="file", source_uri=f"/x/{i}.mp3")
        for i in range(1, 21)
    ]
    session = SessionManager().create_session(tracks=tracks, playlist_id=1)
    assert session.shuffle is True


def test_a_single_track_is_never_shuffled(client, env):
    """The setting is about playlists; one track has no order to randomise."""
    from backend_service.core.session_manager import SessionManager
    from backend_service.models.database import Track

    client.put("/api/v1/config/general", json={"playlist_shuffle": True})
    track = Track(id=1, title="Solo", source_type="file", source_uri="/x/1.mp3")
    session = SessionManager().create_session(tracks=[track])
    assert session.shuffle is False


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


def test_repeated_wrong_passwords_lock_the_address_out(client):
    """bcrypt slows a guess down; it is not a rate limit on its own."""
    _enable_password("geheim", ["admin"])

    for _ in range(routes_auth.LOGIN_MAX_FAILURES):
        assert client.post("/api/v1/auth/login", json={"password": "falsch"}).status_code == 401

    locked = client.post("/api/v1/auth/login", json={"password": "falsch"})
    assert locked.status_code == 429
    assert locked.json()["code"] == "login_locked_out"
    assert int(locked.headers["Retry-After"]) > 0

    # The correct password is refused too - otherwise the lockout would be
    # trivially bypassed by guessing on.
    assert client.post("/api/v1/auth/login", json={"password": "geheim"}).status_code == 429


def test_a_successful_login_clears_the_counter(client):
    _enable_password("geheim", ["admin"])

    for _ in range(routes_auth.LOGIN_MAX_FAILURES - 1):
        client.post("/api/v1/auth/login", json={"password": "falsch"})
    assert client.post("/api/v1/auth/login", json={"password": "geheim"}).status_code == 200

    # Counter reset: a fresh run of failures must be needed to lock out again.
    for _ in range(routes_auth.LOGIN_MAX_FAILURES - 1):
        assert client.post("/api/v1/auth/login", json={"password": "falsch"}).status_code == 401


# --- The player area (B1/B2) ------------------------------------------------


def test_player_routes_are_open_unless_the_area_is_switched_on(client):
    """Default behaviour must not change for a box that already has a password."""
    _enable_password("geheim", ["admin", "media", "dashboard"])

    assert client.get("/api/v1/tags").status_code == 200
    assert client.get("/api/v1/audio/status").status_code == 200
    assert client.get("/api/v1/scan-history/").status_code == 200


def test_the_player_area_protects_playback_cards_and_history(client):
    _enable_password("geheim", ["player"])

    assert client.get("/api/v1/tags").status_code == 401
    assert client.get("/api/v1/audio/status").status_code == 401
    assert client.get("/api/v1/scan-history/").status_code == 401
    # Media is not protected here, so it stays open.
    assert client.get("/api/v1/tracks").status_code == 200

    assert client.post("/api/v1/auth/login", json={"password": "geheim"}).status_code == 200
    assert client.get("/api/v1/tags").status_code == 200


def test_the_player_area_covers_the_websocket(client):
    """The middleware never sees a handshake, so /ws checks for itself."""
    from starlette.websockets import WebSocketDisconnect as StarletteDisconnect

    _enable_password("geheim", ["player"])
    with pytest.raises(StarletteDisconnect):
        with client.websocket_connect("/ws"):
            pass

    client.post("/api/v1/auth/login", json={"password": "geheim"})
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"hello": true}')
        assert ws.receive_json()["type"] == "ack"


def test_the_websocket_is_open_while_the_area_is_off(client):
    _enable_password("geheim", ["admin"])
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"hello": true}')
        assert ws.receive_json()["type"] == "ack"


# --- Config writing (B6/B7) -------------------------------------------------


def test_a_config_body_that_lost_its_content_is_refused(client, tmp_path, monkeypatch):
    """A body without its list would leave the LED service unable to start."""
    config_dir = tmp_path / "config_services"
    (config_dir / "led").mkdir(parents=True)
    led_file = config_dir / "led" / "leds.json"
    original = '{"leds": [{"id": "led_1", "gpio": 17}]}'
    led_file.write_text(original, encoding="utf-8")
    monkeypatch.setattr(routes_config, "CONFIG_SERVICES_BASE", config_dir)

    refused = client.put("/api/v1/config/leds", json={"brightness": 50})
    assert refused.status_code == 422
    assert refused.json()["code"] == "config_invalid"
    assert led_file.read_text(encoding="utf-8") == original  # untouched

    accepted = client.put("/api/v1/config/leds", json={"leds": []})
    assert accepted.status_code == 200
    assert json.loads(led_file.read_text(encoding="utf-8")) == {"leds": []}


def test_writing_the_rfid_config_keeps_the_sections_it_does_not_own(
    client, tmp_path, monkeypatch
):
    config_dir = tmp_path / "config_services"
    (config_dir / "rfid").mkdir(parents=True)
    rfid_file = config_dir / "rfid" / "rfid.json"
    rfid_file.write_text(
        json.dumps(
            {
                "reader": {"reader_type": "pn532", "interface": "i2c"},
                "modes": {"default": "normal"},
                "service": {"health_port": 8000},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(routes_config, "CONFIG_SERVICES_BASE", config_dir)

    response = client.put("/api/v1/config/rfid", json={"reader_type": "PN532", "interface": "SPI"})
    assert response.status_code == 200

    written = json.loads(rfid_file.read_text(encoding="utf-8"))
    assert written["reader"]["interface"] == "spi"
    # These belong to the RFID service and were previously dropped on save.
    assert written["modes"] == {"default": "normal"}
    assert written["service"] == {"health_port": 8000}


def test_auth_settings_are_written_atomically_and_privately(client, env):
    _enable_password("geheim", ["admin"])
    path = env["data"] / "auth_settings.json"

    assert json.loads(path.read_text(encoding="utf-8"))["protected_areas"] == ["admin"]
    assert oct(path.stat().st_mode)[-3:] == "600"
    # No temporary file left behind by the rename.
    assert list(env["data"].glob(".auth_settings.json.*")) == []


# --- The signing secret (B4) ------------------------------------------------


def test_a_secret_is_generated_per_box_instead_of_a_shared_default(env, monkeypatch):
    monkeypatch.delenv("WEB_AUTH_SECRET", raising=False)
    monkeypatch.delenv("HOST_HELPER_API_KEY", raising=False)
    monkeypatch.setattr(auth_module, "_generated_secret", None)

    secret = auth_module._auth_secret()
    assert len(secret) >= 32
    assert "minabox" not in secret  # never the old hard-coded fallback

    stored = env["data"] / "web_auth_secret"
    assert stored.read_text(encoding="utf-8").strip() == secret
    assert oct(stored.stat().st_mode)[-3:] == "600"

    # Stable across calls, so sessions survive within a run.
    monkeypatch.setattr(auth_module, "_generated_secret", None)
    assert auth_module._auth_secret() == secret
