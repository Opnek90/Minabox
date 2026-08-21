"""Vergleicht die laufenden Dienstversionen mit dem veroeffentlichten Stand.

Die Quelle ist `release-manifest.json` im Repository (docs/Versionierung.md):
eine Datei, ein Abruf, je Dienst die aktuelle Version und die
Aenderungsnotizen in beiden Sprachen.

Zwei Regeln bestimmen den Aufbau:

* **Kein Netz heisst niemals "Update verfuegbar".** Faellt der Abruf aus, wird
  der letzte bekannte Stand gezeigt und der Fehler benannt - nie ein Update
  behauptet, das niemand pruefen konnte.
* **Angeboten wird nur, was auch abholbar ist.** Das Manifest wird mit dem
  Commit veroeffentlicht, die Images erst wenn die CI durch ist. In diesem
  Fenster kennt es eine Version, die es in der Registry noch nicht gibt.
  Deshalb wird vor jedem Angebot geprueft, ob der Image-Tag wirklich liegt.
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

logger = structlog.get_logger(__name__)

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Opnek90/Minabox/main/release-manifest.json"
)
DEFAULT_REGISTRY = "ghcr.io/opnek90"

# Sechs Stunden: haeufig genug, dass ein Update nicht wochenlang unbemerkt
# bleibt, selten genug, dass niemand die GitHub-Grenzen streift.
CACHE_TTL_SECONDS = 6 * 60 * 60
FETCH_TIMEOUT = 10.0


def _manifest_url() -> str:
    return os.environ.get("MINABOX_MANIFEST_URL") or DEFAULT_MANIFEST_URL


def _cache_path() -> Path:
    return Path(os.environ.get("DATA_PATH", "/data")) / "update-check.json"


def parse_version(version: str) -> tuple:
    """Sortierschluessel fuer SemVer; ein Vorab-Kennzeichen sortiert davor."""
    core, _, pre = version.partition("-")
    try:
        numbers = tuple(int(part) for part in core.split("."))
    except ValueError:
        return ((0,), 0, version)
    return (numbers, 1 if not pre else 0, pre)


def is_newer(candidate: str, installed: str) -> bool:
    return parse_version(candidate) > parse_version(installed)


async def _fetch_manifest(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(_manifest_url())
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or "services" not in data:
        raise ValueError("Manifest hat kein 'services'-Feld")
    return data


async def _tag_exists(client: httpx.AsyncClient, image: str, tag: str) -> bool:
    """Liegt dieses Image mit diesem Tag wirklich in der Registry?

    Ohne diese Pruefung wuerde in dem Fenster zwischen Commit und fertigem
    CI-Build ein Update angeboten, das der Pull nicht finden kann.
    """
    repository = image.split("/", 1)[1] if "/" in image else image
    try:
        token_response = await client.get(
            "https://ghcr.io/token",
            params={"scope": f"repository:{repository}:pull", "service": "ghcr.io"},
        )
        token = token_response.json().get("token") if token_response.is_success else None
        if not token:
            # Private Pakete koennen wir nicht pruefen. Dann lieber anbieten
            # als grundlos verschweigen - der Pull meldet sich notfalls selbst.
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


def _build_entries(
    manifest: dict[str, Any], installed: dict[str, str]
) -> list[dict[str, Any]]:
    """Je Dienst: was laeuft, was es gibt, und was dazwischen passiert ist."""
    entries: list[dict[str, Any]] = []
    services = manifest.get("services") or {}

    for service, running in sorted(installed.items()):
        info = services.get(service)
        if not info:
            # Ein Dienst ohne Eintrag im Manifest - etwa der MQTT-Broker, der
            # aus einem fremden Image kommt. Er wird gezeigt, aber nie als
            # veraltet gemeldet.
            entries.append(
                {
                    "service": service,
                    "installed": running,
                    "latest": None,
                    "update_available": False,
                    "managed": False,
                    "releases": [],
                }
            )
            continue

        latest = info.get("latest")
        newer = [
            release
            for release in info.get("releases") or []
            if release.get("version") and is_newer(release["version"], running)
        ]
        newer.sort(key=lambda r: parse_version(r["version"]), reverse=True)

        entries.append(
            {
                "service": service,
                "installed": running,
                "latest": latest,
                "update_available": bool(latest and is_newer(latest, running)),
                "managed": True,
                # Alle uebersprungenen Ausgaben, nicht nur die neueste - wer
                # zwei Versionen ueberspringt, verlaere sonst die Haelfte der
                # Information.
                "releases": newer,
            }
        )
    return entries


async def check(installed: dict[str, str], *, force: bool = False) -> dict[str, Any]:
    """Update-Stand ermitteln. `installed` ist {dienst: laufende Version}."""
    cached = _read_cache()
    if not force and cached:
        age = time.time() - float(cached.get("cached_at") or 0)
        if age < CACHE_TTL_SECONDS:
            return {**cached["result"], "from_cache": True}

    def _stale(error: str) -> dict[str, Any]:
        """Fehlerfall: den letzten bekannten Stand zeigen, aber nichts behaupten."""
        if cached:
            return {**cached["result"], "from_cache": True, "error": error}
        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "from_cache": False,
            "update_available": False,
            "error": error,
            "services": [
                {
                    "service": name,
                    "installed": version,
                    "latest": None,
                    "update_available": False,
                    "managed": False,
                    "releases": [],
                }
                for name, version in sorted(installed.items())
            ],
        }

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            manifest = await _fetch_manifest(client)
            entries = _build_entries(manifest, installed)

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
                        # Das Manifest ist der CI voraus - noch nichts anbieten.
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
        "error": None,
        "services": entries,
    }
    _write_cache({"cached_at": time.time(), "result": result})
    return result
