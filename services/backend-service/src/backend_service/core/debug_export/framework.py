"""Collector registry, runner and archive builder for the debug export.

The rules this module enforces (see docs/DebugExport.md, section 4):

* A collector is selected by *name* from a registry - never by a path or a
  command coming from the request. Unknown name means the option is ignored,
  not passed through.
* No collector can break the export. Each runs isolated with a timeout and its
  outcome lands in the manifest as ok / failed / skipped, because "display logs
  unavailable" is itself a diagnosis.
* Every file passes through redaction, and the finished payload is checked
  against the device's real secrets before it is written.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from backend_service.core.debug_export.redaction import (
    SecretTripwire,
    scrub,
    scrub_text,
)

logger = structlog.get_logger(__name__)

SCHEMA_VERSION = 1
DEFAULT_MAX_TOTAL_BYTES = 25 * 1024 * 1024
DEFAULT_LOG_TAIL = 2000
MAX_LOG_TAIL = 5000

# Dialog building blocks. The WebUI shows these; collectors declare which one
# they belong to, so a deselected block simply never runs.
BLOCK_SYSTEM = "system"
BLOCK_LOGS = "logs"
BLOCK_SETTINGS = "settings"
BLOCK_NETWORK = "network"
BLOCK_MEDIA = "media"
BLOCK_HISTORY = "history"
BLOCK_CLIENT = "client"
BLOCK_DATABASE = "database"

MEDIA_OFF = "off"
MEDIA_COUNTS = "counts"
MEDIA_FILENAMES = "filenames"


@dataclass
class ExportOptions:
    """What the user ticked in the dialog.

    Parsed defensively: this is the only request-shaped input the export takes,
    and it must never turn into a path or a command.
    """

    system: bool = True
    logs: bool = True
    settings: bool = True
    network: bool = True
    media: str = MEDIA_COUNTS
    history: bool = False
    client: bool = True
    include_db: bool = False
    log_tail: int = DEFAULT_LOG_TAIL
    preset: str = "recommended"

    @classmethod
    def from_payload(cls, raw: dict[str, Any] | None) -> ExportOptions:
        raw = raw or {}
        preset = str(raw.get("preset") or "recommended")
        base = _PRESET_VALUES.get(preset, _PRESET_VALUES["recommended"]).copy()
        base["preset"] = preset if preset in _PRESET_VALUES else "recommended"

        for flag in (
            "system",
            "logs",
            "settings",
            "network",
            "history",
            "client",
            "include_db",
        ):
            if flag in raw:
                base[flag] = bool(raw[flag])

        if "media" in raw:
            media = str(raw["media"]).lower()
            base["media"] = (
                media
                if media in (MEDIA_OFF, MEDIA_COUNTS, MEDIA_FILENAMES)
                else MEDIA_COUNTS
            )

        if "log_tail" in raw:
            try:
                base["log_tail"] = max(50, min(int(raw["log_tail"]), MAX_LOG_TAIL))
            except (TypeError, ValueError):
                base["log_tail"] = DEFAULT_LOG_TAIL

        # The technical state of the box is what makes the archive worth
        # sending at all, so it is not switchable.
        base["system"] = True
        return cls(**base)

    def restrict_to_standard(self) -> ExportOptions:
        """Drop everything that needs an admin session (see section 4.5)."""
        self.history = False
        self.include_db = False
        if self.media == MEDIA_FILENAMES:
            self.media = MEDIA_COUNTS
        return self

    def block_enabled(self, block: str) -> bool:
        return {
            BLOCK_SYSTEM: self.system,
            BLOCK_LOGS: self.logs,
            BLOCK_SETTINGS: self.settings,
            BLOCK_NETWORK: self.network,
            BLOCK_MEDIA: self.media != MEDIA_OFF,
            BLOCK_HISTORY: self.history,
            BLOCK_CLIENT: self.client,
            BLOCK_DATABASE: self.include_db,
        }.get(block, False)

    def as_manifest(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "system": self.system,
            "logs": self.logs,
            "settings": self.settings,
            "network": self.network,
            "media": self.media,
            "history": self.history,
            "client": self.client,
            "include_db": self.include_db,
            "log_tail": self.log_tail,
        }


_PRESET_VALUES: dict[str, dict[str, Any]] = {
    "minimal": {
        "system": True,
        "logs": False,
        "settings": False,
        "network": True,
        "media": MEDIA_OFF,
        "history": False,
        "client": False,
        "include_db": False,
        "log_tail": DEFAULT_LOG_TAIL,
    },
    "recommended": {
        "system": True,
        "logs": True,
        "settings": True,
        "network": True,
        "media": MEDIA_COUNTS,
        "history": False,
        "client": True,
        "include_db": False,
        "log_tail": DEFAULT_LOG_TAIL,
    },
    "full": {
        "system": True,
        "logs": True,
        "settings": True,
        "network": True,
        "media": MEDIA_FILENAMES,
        "history": True,
        "client": True,
        "include_db": False,
        "log_tail": MAX_LOG_TAIL,
    },
}


@dataclass
class ExportContext:
    """Everything a collector may read. Deliberately small."""

    options: ExportOptions
    salt: str
    data_path: Path
    device_id: str
    client_payload: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Collector:
    name: str
    block: str
    fn: Callable[[ExportContext], Any]
    timeout: float = 10.0
    # Large, truncatable output (logs). Written last so the size budget eats
    # into them before it touches anything essential.
    bulky: bool = False


REGISTRY: dict[str, Collector] = {}


def register(name: str, block: str, *, timeout: float = 10.0, bulky: bool = False):
    """Register a collector under a fixed name (the allowlist)."""

    def decorator(fn: Callable[[ExportContext], Any]) -> Callable[[ExportContext], Any]:
        if name in REGISTRY:
            raise ValueError(f"Collector {name} bereits registriert")
        REGISTRY[name] = Collector(
            name=name, block=block, fn=fn, timeout=timeout, bulky=bulky
        )
        return fn

    return decorator


@dataclass
class CollectorOutcome:
    name: str
    status: str
    ms: int
    files: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_manifest(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "ms": self.ms,
        }
        if self.error:
            entry["error"] = self.error[:300]
        return entry


# Keys a collector uses when it has nothing but a failure to report. A payload
# carrying one of these *alongside* real data (docker.json's "info_error", say)
# is a partial result and still counts as ok.
_ERROR_ONLY_KEYS = frozenset({"error", "detail", "hint"})


def _error_only_payload(payload: Any) -> str | None:
    """Return the error message if this file is nothing but an error object."""
    if isinstance(payload, dict) and payload:
        keys = set(payload)
        if "error" in keys and keys <= _ERROR_ONLY_KEYS:
            return str(payload["error"])
    return None


async def _run_one(collector: Collector, ctx: ExportContext) -> CollectorOutcome:
    started = time.monotonic()
    try:
        if inspect.iscoroutinefunction(collector.fn):
            files = await asyncio.wait_for(collector.fn(ctx), timeout=collector.timeout)
        else:
            files = await asyncio.wait_for(
                asyncio.to_thread(collector.fn, ctx), timeout=collector.timeout
            )
    except TimeoutError:
        ms = int((time.monotonic() - started) * 1000)
        logger.warning("debug_export_collector_timeout", collector=collector.name)
        return CollectorOutcome(
            collector.name, "failed", ms, error="Zeitüberschreitung"
        )
    except Exception as e:  # a broken box is exactly when this runs
        ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "debug_export_collector_failed", collector=collector.name, error=str(e)
        )
        return CollectorOutcome(
            collector.name, "failed", ms, error=f"{type(e).__name__}: {e}"
        )

    ms = int((time.monotonic() - started) * 1000)
    files = files or {}
    if not isinstance(files, dict):
        return CollectorOutcome(
            collector.name, "failed", ms, error="Collector lieferte kein Dateiobjekt"
        )
    if not files:
        return CollectorOutcome(collector.name, "empty", ms)

    # A collector that caught its own exception and returned it as file content
    # used to land in the manifest as "ok" - the triage then reported "kein
    # Befund" while the data was in fact missing. Judged here, centrally, so a
    # new collector cannot get this wrong again.
    errors = [_error_only_payload(payload) for payload in files.values()]
    if all(error is not None for error in errors):
        return CollectorOutcome(
            collector.name,
            "failed",
            ms,
            files=files,
            error="; ".join(dict.fromkeys(errors)),
        )

    return CollectorOutcome(collector.name, "ok", ms, files=files)


async def run_collectors(
    ctx: ExportContext, concurrency: int = 4
) -> list[CollectorOutcome]:
    """Run every selected collector, bounded - this also runs on a Pi Zero."""
    semaphore = asyncio.Semaphore(concurrency)
    outcomes: list[CollectorOutcome] = []
    selected: list[Collector] = []

    for collector in REGISTRY.values():
        if ctx.options.block_enabled(collector.block):
            selected.append(collector)
        else:
            outcomes.append(CollectorOutcome(collector.name, "skipped_by_user", 0))

    async def guarded(collector: Collector) -> CollectorOutcome:
        async with semaphore:
            return await _run_one(collector, ctx)

    results = await asyncio.gather(*(guarded(c) for c in selected))
    outcomes.extend(results)
    outcomes.sort(key=lambda o: o.name)
    return outcomes


def _serialize(content: Any) -> str:
    """Turn a collector's value into redacted text."""
    if isinstance(content, str):
        return scrub_text(content)
    if isinstance(content, bytes):
        return scrub_text(content.decode("utf-8", errors="replace"))
    return json.dumps(scrub(content), indent=2, ensure_ascii=False, default=str)


