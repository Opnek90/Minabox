"""What the optional components are - written for somebody who does not have them.

``capabilities.py`` answers what a box *has*; this module answers what it
*could* have. Without it the components section is a row of switches with a
name on them, and the only way to find out what "media import" needs, or that
the card reader wants a reboot before it can start, is the documentation
(#181).

Two sources, in this order:

* **The bundled file** ``resources/components.json``, shipped inside this image.
  It
  is what makes the catalogue work on a box that has never reached the
  internet - and that is the normal case for a box in a children's room.
* **The release manifest**, remembered whenever the update check has fetched
  it (``remember``). It carries the same block plus the published version per
  service, so a description can be corrected, and a not-yet-installed
  component can name the version it would bring, without a new backend image.

Only components this box's Compose file actually knows are offered. A manifest
from a newer release may describe a component that the local
``docker-compose.yml`` has no profile for; switching it on would write a
profile that starts nothing, so it is left out of the answer.

Which components exist at all is a decision, not a list that grows by itself:
a separate container is worth it when something brings a heavy or risky
dependency that should not sit in the backend image for everyone - ``yt-dlp``
in the media downloader is the model - while pure logic plus a settings form
belongs in the core. The reasoning is written down in
``docs/services/README.md``.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from backend_service.core import capabilities, container_registry

logger = structlog.get_logger(__name__)

BUNDLED_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "components.json"
)

#: Where the block from the last fetched manifest is kept. Next to the update
#: check's own cache, and just as disposable: deleting it costs a description,
#: not a state.
CACHE_NAME = "component-catalog.json"

LANGUAGES = ("de", "en")


def _cache_path() -> Path:
    return Path(os.environ.get("DATA_PATH", "/data")) / CACHE_NAME


@lru_cache(maxsize=1)
def _bundled() -> dict[str, Any]:
    """The catalogue shipped with this image. Never raises - an unreadable
    file costs the descriptions, not the components section."""
    try:
        data = json.loads(BUNDLED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("component_catalog_bundled_unreadable", error=str(e))
        return {}
    components = data.get("components")
    return components if isinstance(components, dict) else {}


def _cached() -> dict[str, Any]:
    """The block from the last fetched manifest: {"components", "services"}."""
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.debug("component_catalog_cache_unreadable", error=str(e))
        return {}
    return data if isinstance(data, dict) else {}


def remember(manifest: dict[str, Any]) -> None:
    """Keep what a fetched manifest says about the components.

    Called from the update check, not from here: the manifest is already on
    the wire there, and a components section that had to fetch it itself would
    stall for the whole timeout on a box without internet.
    """
    components = manifest.get("components")
    services = manifest.get("services") or {}
    payload = {
        "components": components if isinstance(components, dict) else {},
        # Only the two version fields; the release notes are the update
        # check's business and would blow this file up to the size of the
        # manifest.
        "services": {
            name: {
                "latest": info.get("latest"),
                "latest_beta": info.get("latest_beta"),
            }
            for name, info in services.items()
            if isinstance(info, dict)
        },
    }
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.debug("component_catalog_cache_unwritable", error=str(e))


def descriptions(cached: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Per profile the description, manifest before bundled file."""
    merged = dict(_bundled())
    remembered = _cached() if cached is None else cached
    for profile, entry in (remembered.get("components") or {}).items():
        if isinstance(entry, dict):
            merged[profile] = entry
    return merged


def _published(service: str, channel: str, cached: dict[str, Any]) -> str | None:
    """The version this channel would install for *service*, if it is known.

    Mirrors the channel rule of the update check: stable never looks at a
    release candidate, and beta falls back to the finished release when there
    is no candidate open.
    """
    info = (cached.get("services") or {}).get(service)
    if not isinstance(info, dict):
        return None
    latest = info.get("latest")
    if channel != "beta":
        return latest
    return info.get("latest_beta") or latest


def _text(value: Any) -> dict[str, str] | None:
    """One translated field, reduced to the languages the WebUI reads."""
    if not isinstance(value, dict):
        return None
    texts = {lang: str(value[lang]) for lang in LANGUAGES if value.get(lang)}
    return texts or None


def merge(
    payload: dict[str, Any],
    *,
    channel: str,
    entries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """The Host-Helper's answer, enriched into a catalogue.

    Both languages travel with every entry rather than one chosen here: the
    WebUI already knows which one is on screen, and the language of a REST call
    made by the backend for a browser is a question nobody has to answer that
    way.
    """
    # Read once: every entry asks it for a description and a version, and the
    # file is small but it is still a file.
    cached = _cached()
    catalog = descriptions(cached)
    states = capabilities.feature_states_from(entries)
    versions = {
        e["service"]: e.get("version")
        for e in (entries or [])
        if e.get("service")
    }

    known = payload.get("components")
    if not isinstance(known, list) or not known:
        # No Host-Helper. The catalogue is still worth showing - what can be
        # read here is read, only changing it is out of reach - so the profiles
        # of this image stand in for the list it would have sent.
        known = [
            {
                "profile": profile,
                "service": capabilities.FEATURE_TO_SERVICE[feature],
                "installed": feature in capabilities.installed_features(),
            }
            for profile, feature in capabilities.PROFILE_TO_FEATURE.items()
        ]

    components = []
    for component in known:
        if not isinstance(component, dict):
            continue
        profile = str(component.get("profile") or "")
        service = str(component.get("service") or "")
        feature = capabilities.PROFILE_TO_FEATURE.get(profile)
        described = catalog.get(profile) or {}
        state = states.get(feature or "") or {}
        installed = bool(component.get("installed"))
        components.append(
            {
                **component,
                "summary": _text(described.get("summary")),
                "hardware": _text(described.get("hardware")),
                "network": bool(described.get("network")),
                "running": bool(state.get("running")),
                "healthy": bool(state.get("healthy")),
                # What is on the box, and what the box would install. For a
                # component that is switched off there is no container and
                # therefore no version - only the second number.
                "version": versions.get(service) if installed else None,
                "latest": _published(service, channel, cached),
            }
        )

    # The channel is a property of the box, not of a single component, so it
    # is named once - the same way the update check reports it.
    return {**payload, "components": components, "channel": channel}


async def enrich(payload: dict[str, Any], *, channel: str) -> dict[str, Any]:
    """`merge`, with the container list fetched here."""
    return merge(payload, channel=channel, entries=await container_registry.discover())
