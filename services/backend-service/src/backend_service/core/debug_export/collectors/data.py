"""Collectors for settings, database, media and the browser context.

The privacy tiers from docs/DebugExport.md 4.7 are implemented here: the same
table produces counts by default, filenames only when the user asked for them,
and raw history only in its own block.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from backend_service.core.debug_export.framework import (
    BLOCK_CLIENT,
    BLOCK_DATABASE,
    BLOCK_HISTORY,
    BLOCK_LOGS,
    BLOCK_MEDIA,
    BLOCK_SETTINGS,
    BLOCK_SYSTEM,
    MEDIA_FILENAMES,
    ExportContext,
    register,
)
from backend_service.core.debug_export.redaction import pseudonymize

logger = structlog.get_logger(__name__)

MAX_CLIENT_ENTRIES = 200
MAX_HISTORY_ROWS = 500


def _database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "/data/minabox.db"))


def _open_readonly(path: Path) -> sqlite3.Connection:
    """Open the database read-only - the export must never write to it."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)


@register("settings.general", BLOCK_SETTINGS, timeout=10.0)
def collect_settings(ctx: ExportContext) -> dict[str, Any]:
    """User settings, plus the *shape* of the auth file - never its content."""
    files: dict[str, Any] = {}
    data_path = ctx.data_path

    general = data_path / "general_settings.json"
    if general.exists():
        try:
            files["config/general_settings.json"] = json.loads(
                general.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as e:
            files["config/general_settings.json"] = {"error": str(e)}

    auth = data_path / "auth_settings.json"
    if auth.exists():
        try:
            payload = json.loads(auth.read_text(encoding="utf-8"))
            files["config/auth_settings.shape.json"] = {
                "web_password_hash_gesetzt": bool(payload.get("web_password_hash")),
                "protected_areas": payload.get("protected_areas") or [],
                "hinweis": "Der Hash selbst ist bewusst nicht enthalten.",
            }
        except (OSError, ValueError) as e:
            files["config/auth_settings.shape.json"] = {"error": str(e)}

    services_root = Path(os.environ.get("CONFIG_SERVICES_PATH", "/app/config_services"))
    if services_root.is_dir():
        for service_dir in sorted(services_root.iterdir()):
            if not service_dir.is_dir():
                continue
            for config_file in sorted(service_dir.glob("*.json")):
                try:
                    files[f"config/services/{service_dir.name}/{config_file.name}"] = (
                        json.loads(config_file.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError) as e:
                    files[f"config/services/{service_dir.name}/{config_file.name}"] = {
                        "error": str(e)
                    }
    return files


@register("settings.environment", BLOCK_SETTINGS, timeout=5.0)
def collect_environment(ctx: ExportContext) -> dict[str, Any]:
    """Environment variable *names* and whether they are set. Never the values."""
    interesting = {
        key: ("gesetzt" if value.strip() else "leer")
        for key, value in sorted(os.environ.items())
        if key.isupper() and not key.startswith(("LS_", "LC_"))
    }
    return {
        "config/env.sanitized.json": {
            "hinweis": "Nur Namen und ob ein Wert gesetzt ist - niemals der Wert selbst.",
            "variables": interesting,
        }
    }


@register("db.meta", BLOCK_SYSTEM, timeout=20.0)
def collect_database_meta(ctx: ExportContext) -> dict[str, Any]:
    """Schema, migration state, row counts and integrity - no user content."""
    path = _database_path()
    if not path.exists():
        return {"db/meta.json": {"error": f"Datenbank nicht gefunden: {path}"}}

    files: dict[str, Any] = {}
    try:
        connection = _open_readonly(path)
    except sqlite3.Error as e:
        return {"db/meta.json": {"error": f"{type(e).__name__}: {e}"}}

    try:
        cursor = connection.cursor()
        schema_rows = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
        files["db/schema.sql"] = "\n\n".join(row[0] for row in schema_rows)

        tables = [
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        counts: dict[str, Any] = {}
        for table in tables:
            try:
                counts[table] = cursor.execute(
                    f'SELECT COUNT(*) FROM "{table}"'  # noqa: S608 - name from sqlite_master
                ).fetchone()[0]
            except sqlite3.Error as e:
                counts[table] = f"Fehler: {e}"
        files["db/table_counts.json"] = counts

        try:
            version = cursor.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            files["db/alembic_version.txt"] = version[0] if version else "(leer)"
        except sqlite3.Error:
            files["db/alembic_version.txt"] = "(keine alembic_version-Tabelle)"

        integrity = cursor.execute("PRAGMA quick_check").fetchone()
        files["db/integrity_check.txt"] = (
            str(integrity[0]) if integrity else "unbekannt"
        )

        files["db/meta.json"] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "wal_present": (path.parent / f"{path.name}-wal").exists(),
            "page_size": cursor.execute("PRAGMA page_size").fetchone()[0],
            "journal_mode": cursor.execute("PRAGMA journal_mode").fetchone()[0],
        }
    finally:
        connection.close()
    return files


@register("media.summary", BLOCK_MEDIA, timeout=30.0)
def collect_media(ctx: ExportContext) -> dict[str, Any]:
    """Library summary and - the most common support case - missing files."""
    path = _database_path()
    if not path.exists():
        return {}

    include_names = ctx.options.media == MEDIA_FILENAMES
    files: dict[str, Any] = {}
    try:
        connection = _open_readonly(path)
    except sqlite3.Error as e:
        return {"media/library_summary.json": {"error": f"{type(e).__name__}: {e}"}}

    try:
        cursor = connection.cursor()
        summary: dict[str, Any] = {"include_filenames": include_names}
        for label, table in (
            ("tracks", "tracks"),
            ("playlists", "playlists"),
            ("streams", "streams"),
            ("podcasts", "podcasts"),
            ("podcast_episodes", "podcast_episodes"),
            ("track_folders", "track_folders"),
            ("tags", "tags"),
        ):
            try:
                summary[label] = cursor.execute(
                    f'SELECT COUNT(*) FROM "{table}"'  # noqa: S608
                ).fetchone()[0]
            except sqlite3.Error:
                summary[label] = None

        extensions: Counter[str] = Counter()
        source_types: Counter[str] = Counter()
        missing: list[dict[str, Any]] = []
        checked = 0
        try:
            rows = cursor.execute(
                "SELECT id, title, source_type, source_uri FROM tracks"
            ).fetchall()
        except sqlite3.Error as e:
            rows = []
            summary["tracks_error"] = str(e)

        audio_root = Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))
        for track_id, title, source_type, source_uri in rows:
            source_types[str(source_type)] += 1
            if str(source_type) != "file" or not source_uri:
                continue
            checked += 1
            extensions[Path(str(source_uri)).suffix.lower() or "(ohne)"] += 1
            candidate = Path(str(source_uri))
            if not candidate.is_absolute():
                candidate = audio_root / candidate
            if not candidate.exists():
                entry: dict[str, Any] = {"track_id": track_id}
                if include_names:
                    entry["title"] = title
                    entry["path"] = str(source_uri)
                missing.append(entry)

        summary["file_tracks_checked"] = checked
        summary["extensions"] = dict(extensions)
        summary["source_types"] = dict(source_types)
        files["media/library_summary.json"] = summary
        files["media/missing_files.json"] = {
            "count": len(missing),
            "entries": missing[:200],
            "hinweis": (
                "Einträge, deren Datei auf der Platte fehlt. Der häufigste Grund "
                "für 'ein Titel spielt nicht'."
            ),
        }
    finally:
        connection.close()

    audio_state = Path("/app/state/audio_state.json")
    if audio_state.exists():
        try:
            files["media/audio_state.json"] = json.loads(
                audio_state.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as e:
            files["media/audio_state.json"] = {"error": str(e)}
    return files


@register("history.usage", BLOCK_HISTORY, timeout=20.0)
def collect_history(ctx: ExportContext) -> dict[str, Any]:
    """Scan and playback history. Tag UIDs are hashed; the timeline stays visible.

    This block is off by default: it shows when and how long a child listened.
    """
    path = _database_path()
    if not path.exists():
        return {}
    try:
        connection = _open_readonly(path)
    except sqlite3.Error as e:
        return {"db/recent_scans.json": {"error": f"{type(e).__name__}: {e}"}}

    files: dict[str, Any] = {}
    try:
        cursor = connection.cursor()
        try:
            rows = cursor.execute(
                "SELECT tag_uid, tag_name, media_type, action, scanned_at "
                "FROM tag_scan_events ORDER BY scanned_at DESC LIMIT ?",
                (MAX_HISTORY_ROWS,),
            ).fetchall()
            files["db/recent_scans.json"] = {
                "count": len(rows),
                "entries": [
                    {
                        "tag_pseudonym": pseudonymize(row[0], ctx.salt),
                        "tag_name": (
                            row[1] if ctx.options.media == MEDIA_FILENAMES else None
                        ),
                        "media_type": row[2],
                        "action": row[3],
                        "scanned_at": row[4],
                    }
                    for row in rows
                ],
            }
        except sqlite3.Error as e:
            files["db/recent_scans.json"] = {"error": str(e)}

        try:
            since = (datetime.now(UTC) - timedelta(days=14)).isoformat()
            rows = cursor.execute(
                "SELECT COUNT(*), SUM(COALESCE(duration_ms, 0)) FROM playback_events "
                "WHERE started_at >= ?",
                (since,),
            ).fetchone()
            files["db/playback_summary.json"] = {
                "window_days": 14,
                "events": rows[0] if rows else 0,
                "total_minutes": round((rows[1] or 0) / 60000, 1) if rows else 0,
            }
        except sqlite3.Error as e:
            files["db/playback_summary.json"] = {"error": str(e)}

        try:
            rows = cursor.execute(
                "SELECT recorded_at, temperature_celsius FROM temperature_readings "
                "ORDER BY recorded_at DESC LIMIT 288"
            ).fetchall()
            files["runtime/temperature_recent.json"] = {
                "count": len(rows),
                "readings": [{"at": row[0], "celsius": row[1]} for row in rows],
            }
        except sqlite3.Error:
            pass
    finally:
        connection.close()
    return files


@register("database.copy", BLOCK_DATABASE, timeout=30.0)
def collect_database_copy(ctx: ExportContext) -> dict[str, Any]:
    """The full database. Opt-in, admin-only, and the most personal part."""
    path = _database_path()
    if not path.exists():
        return {}
    try:
        # sqlite3's backup API gives a consistent copy even with WAL active -
        # copying the file underneath a running service would not.
        source = _open_readonly(path)
        target = sqlite3.connect(":memory:")
        try:
            source.backup(target)
            dump = "\n".join(target.iterdump())
        finally:
            source.close()
            target.close()
    except sqlite3.Error as e:
        return {"db/copy_error.json": {"error": f"{type(e).__name__}: {e}"}}
    # Exported as SQL text rather than the binary file: it stays readable, and
    # it still passes through redaction like every other file.
    return {"db/minabox.db.sql": dump}


@register("runtime.buffers", BLOCK_LOGS, timeout=10.0)
def collect_runtime_buffers(ctx: ExportContext) -> dict[str, Any]:
    """The backend's last warnings and the recent MQTT traffic.

    Both are memory-only ring buffers: container logs get rotated away and MQTT
    is never persisted at all. "The button press never reached the backend" is
    only answerable from here.
    """
    from backend_service.core.debug_export.runtime_buffers import (
        log_buffer,
        mqtt_buffer,
    )

    files: dict[str, Any] = {}
    errors = log_buffer.entries()
    files["runtime/errors_recent.json"] = {
        "count": len(errors),
        "hinweis": (
            "Die letzten Warnungen und Fehler des Backends, unabhängig von der "
            "Log-Rotation der Container."
        ),
        "entries": errors,
    }
    messages = mqtt_buffer.entries()
    files["runtime/mqtt_recent.json"] = {
        "count": len(messages),
        "hinweis": (
            "Letzte MQTT-Nachrichten (in = empfangen, out = gesendet). Zeigt, ob "
            "ein Tastendruck oder Kartenscan das Backend überhaupt erreicht hat."
        ),
        "entries": messages,
    }
    return files


@register("client.context", BLOCK_CLIENT, timeout=5.0)
def collect_client(ctx: ExportContext) -> dict[str, Any]:
    """Browser context and the WebUI error ring buffer, sent along by the client.

    Frontend errors appear nowhere else - not in container logs, not in the
    backend. This is the only place they are captured.
    """
    payload = ctx.client_payload or {}
    if not payload:
        return {
            "client/context.json": {
                "hinweis": "Die Oberfläche hat keine Browser-Daten mitgeschickt."
            }
        }

    def _trim(entries: Any) -> list[Any]:
        if not isinstance(entries, list):
            return []
        return entries[-MAX_CLIENT_ENTRIES:]

    files: dict[str, Any] = {
        "client/browser.json": payload.get("browser") or {},
        "client/console_errors.json": {"entries": _trim(payload.get("console_errors"))},
        "client/failed_requests.json": {
            "entries": _trim(payload.get("failed_requests"))
        },
    }
    return files
