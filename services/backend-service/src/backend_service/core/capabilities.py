"""Which optional components this box has - the capability contract.

An install offers six optional components (``install.sh``); the choice is
stored as ``COMPOSE_PROFILES`` in ``.env`` and handed to this container through
``docker-compose.yml``. Compose is the only thing that acts on the value, so it
stays the single source of truth - this module just reads it.

Three facts per feature:

* ``installed`` - the component was selected at install time. Comes from
  ``COMPOSE_PROFILES`` alone, so it stays true for a container that is merely
  stopped or unhealthy.
* ``running`` / ``healthy`` - the current container state, from
  ``container_registry`` (the same source ``/system/status`` uses).

**Fail-open.** When ``COMPOSE_PROFILES`` is absent or empty - which should not
happen, every install writes it - every optional feature counts as installed.
That is the pre-capability behaviour: nothing gets hidden because of missing
information.
"""

from __future__ import annotations

import os

import structlog

from backend_service.core import container_registry
from backend_service.core.api_errors import ApiError

logger = structlog.get_logger(__name__)

# Compose profile (docker-compose.yml / COMPOSE_PROFILES) -> feature key.
# Only "media" is renamed; the media-downloader is one service behind the
# profile and "media_downloader" is what the WebUI gates on.
PROFILE_TO_FEATURE: dict[str, str] = {
    "rfid": "rfid",
    "led": "led",
    "button": "button",
    "display": "display",
    "media": "media_downloader",
    "voice": "voice",
}

# Feature key -> container_registry service id (the Compose service name).
FEATURE_TO_SERVICE: dict[str, str] = {
    "rfid": "rfid",
    "led": "led",
    "button": "button",
    "display": "display",
    "media_downloader": "media-downloader",
    "voice": "tts",
}

# Stable order for the API response and for iterating.
OPTIONAL_FEATURES: tuple[str, ...] = tuple(FEATURE_TO_SERVICE)


def installed_features() -> set[str]:
    """The set of optional features selected at install time.

    Empty or missing ``COMPOSE_PROFILES`` -> every feature (fail-open).
    """
    raw = os.environ.get("COMPOSE_PROFILES")
    if not raw or not raw.strip():
        logger.warning("compose_profiles_unset_fail_open")
        return set(OPTIONAL_FEATURES)
    profiles = {p.strip() for p in raw.split(",") if p.strip()}
    return {
        feature
        for profile, feature in PROFILE_TO_FEATURE.items()
        if profile in profiles
    }


def feature_states_from(
    entries: list[dict] | None,
) -> dict[str, dict[str, bool]]:
    """``installed`` merged with the container state in *entries*.

    Split off from ``feature_states`` so a caller that already has the
    container list - the component catalogue reads the running version out of
    the same list - does not ask Docker a second time for the same answer.
    """
    installed = installed_features()
    by_service = (
        {e["service"]: e for e in entries if e.get("service")}
        if entries is not None
        else {}
    )

    result: dict[str, dict[str, bool]] = {}
    for feature in OPTIONAL_FEATURES:
        is_installed = feature in installed
        entry = by_service.get(FEATURE_TO_SERVICE[feature])
        if entries is None:
            # No Docker socket: running/healthy cannot be observed, so mirror
            # what was installed rather than claim everything is down.
            running = healthy = is_installed
        elif entry is None:
            running = healthy = False
        else:
            running = entry.get("docker_status") == "running"
            # "online" already folds in an unhealthy container ("error") and a
            # service that reports itself degraded ("degraded").
            healthy = running and entry.get("state") == "online"
        result[feature] = {
            "installed": is_installed,
            "running": running,
            "healthy": healthy,
        }
    return result


async def feature_states() -> dict[str, dict[str, bool]]:
    """``installed`` merged with the live container state, per optional feature."""
    return feature_states_from(await container_registry.discover())


def require_feature(feature: str) -> None:
    """Raise 409 ``feature_not_installed`` when *feature* was not installed.

    UI conditionals are not access control: this is what stops a direct API call
    for an absent component from a silent failure or a multi-second retry.
    """
    if feature not in installed_features():
        raise ApiError(
            status_code=409,
            code="feature_not_installed",
            detail=f"feature '{feature}' is not installed on this box",
        )