def _tail(text: str, max_bytes: int) -> tuple[str, int, int]:
    """Keep the end of a log - the interesting part is always the last lines."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, 0, text.count("\n") + 1
    lines = text.splitlines()
    kept: list[str] = []
    size = 0
    for line in reversed(lines):
        size += len(line.encode("utf-8", errors="replace")) + 1
        if size > max_bytes:
            break
        kept.append(line)
    kept.reverse()
    return "\n".join(kept), len(lines), len(kept)


def build_archive(
    ctx: ExportContext,
    outcomes: list[CollectorOutcome],
    tripwire: SecretTripwire,
    *,
    versions: dict[str, Any] | None = None,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> tuple[bytes, dict[str, Any]]:
    """Assemble the ZIP. Returns (archive bytes, manifest)."""
    truncations: list[dict[str, Any]] = []
    leaks: list[dict[str, Any]] = []
    written: list[dict[str, Any]] = []

    # Essential files first, bulky logs last: the size budget must eat into the
    # logs, never into the manifest or the system state.
    bulky_names = {c.name for c in REGISTRY.values() if c.bulky}
    ordered = sorted(outcomes, key=lambda o: (o.name in bulky_names, o.name))

    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for outcome in ordered:
            for rel_path, content in outcome.files.items():
                text = _serialize(content)

                text, found = tripwire.redact(text)
                if found:
                    # Loud, not silent: the value is removed *and* the manifest
                    # records which collector leaked what.
                    still = tripwire.find(text)
                    if still:
                        raise SecretLeakUnresolved(rel_path, still)
                    leaks.append(
                        {"path": rel_path, "collector": outcome.name, "secrets": found}
                    )
                    logger.error(
                        "debug_export_secret_blocked",
                        collector=outcome.name,
                        path=rel_path,
                        secrets=found,
                    )

                encoded_len = len(text.encode("utf-8", errors="replace"))
                remaining = max_total_bytes - total
                if encoded_len > remaining:
                    if outcome.name not in bulky_names or remaining < 4096:
                        truncations.append(
                            {
                                "path": rel_path,
                                "status": "dropped",
                                "reason": "Größenbudget",
                            }
                        )
                        continue
                    text, total_lines, kept_lines = _tail(text, remaining)
                    truncations.append(
                        {
                            "path": rel_path,
                            "status": "truncated",
                            "kept_lines": kept_lines,
                            "total_lines": total_lines,
                        }
                    )
                    encoded_len = len(text.encode("utf-8", errors="replace"))

                archive.writestr(rel_path, text)
                total += encoded_len
                written.append({"path": rel_path, "bytes": encoded_len})

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": ctx.started_at.isoformat(),
            "device_id": ctx.device_id,
            "export_id": ctx.salt[:16],
            "redaction_level": "standard",
            "options": ctx.options.as_manifest(),
            "versions": versions or {},
            "uncompressed_bytes": total,
            "collectors": [o.as_manifest() for o in outcomes],
            "files": written,
            "truncations": truncations,
            "secret_tripwire": {
                "checked": tripwire.names,
                "blocked": leaks,
            },
        }
        archive.writestr(
            "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        archive.writestr("README.txt", readme_text(ctx, manifest))

    return buffer.getvalue(), manifest


class SecretLeakUnresolved(RuntimeError):
    """A secret survived literal removal - the export is aborted."""

    def __init__(self, path: str, names: list[str]) -> None:
        super().__init__(f"Geheimnis in {path} nicht entfernbar: {', '.join(names)}")
        self.path = path
        self.names = names


def readme_text(ctx: ExportContext, manifest: dict[str, Any]) -> str:
    """The privacy notice, in the archive itself - readable weeks later."""
    created = ctx.started_at.strftime("%d.%m.%Y %H:%M UTC")
    options = ctx.options
    included = [
        "- Technischer Zustand der Box (immer enthalten)",
    ]
    if options.logs:
        included.append("- Fehlerprotokolle der letzten Stunden")
    if options.settings:
        included.append("- Deine Einstellungen")
    if options.network:
        included.append("- Netzwerk-Zustand")
    if options.media == MEDIA_COUNTS:
        included.append("- Übersicht deiner Medien (nur Anzahl, keine Dateinamen)")
    elif options.media == MEDIA_FILENAMES:
        included.append("- Übersicht deiner Medien inklusive Dateinamen")
    if options.history:
        included.append("- Abspielverlauf und Karten-Nutzung")
    if options.client:
        included.append("- Infos zu deinem Browser und Fehlermeldungen der Oberfläche")
    if options.include_db:
        included.append("- Komplette Datenbank")

    return f"""Minabox Diagnose-Paket
