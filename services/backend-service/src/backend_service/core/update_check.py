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
* **Never offer a combination nobody built.** A release may say what it needs
  from the other services (``requires`` in the manifest, #194). Where that can
  be met by an update this box is being offered anyway, the other service goes
  along in the same run; where it cannot, the candidate is held back and the
  reason is named - the same shape the rollback lock has always used.

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
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from backend_service.core import component_catalog, container_registry
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

#: The one expression a requirement may use - mirrors RE_REQUIREMENT in
#: scripts/build_manifest.py. Anything else is ignored rather than guessed at:
#: a requirement this build cannot read is one it must not act on, in either
#: direction.
RE_MINIMUM = re.compile(r"^>=\s*(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$")

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


def _minimum(expression: Any) -> str | None:
    """The version a requirement asks for at least, or None if unreadable."""
    match = RE_MINIMUM.match(str(expression or "").strip())
    return match.group(1) if match else None


def requirements_of(info: dict[str, Any], version: str | None) -> dict[str, str]:
    """What one published version of a service needs from the others.

    ``{"backend": "0.4.0"}`` - the bare minimum version, not the ``>=`` the
    manifest writes. Callers compare it, they do not print it.

    A version the manifest does not describe - a development build, or one
    older than the oldest entry - needs nothing as far as this box can tell.
    Guessing from a neighbouring release would be inventing a statement that
    nobody made.
    """
    for release in info.get("releases") or []:
        if release.get("version") != version:
            continue
        raw = release.get("requires")
        if not isinstance(raw, dict):
            return {}
        return {
            str(name): found
            for name, expression in raw.items()
            if (found := _minimum(expression))
        }
    return {}


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
                    "requires": {},
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
                # What the *running* build needs from the others - not what
                # the candidate needs. This is the field the rollback lock
                # reads: a step back is dangerous when it drops a service
                # below what something running today asks of it.
                "requires": requirements_of(info, running),
                # Every release that was skipped, not just the newest: two
                # versions behind, and half the information would be lost.
                "releases": newer,
            }
        )
    return entries


def _apply_requirements(
    manifest: dict[str, Any], entries: list[dict[str, Any]], installed: dict[str, str]
) -> None:
    """Settle what a candidate needs from the others - take it along, or wait.

    Runs after the registry check, and it has to: whether a requirement can be
    met depends on what is really on offer, and a candidate the registry does
    not have yet cannot carry anyone.

    Three answers per requirement:

    * what runs today is already enough - nothing to say;
    * it is not enough, but the other service is being offered a version that
      is: it goes along in the same run (``requires_pull``), because
      ``POST /system/update`` takes several targets;
    * neither - the candidate is held back and says why (``requires_unmet``).
      That is the honest answer for the case the requirement points at
      something that is not published yet, or at a service this box updates
      later for a reason of its own.

    A required service the box does not have at all counts as met. There is no
    combination to split: the requirement is about a container that is not
    running here, and holding an update back over it would be a refusal
    nobody could act on.

    Held back once, held back for good within one run: a candidate that drops
    out lowers what the others may count on, so the rounds repeat until
    nothing changes. Only blocking ever happens, never unblocking, so it ends.
    """
    services = manifest.get("services") or {}
    by_service = {e["service"]: e for e in entries}

    def planned(name: str) -> str | None:
        """The version *name* would run once this update run is through."""
        entry = by_service.get(name)
        if entry and entry.get("update_available") and entry.get("latest"):
            return entry["latest"]
        return installed.get(name)

    for _ in range(len(entries) + 1):
        blocked_any = False
        for entry in entries:
            if not entry.get("update_available"):
                continue

            info = services.get(entry["service"]) or {}
            pull: list[dict[str, str]] = []
            unmet: list[dict[str, str]] = []

            for name, minimum in sorted(
                requirements_of(info, entry["latest"]).items()
            ):
                current = installed.get(name)
                if current is None or not is_newer(minimum, current):
                    continue
                target = planned(name)
                if target and not is_newer(minimum, target):
                    pull.append({"service": name, "version": target})
                else:
                    unmet.append(
                        {"service": name, "minimum": minimum, "installed": current}
                    )

            if unmet:
                blocked_any = True
                entry["update_available"] = False
                entry["requires_unmet"] = unmet
                entry.pop("requires_pull", None)
                # Same reasoning as pending_publish: notes about a version
                # that is not going to arrive read like a promise.
                entry["releases"] = []
                logger.info(
                    "update_requirements_unmet",
                    service=entry["service"],
                    version=entry["latest"],
                    unmet=unmet,
                )
            elif pull:
                entry["requires_pull"] = pull
            else:
                entry.pop("requires_pull", None)

        if not blocked_any:
            break


def companions(targets: dict[str, str]) -> dict[str, str]:
    """The services that have to travel with *targets*, per the last check.

    Read from the remembered answer rather than fetched again: the update
    button is pressed on a box that has just been told what is on offer, and a
    second fetch would put the whole network timeout in front of a run the
    user has already confirmed. Without a cached answer nothing is added -
    that is the state before the first check, where there is no requirement
    this box knows of either.

    A service pulled in can bring its own requirement, so the list is walked
    until it stops growing.
    """
    cached = _read_cache() or {}
    by_service = {
        e["service"]: e
        for e in (cached.get("result") or {}).get("services") or []
        if isinstance(e, dict) and e.get("service")
    }

    extra: dict[str, str] = {}
    queue = list(targets)
    while queue:
        entry = by_service.get(queue.pop()) or {}
        for companion in entry.get("requires_pull") or []:
            name, version = companion.get("service"), companion.get("version")
            if not name or not version or name in targets or name in extra:
                continue
            extra[name] = version
            queue.append(name)
    return extra


def declared_requirements() -> dict[str, dict[str, str]]:
    """Per running service, what it needs from the others - per the last check.

    The rollback lock reads this. Stepping one service back below what another
    running service asks of it splits the box in exactly the way an update is
    held back for, and it is the same question asked from the other end.

    From the cache, like `companions`: pressing *step back* must not wait out
    a network timeout. A box that has never run a check knows of no
    requirement and locks nothing - which is the same "claim nothing without
    having looked" the module opens with.
    """
    cached = _read_cache() or {}
    result: dict[str, dict[str, str]] = {}
    for entry in (cached.get("result") or {}).get("services") or []:
        if not isinstance(entry, dict):
            continue
        wanted = entry.get("requires")
        if isinstance(wanted, dict) and wanted:
            result[str(entry.get("service"))] = {
                str(name): str(minimum) for name, minimum in wanted.items()
            }
    return result


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
                    "requires": {},
                    "releases": [],
                }
                for name, version in sorted(installed.items())
            ],
        }

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            manifest = await _fetch_manifest(client)
            # The catalogue rides along on this one fetch: the manifest also
            # describes the components that are *not* installed, and asking
            # for the file a second time from there would stall the whole
            # timeout on a box without internet.
            component_catalog.remember(manifest)
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

            # Last, and after the registry: a candidate that is not really
            # published cannot satisfy anybody's requirement either.
            _apply_requirements(manifest, entries, installed)
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
