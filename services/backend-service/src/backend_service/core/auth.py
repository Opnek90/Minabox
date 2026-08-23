"""Web auth: read/write auth_settings, password hashing, session token."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import bcrypt as bcrypt_pkg
import jwt
import structlog
from jwt import InvalidTokenError

from backend_service.core.json_store import write_json_atomic

# Bcrypt limit; we pass bytes truncated to this to avoid library errors
_BCRYPT_MAX_BYTES = 72

logger = structlog.get_logger(__name__)

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
AUTH_SETTINGS_PATH = DATA_PATH / "auth_settings.json"

#: The areas a user can put behind the password. `player` also covers the live
#: WebSocket feed, because that carries the same events as the routes it guards.
VALID_AREAS: tuple[str, ...] = ("admin", "media", "dashboard", "player")

ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 86400  # 24h

_generated_secret: str | None = None


def _secret_file() -> Path:
    """Where a self-generated signing secret is kept."""
    return Path(os.environ.get("DATA_PATH", "/data")) / "web_auth_secret"


def _load_or_create_secret() -> str:
    """Return this box's own signing secret, creating it once if needed.

    There used to be a hard-coded string as the last resort. `install.sh`
    generates real secrets, but a hand-written `.env` silently fell back to a
    value that is public in the repository - and anyone who knows it can mint a
    valid session cookie. Generating one per box removes that without ever
    locking anyone out.
    """
    global _generated_secret
    if _generated_secret:
        return _generated_secret

    path = _secret_file()
    try:
        if path.exists():
            stored = path.read_text(encoding="utf-8").strip()
            if stored:
                _generated_secret = stored
                return stored
    except OSError as e:
        logger.warning("auth_secret_read_failed", path=str(path), error=str(e))

    created = secrets.token_urlsafe(48)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(created, encoding="utf-8")
        path.chmod(0o600)
        logger.info("auth_secret_generated", path=str(path))
    except OSError as e:
        # Still usable for this process; it just will not survive a restart,
        # which logs everyone out rather than trusting a known value.
        logger.warning("auth_secret_write_failed", path=str(path), error=str(e))

    _generated_secret = created
    return created


def _auth_secret() -> str:
    """Signing secret for the session token.

    Order: the explicit setting, then the Host-Helper key, then a secret this
    box generated for itself.
    """
    return (
        os.environ.get("WEB_AUTH_SECRET", "").strip()
        or os.environ.get("HOST_HELPER_API_KEY", "").strip()
        or _load_or_create_secret()
    )


def normalize_areas(raw: object) -> list[str]:
    """Keep only known area names, in a stable order."""
    if not isinstance(raw, (list, tuple)):
        return []
    seen = {str(x).strip() for x in raw}
    return [area for area in VALID_AREAS if area in seen]


def read_auth_settings() -> dict:
    """Return auth settings. Default: web_password_hash='', protected_areas=[]."""
    default = {"web_password_hash": "", "protected_areas": []}
    if not AUTH_SETTINGS_PATH.exists():
        return default.copy()
    try:
        data = json.loads(AUTH_SETTINGS_PATH.read_text(encoding="utf-8"))
        return {
            "web_password_hash": str(data.get("web_password_hash", "")).strip(),
            "protected_areas": normalize_areas(data.get("protected_areas")),
        }
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("auth_settings_read_failed", path=str(AUTH_SETTINGS_PATH), error=str(e))
        return default.copy()


def write_auth_settings(data: dict) -> None:
    """Write only web_password_hash and protected_areas to auth_settings.json.

    Written atomically and readable only by the service user: a truncated file
    reads as "no password configured", which would silently unprotect the box.
    """
    to_write = {
        "web_password_hash": str(data.get("web_password_hash", "")).strip(),
        "protected_areas": normalize_areas(data.get("protected_areas")),
    }
    write_json_atomic(AUTH_SETTINGS_PATH, to_write, chmod=0o600)


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
    """Verify JWT signature and expiry. Returns True if valid.

    The algorithm is pinned to a single value, so a token that names a
    different one is rejected rather than being taken at its word.
    """
    if not token:
        return False
    try:
        jwt.decode(token, _auth_secret(), algorithms=[ALGORITHM])
        return True
    except InvalidTokenError:
        return False


__all__ = [
    "ALGORITHM",
    "AUTH_SETTINGS_PATH",
    "TOKEN_EXPIRY_SECONDS",
    "VALID_AREAS",
    "create_session_token",
    "hash_password",
    "normalize_areas",
    "read_auth_settings",
    "verify_password",
    "verify_session_token",
    "write_auth_settings",
]
