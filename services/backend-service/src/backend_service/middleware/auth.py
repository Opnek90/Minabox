"""Web authentication middleware for the Backend Service.

Provides session-cookie-based auth for protected API paths.
Extracted from app_factory._create_app() for testability and clarity.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend_service.api.routes_auth import COOKIE_NAME
from backend_service.core.auth import read_auth_settings, verify_session_token

# Maps URL path prefixes to the protected area name required to access them.
# When a new route needs protection, add an entry here — no other code changes
# are necessary.
_PROTECTED_PREFIXES: dict[str, str] = {
    "/api/v1/config": "admin",
    "/api/v1/system": "admin",
    "/api/v1/playlists": "media",
    "/api/v1/tracks": "media",
    "/api/v1/streams": "media",
    "/api/v1/podcasts": "media",
    "/api/v1/stats": "dashboard",
    # Restarting a container is an admin action wherever it lives. It sits
    # under /audio because that is the service it restarts, but it must not
    # inherit the `player` area, which is off by default. The longest matching
    # prefix wins, so this entry beats the /api/v1/audio one below regardless
    # of where it stands in this map.
    "/api/v1/audio/restart-service": "admin",
    # The `player` area. These are off by default: the player is the everyday
    # screen, and a box where a child cannot press play is not the default
    # anyone wants. Switching the area on covers the live WebSocket too - see
    # api/websocket.py - because it carries the same events these routes do.
    "/api/v1/audio": "player",
    "/api/v1/tags": "player",
    "/api/v1/rfid": "player",
    "/api/v1/scan-history": "player",
}

# Paths that are always publicly accessible (auth endpoints themselves).
#
# The debug export is deliberately in this list: it is the one thing a user
# still needs when the password itself is the problem. It is not unguarded —
# it enforces a private-network check, a rate limit and, without a valid
# session, the standard tier (no filenames, no history, no database copy).
# See docs/DebugExport.md section 4.5.
_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/api/v1/auth/config",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/password",
    "/api/v1/system/debug-export",
    "/api/v1/system/debug-export/options",
    # Read-only network state, polled by the display service without a session
    # so it can show the address/hotspot to reach the box on. The hotspot
    # password it may carry is only set while that hotspot is the box's only
    # network, i.e. everyone who can reach this already has it.
    "/api/v1/system/network-status",
})


def area_for_path(path: str) -> str | None:
    """The protected area a request path falls into, or None.

    The longest matching prefix wins. A plain "first match" would make the
    *order* of _PROTECTED_PREFIXES decide whether /api/v1/audio/restart-service
    is an admin route or a player one - a trap for whoever adds the next
    specific path under a general prefix.
    """
    matches = [
        (prefix, area)
        for prefix, area in _PROTECTED_PREFIXES.items()
        if path.startswith(prefix)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def area_requires_session(area: str) -> bool:
    """True when this area is behind the password on this box.

    Shared with the WebSocket endpoint, which sits outside the middleware and
    would otherwise hand out the same events without a check.
    """
    settings = read_auth_settings()
    if not (settings.get("web_password_hash") or "").strip():
        return False
    return area in set(settings.get("protected_areas") or [])


async def web_auth_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Require a valid session cookie for protected API paths.

    Short-circuits immediately for:
    - Non-API paths (static files, WebSocket, health-check, …)
    - Public auth endpoints
    - Installations where no web password is configured
    - Routes not covered by any protected area
    """
    path = request.url.path

    if not path.startswith("/api/v1/"):
        return await call_next(request)

    if path in _PUBLIC_PATHS:
        return await call_next(request)

    settings = read_auth_settings()
    auth_enabled = bool((settings.get("web_password_hash") or "").strip())
    if not auth_enabled:
        return await call_next(request)

    protected_areas = set(settings.get("protected_areas") or [])
    if not protected_areas:
        return await call_next(request)

    area = area_for_path(path)

    if area is None or area not in protected_areas:
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    if not token or not verify_session_token(token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required"},
        )

    return await call_next(request)
