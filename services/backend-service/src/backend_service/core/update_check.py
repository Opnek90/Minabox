"""Compares the running service versions against the published ones.

The source is `release/release-manifest.json` in the repository:
one file, one request, per service the current version and the release notes in
both languages.

Two rules shape this module:

* **No network never means "update available".** When the fetch fails, the last
  known state is shown and the error is named - never an update that nobody
  could verify.
* **Only offer what can actually be pulled.** The manifest is published with the
  commit, the images only once CI is through. In that window it knows a version
  the registry does not have yet, so every candidate is checked against the
  registry before it is offered.

On top of that sits the channel. A box on the stable channel reads the
manifest's ``latest`` and never sees a release candidate; a box on beta reads
``latest_beta`` and gets them as soon as they are published. The choice is a
setting, and switching it back is enough to be offered the finished version
again - there is nothing to reinstall.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from backend_service.core import container_registry
from backend_service.core.general_settings import read_general_settings
from backend_service.core.system_alerts import clear_alert, set_alert

logger = structlog.get_logger(__name__)

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Opnek90/Minabox/main/release/release-manifest.json"
)
DEFAULT_REGISTRY = "ghcr.io/opnek90"

# Six hours: often enough that an update does not go unnoticed for weeks, rare
# enough that nobody brushes against GitHub's rate limits.
CACHE_TTL_SECONDS = 6 * 60 * 60
FETCH_TIMEOUT = 10.0

# How often the background scan looks. The fetch itself stays throttled by
# CACHE_TTL_SECONDS - this interval only decides how quickly a freshly enabled
# scan reacts and keeps the header hint current.
POLL_INTERVAL_SECONDS = 30 * 60

ALERT_UPDATE_AVAILABLE = "update_available"

#: The channels a box can follow. "stable" is what an untouched box gets.
CHANNELS = ("stable", "beta")
DEFAULT_CHANNEL = "stable"


def _read_auto_update_check_enabled() -> bool:
    """Whether the background scan should run (default: off)."""
    return bool(read_general_settings().get("auto_update_check_enabled", False))


def clamp_channel(value: Any) -> str:
    """Turn whatever is in the settings file into a channel name."""
    text = str(value or "").strip().lower()
    return text if text in CHANNELS else DEFAULT_CHANNEL


def read_update_channel() -> str:
    """The channel this box follows (default: stable)."""
    return clamp_channel(read_general_settings().get("update_channel"))


def _manifest_url() -> str:
    return os.environ.get("MINABOX_MANIFEST_URL") or DEFAULT_MANIFEST_URL


def _cache_path() -> Path:
    return Path(os.environ.get("DATA_PATH", "/data")) / "update-check.json"


def parse_version(version: str) -> tuple:
    """Sort key for a SemVer string; a pre-release marker sorts before it."""
    core, _, pre = version.partition("-")
    try:
        numbers = tuple(int(part) for part in core.split("."))
    except ValueError:
        return ((0,), 0, version)
    return (numbers, 1 if not pre else 0, pre)


def is_newer(candidate: str, installed: str) -> bool:
    return parse_version(candidate) > parse_version(installed)


def channel_of(version: str) -> str:
    """Which channel a version belongs to - the marker in the string decides.

    Mirrors ``channel_of`` in scripts/build_manifest.py. It is repeated here so
    a manifest written before the channel field existed is still read
    correctly, instead of counting every old entry as stable.
    """
    return "beta" if "-" in (version or "") else "stable"


def _in_channel(version: str, channel: str) -> bool:
    """Beta sees everything; stable only the finished releases."""
    return channel == "beta" or channel_of(version) == "stable"


async def _fetch_manifest(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(_manifest_url())
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or "services" not in data:
        raise ValueError("Manifest has no 'services' field")
    return data


async def _tag_exists(client: httpx.AsyncClient, image: str, tag: str) -> bool:
    """Is this image really in the registry under this tag?

    Without the check, the window between the commit and the finished CI build
    would offer an update that the pull cannot find.
    """
    repository = image.split("/", 1)[1] if "/" in image else image
    try:
        token_response = await client.get(
            "https://ghcr.io/token",
            params={"scope": f"repository:{repository}:pull", "service": "ghcr.io"},
        )
        token = token_response.json().get("token") if token_response.is_success else None
        if not token:
            # Private packages cannot be checked. Better to offer than to
            # withhold for no reason - the pull will say so if it has to.
            logger.debug("registry_token_unavailable", image=image)
            return True
        manifest = await client.head(
            f"https://ghcr.io/v2/{repository}/manifests/{tag}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json, "
                    "application/vnd.oci.image.manifest.v1+json"
                ),
            },
        )
        return manifest.is_success
    except Exception as e:
        logger.debug("registry_check_failed", image=image, tag=tag, error=str(e))
        return True


def _read_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.debug("update_cache_unreadable", error=str(e))
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.debug("update_cache_unwritable", error=str(e))


def _channel_target(info: dict[str, Any], channel: str) -> str | None:
    """The newest version this channel offers for one service.

    On beta that is ``latest_beta`` when the manifest carries one, otherwise
    the stable release - a service that has no release candidate open must not
    fall off the list just because the box follows beta.
    """
    latest = info.get("latest")
    if channel != "beta":
        return latest
    candidate = info.get("latest_beta") or latest
    if latest and candidate and is_newer(latest, candidate):
        # A stable release published after the last candidate. Beta is meant
        # to be ahead of stable, never behind it.
        return latest
    return candidate


def _build_entries(
    manifest: dict[str, Any], installed: dict[str, str], channel: str = DEFAULT_CHANNEL
) -> list[dict[str, Any]]:
    """Per service: what runs, what exists, and what happened in between."""
    entries: list[dict[str, Any]] = []
    services = manifest.get("services") or {}

    for service, running in sorted(installed.items()):
        info = services.get(service)
        if not info:
            # A service with no manifest entry - the MQTT broker, say, which
            # comes from a third-party image. It is shown, but never reported
            # as outdated.
            entries.append(
                {
                    "service": service,
                    "installed": running,
                    "latest": None,
                    "update_available": False,
                    "managed": False,
                    "channel": channel_of(running),
                    "releases": [],
                }
            )
            continue

        latest = _channel_target(info, channel)
        newer = [
            release
            for release in info.get("releases") or []
            if release.get("version")
            and is_newer(release["version"], running)
            # A release candidate stays out of sight on the stable channel,
            # including in the notes - reading about a change that will not
            # arrive is worse than not reading about it.
            and _in_channel(release["version"], channel)
        ]
        newer.sort(key=lambda r: parse_version(r["version"]), reverse=True)

        entries.append(
            {
                "service": service,
                "installed": running,
                "latest": latest,
                "update_available": bool(latest and is_newer(latest, running)),
                "managed": True,
                # Which channel the *running* version came from. A box that
                # switched back to stable still shows its beta build as one.
                "channel": channel_of(running),
                # Every release that was skipped, not just the newest: two
                # versions behind, and half the information would be lost.
                "releases": newer,
            }
        )
    return entries


def _cached_services(cached: dict[str, Any]) -> set[str]:
    """The services a cached answer was computed for."""
    entries = (cached.get("result") or {}).get("services") or []
    return {e.get("service") for e in entries if isinstance(e, dict)}


def _only_installed(result: dict[str, Any], installed: dict[str, str]) -> dict[str, Any]:
    """The same answer without the services this box no longer has.

    Untouched when nothing is missing. Rebuilding the top-level flag from the
    entries is only correct where an entry was actually dropped; doing it
    always would overwrite what an earlier run concluded.
    """
    all_entries = result.get("services") or []
    entries = [
        e for e in all_entries if isinstance(e, dict) and e.get("service") in installed
    ]
    if len(entries) == len(all_entries):
        return result
    return {
        **result,
        "services": entries,
        # The header hint hangs off this, so a withdrawn entry has to withdraw
        # its update with it.
        "update_available": any(e.get("update_available") for e in entries),
    }


async def check(installed: dict[str, str], *, force: bool = False) -> dict[str, Any]:
    """Work out the update state. `installed` is {service: running version}."""
    channel = read_update_channel()
    cached = _read_cache()
    if not force and cached:
        age = time.time() - float(cached.get("cached_at") or 0)
        # A cached answer belongs to the channel it was computed for. After a
        # switch it would name the wrong versions, so it counts as a miss -
        # the one extra fetch is the price of not lying about the target.
        same_channel = (cached.get("result") or {}).get("channel", DEFAULT_CHANNEL) == channel
        # And it belongs to the components the box had at the time. Switching
        # one off removes its container, so it drops out of `installed` - but
        # the cache would keep listing it, and keep offering an update for six
        # hours that "compose pull" could no longer even carry out.
        same_services = _cached_services(cached) == set(installed)
        if age < CACHE_TTL_SECONDS and same_channel and same_services:
            return {**cached["result"], "from_cache": True}

    def _stale(error: str) -> dict[str, Any]:
        """On failure: show the last known state, but claim nothing.

        Trimmed to what the box still has. Nothing is invented here - entries
        for components that were switched off in the meantime are dropped,
        because a version for a component that is gone is not "last known
        state" but a leftover.
        """
        if cached:
            return {
                **_only_installed(cached["result"], installed),
                "from_cache": True,
                "error": error,
            }
        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "from_cache": False,
            "update_available": False,
            "channel": channel,
            "error": error,
            "services": [
                {
                    "service": name,
                    "installed": version,
                    "latest": None,
                    "update_available": False,
                    "managed": False,
                    "channel": channel_of(version),
                    "releases": [],
                }
                for name, version in sorted(installed.items())
            ],
        }

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            manifest = await _fetch_manifest(client)
            entries = _build_entries(manifest, installed, channel)

            registry = manifest.get("registry") or DEFAULT_REGISTRY
            pending = [e for e in entries if e["update_available"]]
            if pending:
                results = await asyncio.gather(
                    *(
                        _tag_exists(
                            client, f"{registry}/minabox-{e['service']}", e["latest"]
                        )
                        for e in pending
                    )
                )
                for entry, published in zip(pending, results, strict=True):
                    if not published:
                        # The manifest is ahead of CI - offer nothing yet.
                        entry["update_available"] = False
                        entry["pending_publish"] = True
                        entry["releases"] = []
                        logger.info(
                            "update_not_published_yet",
                            service=entry["service"],
                            version=entry["latest"],
                        )
    except Exception as e:
        logger.warning("update_check_failed", error=f"{type(e).__name__}: {e}")
        return _stale(f"{type(e).__name__}: {e}")

    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "from_cache": False,
        "update_available": any(e["update_available"] for e in entries),
        "channel": channel,
        "error": None,
        "services": entries,
    }
    _write_cache({"cached_at": time.time(), "result": result})
    return result


async def apply_alert(result: dict[str, Any], ws_broadcast: Any) -> None:
    """Reconcile the header hint with the finding: set it, or withdraw it.

    A failed fetch (`result["error"]`) must not clear the hint - that would be
    exactly the withholding this module rules out above. It simply stays until
    a fetch succeeds.
    """
    if result.get("error"):
        return

    if result.get("update_available"):
        set_alert(ALERT_UPDATE_AVAILABLE, "info", "alerts.update_available")
        if ws_broadcast:
            try:
                await ws_broadcast({
                    "type": "system_alert",
                    "data": {
                        "level": "info",
                        "code": ALERT_UPDATE_AVAILABLE,
                        "message": "alerts.update_available",
                    },
                })
            except Exception as e:
                logger.debug("update_check_ws_broadcast_failed", error=str(e))
    elif clear_alert(ALERT_UPDATE_AVAILABLE) and ws_broadcast:
        try:
            await ws_broadcast({
                "type": "system_alert_cleared",
                "data": {"code": ALERT_UPDATE_AVAILABLE},
            })
        except Exception as e:
            logger.debug("update_check_ws_broadcast_failed", error=str(e))


async def run_update_check_loop(ws_broadcast: Any) -> None:
    """Background task: check for updates regularly, while switched on.

    The network fetch stays throttled by the cache in `check()`
    (CACHE_TTL_SECONDS) - this task only asks more often whether a fresh look
    is due, and keeps the header hint current.
    """
    await asyncio.sleep(60)  # initial delay before first check

    while True:
        try:
            if _read_auto_update_check_enabled():
                entries = await container_registry.discover()
                installed = {
                    e["service"]: e["version"]
                    for e in (entries or [])
                    if e.get("service") and e.get("version")
                }
                if installed:
                    result = await check(installed, force=False)
                    await apply_alert(result, ws_broadcast)
        except asyncio.CancelledError:
            break
        except Exception as e:
            # A failed round must not end the background task.
            logger.warning("update_check_loop_failed", error=str(e))

        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break

    logger.info("update_check_loop_stopped")