======================

Erstellt am: {created}
Gerät: {ctx.device_id}

WAS IST DAS HIER?
-----------------
Dieses Paket hilft dem Entwickler, einen Fehler an deiner Minabox zu finden.
Es wurde auf deinem Gerät erstellt und nirgendwo automatisch hochgeladen.
Niemand bekommt es zu sehen, solange du es nicht selbst verschickst.

WAS IST ENTHALTEN?
------------------
{chr(10).join(included)}

WAS WURDE AUTOMATISCH ENTFERNT?
-------------------------------
Passwörter, Passwort-Merkmale, WLAN-Kennwörter und Zugangsschlüssel.
Der WLAN-Name, Geräte-Seriennummern und Kartennummern wurden durch
unlesbare Zeichenfolgen ersetzt.

WAS IST NIE ENTHALTEN?
----------------------
Deine Musik- und Audiodateien, Cover-Bilder und dein Passwort für die
Weboberfläche.

KANN ICH DAS SELBST ANSEHEN?
----------------------------
Ja. Das ist eine normale ZIP-Datei, alle Inhalte sind Text. Die Datei
manifest.json listet auf, was gesammelt wurde und was dabei fehlgeschlagen
ist. Wenn dir etwas darin nicht gefällt, verschick das Paket nicht.

WAS PASSIERT DAMIT?
-------------------
Der Entwickler nutzt es ausschließlich zur Fehlersuche und löscht es,
sobald dein Problem geklärt ist.

Schema-Version: {manifest['schema_version']}
"""
