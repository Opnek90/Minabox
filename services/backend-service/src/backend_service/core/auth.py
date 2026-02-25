"""Web auth: read/write auth_settings, password hashing, session token."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import structlog
import bcrypt as bcrypt_pkg
from jose import JWTError, jwt

# Bcrypt limit; we pass bytes truncated to this to avoid library errors
_BCRYPT_MAX_BYTES = 72

logger = structlog.get_logger(__name__)

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
AUTH_SETTINGS_PATH = DATA_PATH / "auth_settings.json"

# JWT: symmetric secret; fallback for dev/local
def _auth_secret() -> str:
    return (
        os.environ.get("WEB_AUTH_SECRET", "").strip()
        or os.environ.get("HOST_HELPER_API_KEY", "").strip()
        or "minabox-web-auth-dev-secret"
    )


ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 86400  # 24h


def read_auth_settings() -> dict:
    """Return auth settings. Default: web_password_hash='', protected_areas=[]."""
    default = {"web_password_hash": "", "protected_areas": []}
    if not AUTH_SETTINGS_PATH.exists():
        return default.copy()
    try:
        data = json.loads(AUTH_SETTINGS_PATH.read_text(encoding="utf-8"))
        return {
            "web_password_hash": str(data.get("web_password_hash", "")).strip(),
            "protected_areas": [
                str(x).strip()
                for x in (data.get("protected_areas") or [])
                if str(x).strip() in ("admin", "media", "dashboard")
            ],
        }
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("auth_settings_read_failed", path=str(AUTH_SETTINGS_PATH), error=str(e))
        return default.copy()


def write_auth_settings(data: dict) -> None:
    """Write only web_password_hash and protected_areas to auth_settings.json."""
    allowed = {"web_password_hash", "protected_areas"}
    to_write = {k: v for k, v in data.items() if k in allowed}
    if "protected_areas" in to_write:
        to_write["protected_areas"] = [
            str(x).strip()
            for x in to_write["protected_areas"]
            if str(x).strip() in ("admin", "media", "dashboard")
        ]
    AUTH_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_SETTINGS_PATH.write_text(
        json.dumps(to_write, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _password_bytes(password: str) -> bytes:
    """Encode password to bytes, at most 72 bytes (bcrypt limit)."""
    if not isinstance(password, str):
        password = str(password, "utf-8", errors="replace")
    raw = password.strip().encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raw = raw[:_BCRYPT_MAX_BYTES]
    return raw


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against bcrypt hash."""
    if not hashed:
        return False
    try:
        return bcrypt_pkg.checkpw(_password_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def hash_password(password: str) -> str:
    """Return bcrypt hash of password (max 72 bytes)."""
    pw_bytes = _password_bytes(password)
    return bcrypt_pkg.hashpw(pw_bytes, bcrypt_pkg.gensalt()).decode("utf-8")


def create_session_token() -> str:
    """Return a signed JWT for web session (sub=web, exp=now+24h)."""
    payload = {
        "sub": "web",
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, _auth_secret(), algorithm=ALGORITHM)


def verify_session_token(token: str) -> bool:
    """Verify JWT signature and expiry. Returns True if valid."""
    if not token:
        return False
    try:
        jwt.decode(token, _auth_secret(), algorithms=[ALGORITHM])
        return True
    except JWTError:
        return False
