"""REST API for web auth: config, login, logout, password."""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend_service.core.api_errors import ApiError
from backend_service.core.auth import (
    AUTH_SETTINGS_PATH,
    create_session_token,
    hash_password,
    normalize_areas,
    read_auth_settings,
    verify_password,
    verify_session_token,
    write_auth_settings,
)

logger = structlog.get_logger(__name__)
router = APIRouter()

COOKIE_NAME = "minabox_session"
COOKIE_MAX_AGE = 86400  # 24h

# One area can guard more than one page: the card management screen is backed
# by the same routes as the player, so protecting one without the other would
# leave a page that loads and then fails with 401s.
AREA_TO_PATHS: dict[str, list[str]] = {
    "admin": ["/admin"],
    "media": ["/media"],
    "dashboard": ["/dashboard"],
    "player": ["/player", "/rfid"],
}

# Brute force: bcrypt alone is not a rate limit, and the minimum password is
# four characters. After this many failures from one address, that address has
# to wait - long enough to make guessing pointless, short enough that a parent
# who mistyped is not locked out for the evening.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 300

#: address -> (failure count, time of the last failure)
_login_failures: dict[str, tuple[int, float]] = {}


def _protected_paths(protected_areas: list[str]) -> list[str]:
    paths: list[str] = []
    for area in protected_areas:
        paths.extend(AREA_TO_PATHS.get(area, []))
    return paths


def _client_address(request: Request) -> str:
    """The peer address of the connection.

    Deliberately not X-Forwarded-For: that header is set by the caller, so
    trusting it would let an attacker reset their own lockout at will.
    """
    return request.client.host if request.client else "unknown"


def _lockout_remaining(address: str) -> int:
    """Seconds this address still has to wait, 0 when it may try."""
    failures, last_seen = _login_failures.get(address, (0, 0.0))
    if failures < LOGIN_MAX_FAILURES:
        return 0
    elapsed = time.monotonic() - last_seen
    if elapsed >= LOGIN_LOCKOUT_SECONDS:
        _login_failures.pop(address, None)
        return 0
    return int(LOGIN_LOCKOUT_SECONDS - elapsed)


def _record_login_failure(address: str) -> None:
    failures, _ = _login_failures.get(address, (0, 0.0))
    _login_failures[address] = (failures + 1, time.monotonic())


def reset_login_failures(address: str | None = None) -> None:
    """Clear the failure counter - after a success, or wholesale in tests."""
    if address is None:
        _login_failures.clear()
    else:
        _login_failures.pop(address, None)


# Minimum length of the web password. This is the only lock in front of the
# media library, the parent dashboard and maintenance - and maintenance holds
# the factory reset, the OS update and the backup download with the whole
# database. The Host-Helper asks for eight characters for the system password,
# so this matches it. The WebUI enforces the same value in utils/validators.ts;
# an existing shorter password keeps working for login, only setting a new one
# is affected.
MIN_PASSWORD_LENGTH = 8


class LoginBody(BaseModel):
    password: str = ""


class PasswordBody(BaseModel):
    current_password: str = ""
    new_password: str = ""


class ConfigUpdateBody(BaseModel):
    protected_areas: list[str] = []


def _get_cookie_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME) or None


def _require_auth(request: Request) -> None:
    """Raise 401 if no valid session cookie."""
    token = _get_cookie_token(request)
    if not token or not verify_session_token(token):
        raise ApiError(status_code=401, code="auth_required", detail="Authentication required")


