"""REST API for web auth: config, login, logout, password."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend_service.core.auth import (
    AUTH_SETTINGS_PATH,
    create_session_token,
    hash_password,
    read_auth_settings,
    verify_password,
    verify_session_token,
    write_auth_settings,
)

logger = structlog.get_logger(__name__)
router = APIRouter()

COOKIE_NAME = "minabox_session"
COOKIE_MAX_AGE = 86400  # 24h
AREA_TO_PATH = {"admin": "/admin", "media": "/media", "dashboard": "/dashboard"}


def _protected_paths(protected_areas: list[str]) -> list[str]:
    return [AREA_TO_PATH[a] for a in protected_areas if a in AREA_TO_PATH]


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
        raise HTTPException(status_code=401, detail="Authentication required")


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
async def login(body: LoginBody, response: Response) -> dict:
    """Verify password and set session cookie. No auth required."""
    settings = read_auth_settings()
    hash_val = (settings.get("web_password_hash") or "").strip()
    auth_enabled = bool(hash_val)

    if not auth_enabled:
        return {"ok": True}

    password = (body.password or "").strip()
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    if not verify_password(password, hash_val):
        raise HTTPException(status_code=401, detail="Invalid password")

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

        if not new_raw or len(new_raw) < 4:
            raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

        if auth_enabled:
            _require_auth(request)
            current = (body.current_password or "").strip()
            if not current:
                raise HTTPException(status_code=400, detail="Current password required")
            if not verify_password(current, settings.get("web_password_hash") or ""):
                raise HTTPException(status_code=401, detail="Current password is wrong")
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
            raise HTTPException(status_code=500, detail=f"Password hashing failed: {e!s}") from e

        try:
            write_auth_settings({"web_password_hash": new_hash, "protected_areas": settings.get("protected_areas", [])})
        except OSError as e:
            logger.warning("auth_settings_write_failed", path=str(AUTH_SETTINGS_PATH), error=str(e))
            raise HTTPException(status_code=500, detail="Failed to write auth settings (check permissions)") from e
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("auth_set_password_error")
        raise HTTPException(status_code=500, detail=f"Set password failed: {e!s}") from e


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
        raise HTTPException(status_code=500, detail="Failed to write auth settings (check permissions)") from e


@router.put("/config")
async def update_auth_config(body: ConfigUpdateBody, request: Request) -> dict:
    """Update protected_areas only. Requires valid session (or no password set)."""
    settings = read_auth_settings()
    auth_enabled = bool((settings.get("web_password_hash") or "").strip())

    if auth_enabled:
        _require_auth(request)

    areas = [str(x).strip() for x in (body.protected_areas or []) if str(x).strip() in ("admin", "media", "dashboard")]
    write_auth_settings({"web_password_hash": settings.get("web_password_hash") or "", "protected_areas": areas})
    return {"authEnabled": auth_enabled, "protectedPaths": _protected_paths(areas)}
