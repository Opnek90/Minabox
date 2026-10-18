"""Which protected area a path falls into.

The map in middleware/auth.py mixes general prefixes with specific ones:
/api/v1/audio is the everyday player area, which is off by default, while
/api/v1/audio/restart-service restarts a container and belongs behind the admin
password. Resolving that by map order would make the answer depend on where
somebody happens to add the next entry.
"""

from __future__ import annotations

import pytest

from backend_service.middleware import auth

_area = auth.area_for_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/audio/play", "player"),
        ("/api/v1/audio/test-tone", "player"),
        ("/api/v1/audio/troubleshoot", "player"),
        ("/api/v1/audio/restart-service", "admin"),
        ("/api/v1/system/status", "admin"),
        ("/api/v1/config/audio", "admin"),
        ("/api/v1/tracks/1", "media"),
        ("/api/v1/health", None),
    ],
)
def test_the_longest_matching_prefix_decides(path, expected):
    assert _area(path) == expected


def test_restarting_a_container_is_never_a_player_action():
    """The one that matters: a route that restarts a container must not be
    reachable just because the player area is left open, which it is by
    default."""
    assert _area("/api/v1/audio/restart-service") == "admin"


def test_the_map_order_does_not_decide(monkeypatch):
    """Same map, reversed. The answer has to be the same."""
    reversed_map = dict(reversed(list(auth._PROTECTED_PREFIXES.items())))
    monkeypatch.setattr(auth, "_PROTECTED_PREFIXES", reversed_map)

    assert auth.area_for_path("/api/v1/audio/restart-service") == "admin"
    assert auth.area_for_path("/api/v1/audio/play") == "player"


@pytest.mark.asyncio
async def test_auth_config_reports_valid_session_cookie(monkeypatch):
    from starlette.requests import Request

    from backend_service.api import routes_auth
    from backend_service.core import auth as core_auth

    monkeypatch.setattr(
        routes_auth,
        "read_auth_settings",
        lambda: {"web_password_hash": "hashed", "protected_areas": ["admin"]},
    )
    token = core_auth.create_session_token()

    req_without_cookie = Request({"type": "http", "headers": []})
    res_unauth = await routes_auth.get_auth_config(req_without_cookie)
    assert res_unauth["authenticated"] is False

    req_with_cookie = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{routes_auth.COOKIE_NAME}={token}".encode())],
        }
    )
    res_auth = await routes_auth.get_auth_config(req_with_cookie)
    assert res_auth["authenticated"] is True