@router.get("/config")
async def get_auth_config() -> dict:
    """Return auth config (public). authEnabled and protectedPaths for frontend."""
    settings = read_auth_settings()
    auth_enabled = bool((settings.get("web_password_hash") or "").strip())
    protected_areas = settings.get("protected_areas") or []
    return {
        "authEnabled": auth_enabled,
        "protectedPaths": _protected_paths(protected_areas),
    }


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    """Verify password and set session cookie. No auth required."""
    settings = read_auth_settings()
    hash_val = (settings.get("web_password_hash") or "").strip()
    auth_enabled = bool(hash_val)

    if not auth_enabled:
        return {"ok": True}

    address = _client_address(request)
    waiting = _lockout_remaining(address)
    if waiting:
        logger.warning("auth_login_locked_out", client=address, retry_after=waiting)
        raise ApiError(
            status_code=429,
            code="login_locked_out",
            detail=f"Too many failed attempts. Try again in {waiting} seconds.",
            headers={"Retry-After": str(max(1, waiting))},
            extra={"retry_after": waiting},
        )

    password = (body.password or "").strip()
    if not password:
        raise ApiError(status_code=400, code="password_required", detail="Password required")

    if not verify_password(password, hash_val):
        _record_login_failure(address)
        logger.warning("auth_login_failed", client=address)
        raise ApiError(status_code=401, code="invalid_password", detail="Invalid password")

    reset_login_failures(address)
    token = create_session_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/password")
async def set_password(body: PasswordBody, request: Request, response: Response) -> dict:
    """Set or change web password. Initial setup: no cookie. Change: valid cookie + current_password."""
    try:
        settings = read_auth_settings()
        auth_enabled = bool((settings.get("web_password_hash") or "").strip())
        new_raw = (body.new_password or "").strip()

        if not new_raw or len(new_raw) < MIN_PASSWORD_LENGTH:
            raise ApiError(
                status_code=400,
                code="password_too_short",
                detail=f"New password must be at least {MIN_PASSWORD_LENGTH} characters",
            )

        if auth_enabled:
            _require_auth(request)
            current = (body.current_password or "").strip()
            if not current:
                raise ApiError(status_code=400, code="current_password_required", detail="Current password required")
            if not verify_password(current, settings.get("web_password_hash") or ""):
                raise ApiError(status_code=401, code="current_password_invalid", detail="Current password is wrong")
        else:
            # Initial setup: set cookie so user is logged in after setting password
            token = create_session_token()
            response.set_cookie(
                key=COOKIE_NAME,
                value=token,
                max_age=COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
            )

        try:
            new_hash = hash_password(new_raw)
        except Exception as e:
            logger.warning("auth_password_hash_failed", error=str(e))
            raise ApiError(status_code=500, code="password_hash_failed", detail=f"Password hashing failed: {e!s}") from e

        try:
            write_auth_settings({"web_password_hash": new_hash, "protected_areas": settings.get("protected_areas", [])})
        except OSError as e:
            logger.warning("auth_settings_write_failed", path=str(AUTH_SETTINGS_PATH), error=str(e))
            raise ApiError(status_code=500, code="auth_settings_write_failed", detail="Failed to write auth settings (check permissions)") from e
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("auth_set_password_error")
        raise ApiError(status_code=500, code="password_set_failed", detail=f"Set password failed: {e!s}") from e


@router.delete("/password")
async def delete_password(request: Request, response: Response) -> dict:
    """Delete web password and disable access protection. Requires valid session."""
    _require_auth(request)
    try:
        write_auth_settings({"web_password_hash": "", "protected_areas": []})
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return {"ok": True}
    except OSError as e:
        logger.warning("auth_settings_write_failed", path=str(AUTH_SETTINGS_PATH), error=str(e))
        raise ApiError(status_code=500, code="auth_settings_write_failed", detail="Failed to write auth settings (check permissions)") from e


@router.put("/config")
async def update_auth_config(body: ConfigUpdateBody, request: Request) -> dict:
    """Update protected_areas only. Requires valid session (or no password set)."""
    settings = read_auth_settings()
    auth_enabled = bool((settings.get("web_password_hash") or "").strip())

    if auth_enabled:
        _require_auth(request)

    areas = normalize_areas(body.protected_areas)
    write_auth_settings({"web_password_hash": settings.get("web_password_hash") or "", "protected_areas": areas})
    return {"authEnabled": auth_enabled, "protectedPaths": _protected_paths(areas)}
