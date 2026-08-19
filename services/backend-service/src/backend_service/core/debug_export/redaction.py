"""Redaction for the debug export.

Every file goes through here before it is written into the archive - not per
collector, so a new collector cannot forget it.

Three layers, in increasing order of paranoia:

1. ``scrub()``     - key deny-list plus regex patterns over free text.
2. ``pseudonymize()`` - one-way hash with a per-export salt for values that must
   stay correlatable inside one archive (SSID, MAC, tag UID, serial numbers)
   without being traceable across archives.
3. ``SecretTripwire`` - compares the finished payload against the *actual*
   secret values of this device. Patterns only catch what someone anticipated;
   the tripwire also catches the field that gets added next year by someone who
   never read this module.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REDACTED = "[entfernt]"

# Substring match against dict keys, case-insensitive.
SECRET_KEY_PARTS: tuple[str, ...] = (
    "key",
    "token",
    "secret",
    "password",
    "passwd",
    "psk",
    "hash",
    "authorization",
    "cookie",
    "credential",
    "api_key",
    "auth",
)

# Keys that contain one of the parts above but are harmless - without these the
# export would redact half of its own diagnostics (e.g. "keyboard_layout").
SECRET_KEY_ALLOW: frozenset[str] = frozenset(
    {
        "keyboard_layout",
        "authorized_state",
        "auth_enabled",
        "monkeypatch",
        "keys",
        "key_count",
    }
)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization headers and bearer tokens
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}"), r"\1 " + REDACTED),
    (
        re.compile(r"(?i)\b(x-api-key|authorization|cookie)\s*[:=]\s*\S+"),
        r"\1: " + REDACTED,
    ),
    # key=value / "key": "value" for secret-ish names
    (
        re.compile(
            r"(?i)\b([a-z0-9_\-]*(?:api[_\-]?key|secret|token|password|passwd|psk)[a-z0-9_\-]*)"
            r"(\"?\s*[:=]\s*\"?)([^\s\"',;]{4,})"
        ),
        r"\1\2" + REDACTED,
    ),
    # Credentials inside URLs: scheme://user:pass@host
    (re.compile(r"://[^/\s:@]+:[^/\s:@]+@"), "://" + REDACTED + "@"),
    # Long hex blobs: the API key is `openssl rand -hex 32`, i.e. 64 characters.
    # The threshold sits above SHA-1 (40) on purpose - the bootloader version
    # and git revisions are 40-character hashes and are not secrets. Anything
    # that slips through here is still caught by the tripwire.
    (re.compile(r"\b[0-9a-fA-F]{48,}\b"), REDACTED),
    # E-mail addresses
    (re.compile(r"\b[\w.\-+]+@[\w\-]+\.[A-Za-z]{2,}\b"), REDACTED),
)


def scrub_text(text: str) -> str:
    """Apply every regex pattern to a free-text blob (logs, command output)."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in SECRET_KEY_ALLOW:
        return False
    return any(part in lowered for part in SECRET_KEY_PARTS)


def scrub(value: Any) -> Any:
    """Recursively redact a JSON-shaped structure.

    Dict keys are matched against the deny-list; every string that survives is
    still run through the text patterns, because a harmless key can carry a
    token in its value.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_secret_key(str(k)) else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def pseudonymize(value: str | None, salt: str) -> str | None:
    """Stable pseudonym for a value: correlatable within one export, nowhere else.

    Used where deleting would destroy the diagnosis - "same wifi as before",
    "the same tag keeps failing" - but the real value has no business leaving
    the device.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return text
    digest = hashlib.sha256((salt + text).encode("utf-8", errors="replace")).hexdigest()
    return f"id:{digest[:12]}"


class SecretTripwire:
    """Fails the export if a real secret value made it into the archive.

    This is the backstop for everything the scrubber did not anticipate. It
    compares against the values actually present on this device, so a brand new
    config field carrying the Host-Helper key is caught even though no pattern
    describes it.
    """

    # Shorter values produce false positives ("true", "1883") and are not
    # secrets worth protecting anyway.
    MIN_LENGTH = 8

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets: dict[str, str] = {}
        for name, value in (secrets or {}).items():
            self.add(name, value)

    def add(self, name: str, value: str | None) -> None:
        if not value:
            return
        text = str(value).strip()
        if len(text) >= self.MIN_LENGTH:
            self._secrets[name] = text

    @property
    def names(self) -> list[str]:
        return sorted(self._secrets)

    def find(self, payload: str) -> list[str]:
        """Return the names of every known secret that appears in the payload."""
        return [name for name, value in self._secrets.items() if value in payload]

    def redact(self, payload: str) -> tuple[str, list[str]]:
        """Remove every known secret literally. Returns (text, names found).

        Literal replacement is what makes this a backstop rather than a second
        guess: it does not depend on the value looking like a secret.
        """
        found: list[str] = []
        for name, value in self._secrets.items():
            if value in payload:
                found.append(name)
                payload = payload.replace(value, "[GEHEIMNIS ENTFERNT]")
        return payload, found

    @classmethod
    def from_device(cls, data_path: Path | str = "/data") -> SecretTripwire:
        """Collect the secret values that exist on this device."""
        tripwire = cls()
        for env_name in (
            "HOST_HELPER_API_KEY",
            "WEB_AUTH_SECRET",
            "MEDIA_DOWNLOADER_API_KEY",
        ):
            tripwire.add(f"env:{env_name}", os.environ.get(env_name))

        auth_file = Path(data_path) / "auth_settings.json"
        try:
            if auth_file.exists():
                import json

                payload = json.loads(auth_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    tripwire.add(
                        "auth:web_password_hash", payload.get("web_password_hash")
                    )
        except (OSError, ValueError) as e:
            # A broken auth file must not stop the export - it only means this
            # particular value cannot be checked.
            logger.debug("tripwire_auth_read_failed", error=str(e))

        # WLAN pre-shared keys from the NetworkManager profiles, when the host
        # filesystem is reachable.
        for base in (
            "/host/etc/NetworkManager/system-connections",
            "/etc/NetworkManager/system-connections",
        ):
            directory = Path(base)
            if not directory.is_dir():
                continue
            try:
                for profile in directory.glob("*.nmconnection"):
                    for line in profile.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines():
                        if line.strip().startswith("psk="):
                            tripwire.add(f"wifi:{profile.stem}", line.split("=", 1)[1])
            except OSError as e:
                logger.debug("tripwire_wifi_read_failed", error=str(e))
            break

        return tripwire


class SecretLeakError(RuntimeError):
    """Raised when the finished archive still contains a real secret."""

    def __init__(self, path: str, names: list[str]) -> None:
        self.path = path
        self.names = names
        super().__init__(
            f"Export abgebrochen: {path} enthält Geheimnisse ({', '.join(names)})"
        )
