"""REST API endpoints for audio tracks."""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.api_errors import ApiError
from backend_service.core.capabilities import require_feature
from backend_service.core.db_manager import get_db
from backend_service.core.media_settings import is_domain_allowed, read_allowed_domains
from backend_service.core.online_metadata import lookup as online_lookup
from backend_service.core.online_metadata import online_lookup_enabled
from backend_service.core.track_metadata import (
    extract_embedded_cover,
    read_tags,
    save_track_cover,
)
from backend_service.core.uploads import (
    copy_upload_limited,
    max_audio_upload_bytes,
    read_image_upload,
)
from backend_service.infrastructure.media_downloader_client import (
    MediaDownloaderClient,
    MediaDownloaderError,
)
from backend_service.models.database import Track, TrackFolder
from backend_service.models.schemas import TrackCreate, TrackResponse, TrackUpdate

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"
AUDIO_STORAGE_PATH = Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))

MEDIA_DOWNLOADER_URL = os.environ.get("MEDIA_DOWNLOADER_URL", "http://media-downloader:8007")

_PLAYLIST_PARAMS = {"list", "start_radio", "index", "t"}

# In-memory download status store: track_id -> status dict
# Status values: "pending" | "downloading" | "done" | "error"
#
# Bounded: nothing ever removed an entry, so a box running for months kept
# every import it had ever done. Finished entries are the ones worth dropping -
# a client polls only until it sees a terminal state.
_MAX_DOWNLOAD_STATUS_ENTRIES = 50
_download_status: dict[int, dict] = {}

# Background tasks are held until they finish. Without a reference the event
# loop keeps only a weak one, and an import can be garbage collected mid-flight
# (documented asyncio behaviour).
_background_tasks: set[asyncio.Task] = set()

logger = structlog.get_logger(__name__)
router = APIRouter()


def _check_allowed_domain(url: str) -> None:
    """Raise HTTP 400 if the URL's hostname is not on the allow-list.

    The list is user-configurable (Admin UI -> General -> media import) and
    read fresh on every call - see core/media_settings.py.
    """
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        hostname = ""
    allowed_domains = read_allowed_domains()
    if not is_domain_allowed(hostname, allowed_domains):
        logger.warning("api_domain_not_allowed", hostname=hostname, url=url)
        raise ApiError(status_code=400, code="domain_not_allowed", detail=f"Domain '{hostname}' is not supported. Allowed: {', '.join(sorted(allowed_domains))}")


def _strip_playlist_params(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k not in _PLAYLIST_PARAMS}
    clean = parsed._replace(query=urlencode(filtered, doseq=True))
    return urlunparse(clean)


def _extract_cover_art(file_path: Path, track_id: int) -> str | None:
    """Save embedded cover art for *track_id* and return its ``/static`` URL.

    Thin wrapper around ``core.track_metadata`` kept for the callers that only
    want "embedded cover, if any" (the upload path and the URL import).
    """
    cover = extract_embedded_cover(file_path)
    if cover is None:
        return None
    return save_track_cover(track_id, *cover)


def _set_download_status(
    track_id: int, status: str, error: str | None = None, stage: str | None = None
) -> None:
    """Record an import's state, dropping the oldest finished ones.

    *stage* is one of media-downloader-service's STAGE_* names, or "saving"
    for the part that happens here in the backend after it returns - a coarse
    "what is it doing right now" for the WebUI's progress display, distinct
    from *status* (pending/downloading/done/error), which is what everything
    else in this module already keys off.
    """
    _download_status[track_id] = {"status": status, "error": error, "stage": stage}
    if len(_download_status) > _MAX_DOWNLOAD_STATUS_ENTRIES:
        for done_id, entry in list(_download_status.items()):
            if len(_download_status) <= _MAX_DOWNLOAD_STATUS_ENTRIES:
                break
            if entry.get("status") in ("done", "error") and done_id != track_id:
                del _download_status[done_id]


def _update_download_stage(track_id: int, progress: dict) -> None:
    """Update only the stage/percent/speed/eta of an in-progress download.

    *progress* is media-downloader-service's GET /download/progress/{job_id}
    body (or MediaDownloaderClient.get_progress()'s "unknown"-stage fallback
    on a network hiccup - never raises, so this always has something to
    read). Called from the progress-polling loop every ~1 second - must not
    disturb `status`/`error`, and must be a no-op once the entry has moved to
    a terminal state (the poll loop's last tick can race the task's own
    final `_set_download_status` call).
    """
    entry = _download_status.get(track_id)
    if entry is None or entry.get("status") != "downloading":
        return
    entry["stage"] = progress.get("stage")
    entry["percent"] = progress.get("percent")
    entry["speed_bytes_per_sec"] = progress.get("speed_bytes_per_sec")
    entry["eta_seconds"] = progress.get("eta_seconds")


def _stored_track_dir(track: Track) -> Path | None:
    """Directory holding this track's audio file, or None when there is none.

    Only a path that really lies below the configured audio storage counts.
    `source_uri` is not always a stored file: a URL import keeps the source URL
    there until the download finishes, and an upload that failed after the row
    was written leaves the field empty. An empty value resolved to `Path(".")`,
    whose parent is `"."` again - so deleting such a track removed the working
    directory of the running service.
    """
    raw = (track.source_uri or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        return None

    base = Path(get_config().audio_storage_path).resolve()
    directory = path.parent.resolve()
    if directory == base:
        # A file directly in the storage root has no directory of its own that
        # may be removed.
        return None
    try:
        directory.relative_to(base)
    except ValueError:
        return None
    return directory


def _store_uploaded_track(
    upload_stream: Any,
    track_dir: Path,
    file_path: Path,
    track_id: int,
    limit_bytes: int,
) -> tuple[Path, dict[str, Any]]:
    """Write the upload to disk and read its metadata.

    Blocking (disk write + tag parsing) - call via asyncio.to_thread. Returns
    the final path and the metadata the caller should apply to the DB row.
    Raises `ApiError` 413 once the upload exceeds `limit_bytes`; the partial
    file is removed before that error propagates.
    """
    track_dir.mkdir(parents=True, exist_ok=True)
    copy_upload_limited(upload_stream, file_path, limit_bytes)

    tags = read_tags(file_path)
    metadata: dict[str, Any] = {
        "duration_ms": tags.duration_ms,
        "artist": tags.artist,
        "album": tags.album,
        "cover_url": _extract_cover_art(file_path, track_id),
    }
    return file_path, metadata


async def _download_thumbnail(thumbnail_url: str, track_id: int) -> str | None:
    """Download a remote thumbnail and save it to COVERS_DIR.

    Returns the local /static/covers/... URL path, or None on failure.
    This is used as fallback when no embedded cover art is found in the audio file.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(thumbnail_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            ext = ".png" if "png" in content_type else ".jpg"
            COVERS_DIR.mkdir(parents=True, exist_ok=True)
            cover_path = COVERS_DIR / f"track_{track_id}{ext}"
            cover_path.write_bytes(response.content)
            logger.info("track_thumbnail_downloaded", track_id=track_id, url=thumbnail_url)
            return f"/static/covers/track_{track_id}{ext}"
    except Exception as e:
        logger.warning("track_thumbnail_download_failed", track_id=track_id, url=thumbnail_url, error=str(e))
        return None


# --- Metadata enrichment (embedded tags + optional online lookup) -----------
#
# Two entry points share the helpers below: a fire-and-forget task after an
# upload (online part only - the embedded tags were already read while the file
# was written), and the "backfill" maintenance action that walks every stored
# file track whose artist/album/cover is still empty.

_backfill_status: dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "updated": 0,
    "online_used": 0,
    "finished_at": None,
    "error": None,
}


def _resolve_track_file(track: Track) -> Path | None:
    """The stored audio file of a track, or None when it is not a local file.

    Only a path that really sits below the configured audio storage counts -
    ``source_uri`` is a remote URL for a not-yet-downloaded import, and reading
    an arbitrary path off disk as an "audio file" is not something a metadata
    backfill should ever do.
    """
    raw = (track.source_uri or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        return None
    base = Path(get_config().audio_storage_path).resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(base)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _fill_missing_from_tags(track: Track, file_path: Path) -> bool:
    """Fill empty artist/album/duration/cover from the file's own tags.

    Returns True if the track row was changed.
    """
    changed = False
    tags = read_tags(file_path)
    if not track.artist and tags.artist:
        track.artist = tags.artist
        changed = True
    if not track.album and tags.album:
        track.album = tags.album
        changed = True
    if track.duration_ms is None and tags.duration_ms is not None:
        track.duration_ms = tags.duration_ms
        changed = True
    if not track.cover_art_url:
        cover = extract_embedded_cover(file_path)
        if cover is not None:
            url = save_track_cover(track.id, *cover)
            if url:
                track.cover_art_url = url
                changed = True
    return changed


async def _fill_missing_from_online(track: Track) -> bool:
    """Fill still-empty artist/album/cover via the online lookup.

    Caller must have checked ``online_lookup_enabled()``. Returns True if the
    track row was changed.
    """
    if track.artist and track.album and track.cover_art_url:
        return False
    meta = await online_lookup(track.title, track.artist)
    if meta is None:
        return False
    changed = False
    if not track.artist and meta.artist:
        track.artist = meta.artist
        changed = True
    if not track.album and meta.album:
        track.album = meta.album
        changed = True
    if not track.cover_art_url and meta.cover is not None:
        url = save_track_cover(track.id, *meta.cover)
        if url:
            track.cover_art_url = url
            changed = True
    return changed


def _session_and_engine(db_url: str) -> tuple[Any, Any]:
    """A session plus its engine, both bound to a fresh connection pool.

    Background tasks outlive the request that started them, so they cannot use
    its session and have to hand back their own pool when done - the same
    pattern as ``_run_download_task``.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    return sessionmaker(bind=engine)(), engine


async def _enrich_track_online(track_id: int, db_url: str) -> None:
    """Background task: ask the online lookup for the fields an upload left empty."""
    db, engine = _session_and_engine(db_url)
    try:
        track = db.query(Track).filter(Track.id == track_id).first()
        if track is None:
            return
        if await _fill_missing_from_online(track):
            db.commit()
            logger.info("track_metadata_online_enriched", track_id=track_id)
    except Exception as exc:  # noqa: BLE001 - best effort, must not crash the loop
        logger.warning("track_metadata_online_enrich_failed", track_id=track_id, error=str(exc))
    finally:
        db.close()
        engine.dispose()


async def _run_backfill_task(db_url: str) -> None:
    """Walk every stored file track with a gap and fill it from tags / online."""
    db, engine = _session_and_engine(db_url)
    online = online_lookup_enabled()
    try:
        tracks = (
            db.query(Track)
            .filter(Track.source_type == "file")
            .filter(
                or_(
                    Track.artist.is_(None),
                    Track.album.is_(None),
                    Track.cover_art_url.is_(None),
                )
            )
            .all()
        )
        _backfill_status.update(total=len(tracks), processed=0, updated=0, online_used=0)
        logger.info("track_metadata_backfill_started", total=len(tracks), online=online)
        for track in tracks:
            try:
                changed = False
                file_path = _resolve_track_file(track)
                if file_path is not None:
                    changed = _fill_missing_from_tags(track, file_path)
                if online and not (track.artist and track.album and track.cover_art_url):
                    if await _fill_missing_from_online(track):
                        changed = True
                        _backfill_status["online_used"] += 1
                if changed:
                    db.commit()
                    _backfill_status["updated"] += 1
                else:
                    db.rollback()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.warning(
                    "track_metadata_backfill_track_failed", track_id=track.id, error=str(exc)
                )
            finally:
                _backfill_status["processed"] += 1
        _backfill_status["finished_at"] = datetime.now(UTC).isoformat()
        logger.info(
            "track_metadata_backfill_finished",
            processed=_backfill_status["processed"],
            updated=_backfill_status["updated"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("track_metadata_backfill_failed", error=str(exc))
        _backfill_status["error"] = "Unexpected error during backfill"
        _backfill_status["finished_at"] = datetime.now(UTC).isoformat()
    finally:
        _backfill_status["running"] = False
        db.close()
        engine.dispose()


async def _run_download_task(
    track_id: int,
    clean_url: str,
    track_dir: Path,
    db_url: str,
    title_override: str | None = None,
    artist_override: str | None = None,
    album_override: str | None = None,
) -> None:
    """Background task: import audio, update track in DB, resolve cover art.

    title_override/artist_override/album_override let the caller (WebUI's
    "edit before import" dialog) pin metadata the user typed in; the
    extracted values are only used as a fallback for fields left blank.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)

    _set_download_status(track_id, "downloading", stage="fetching_info")
    client = MediaDownloaderClient(base_url=MEDIA_DOWNLOADER_URL)
    db = SessionLocal()
    try:
        download_task = asyncio.create_task(
            client.download_video(clean_url, output_dir=str(track_dir), job_id=str(track_id))
        )
        # Poll media-downloader-service's real yt-dlp progress while the
        # request above is in flight - a separate connection, since the
        # download call itself blocks on the single HTTP response until the
        # whole import (download + convert + embed) is done.
        while not download_task.done():
            done, _ = await asyncio.wait({download_task}, timeout=1.2)
            if download_task not in done:
                progress = await client.get_progress(str(track_id))
                _update_download_stage(track_id, progress)
        result = await download_task
        logger.info("download_task_saving", track_id=track_id)
        _set_download_status(track_id, "downloading", stage="saving")

        mp3_path = Path(result["file_path"])
        track = db.query(Track).filter(Track.id == track_id).first()
        if track is None:
            logger.error("download_task_track_missing", track_id=track_id)
            _set_download_status(track_id, "error", "Track record not found")
            return

        track.title = title_override or result["title"]
        track.artist = artist_override or result.get("artist")
        track.album = album_override or result.get("album", "Downloads")
        track.duration_ms = result.get("duration_ms")
        track.source_uri = str(mp3_path)
        db.commit()
        db.refresh(track)

        # Cover art: prefer embedded, fall back to remote thumbnail
        cover_url = _extract_cover_art(mp3_path, track_id)
        if not cover_url:
            thumbnail_url = result.get("thumbnail")
            if thumbnail_url:
                cover_url = await _download_thumbnail(thumbnail_url, track_id)

        if cover_url:
            track.cover_art_url = cover_url
            db.commit()

        logger.info("download_task_completed", track_id=track_id, title=track.title)
        _set_download_status(track_id, "done")

    except MediaDownloaderError as exc:
        logger.error("download_task_failed", track_id=track_id, error=str(exc))
        _set_download_status(track_id, "error", str(exc))
        try:
            track = db.query(Track).filter(Track.id == track_id).first()
            if track:
                db.delete(track)
                db.commit()
        except Exception:  # noqa: BLE001
            pass
        try:
            shutil.rmtree(track_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("download_task_unexpected_error", track_id=track_id, error=str(exc))
        _set_download_status(track_id, "error", "Unexpected error during download")
    finally:
        db.close()
        # The task builds its own engine because it outlives the request that
        # started it, so it also has to hand back that connection pool.
        engine.dispose()


@router.get("", response_model=list[TrackResponse])
def list_tracks(
    folder_id: int | None = Query(None, description="Filter by folder ID. Use 0 for root-level tracks (no folder)."),
    db: Session = Depends(get_db),
) -> list[TrackResponse]:
    """List all tracks, optionally filtered by folder."""
    logger.info("api_list_tracks", folder_id=folder_id)
    query = db.query(Track)
    if folder_id == 0:
        query = query.filter(Track.folder_id.is_(None))
    elif folder_id is not None:
        folder = db.query(TrackFolder).filter(TrackFolder.id == folder_id).first()
        if not folder:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")
        query = query.filter(Track.folder_id == folder_id)
    return [TrackResponse.model_validate(t) for t in query.all()]


@router.get("/validate-url", response_model=dict)
async def validate_media_url(
    url: str = Query(..., description="Media URL to inspect (metadata only, no import)"),
) -> dict:
    """Proxy to media-downloader GET /info – used for the frontend preview.

    Reads publicly available metadata for *url* only; nothing is imported here.
    Whether the caller is entitled to import the source is a legal question the
    service cannot answer – see the lawful-use notice in the WebUI.
    """
    require_feature("media_downloader")
    clean_url = _strip_playlist_params(url)
    _check_allowed_domain(clean_url)
    if clean_url != url:
        logger.info("api_validate_media_url_playlist_stripped", original=url, clean=clean_url)
    logger.info("api_validate_media_url", url=clean_url)
    client = MediaDownloaderClient(base_url=MEDIA_DOWNLOADER_URL)
    try:
        info = await client.get_video_info(clean_url)
    except MediaDownloaderError as exc:
        raise ApiError(status_code=422, code="media_url_invalid", detail=str(exc)) from exc
    return {
        "valid": True,
        "title": info.get("title", ""),
        "artist": info.get("artist"),
        "duration_ms": info.get("duration_ms"),
        "thumbnail_url": info.get("thumbnail"),
        "video_id": info.get("video_id", ""),
    }


@router.get("/{track_id}/download-status", response_model=dict)
def get_download_status(track_id: int, db: Session = Depends(get_db)) -> dict:
    """Return the async download status for a track imported via POST /from-url."""
    status_entry = _download_status.get(track_id)
    if status_entry is None:
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")
        return {"track_id": track_id, "status": "unknown", "error": None}
    return {"track_id": track_id, **status_entry}


@router.post("/metadata/backfill", status_code=202)
async def start_metadata_backfill(db: Session = Depends(get_db)) -> JSONResponse:
    """Fill missing artist/album/cover for existing file tracks in the background.

    Reads each track's own tags first; only if a gap remains and the user has
    enabled ``online_metadata_lookup_enabled`` does it ask MusicBrainz / the
    Cover Art Archive. Poll ``GET /tracks/metadata/backfill`` for progress.
    """
    if _backfill_status["running"]:
        raise ApiError(
            status_code=409,
            code="backfill_already_running",
            detail="A metadata backfill is already running",
        )
    _backfill_status.update(
        running=True, total=0, processed=0, updated=0, online_used=0,
        finished_at=None, error=None,
    )
    db_url = str(db.bind.url)  # type: ignore[union-attr]
    task = asyncio.create_task(_run_backfill_task(db_url))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info("api_track_metadata_backfill_accepted")
    return JSONResponse(status_code=202, content={"status": "started"})


@router.get("/metadata/backfill", response_model=dict)
def get_metadata_backfill_status() -> dict:
    """Progress of the backfill started via POST /tracks/metadata/backfill."""
    return dict(_backfill_status)


@router.get("/{track_id}", response_model=TrackResponse)
def get_track(track_id: int, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_get_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")
    return TrackResponse.model_validate(track)


@router.post("", response_model=TrackResponse, status_code=201)
def create_track(track_data: TrackCreate, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_create_track", title=track_data.title, source_type=track_data.source_type)
    if track_data.folder_id is not None:
        folder = db.query(TrackFolder).filter(TrackFolder.id == track_data.folder_id).first()
        if not folder:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {track_data.folder_id} not found")
    track = Track(
        title=track_data.title,
        artist=track_data.artist,
        album=track_data.album,
        duration_ms=track_data.duration_ms,
        source_type=track_data.source_type.value,
        source_uri=track_data.source_uri,
        folder_id=track_data.folder_id,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    logger.info("api_track_created", track_id=track.id, title=track.title)
    return TrackResponse.model_validate(track)


@router.post("/from-url", status_code=202)
async def create_track_from_url(
    url: str = Query(..., description="Media URL to import as an audio track"),
    title: str | None = Query(None, description="User-supplied title override (takes precedence over extracted metadata)"),
    artist: str | None = Query(None, description="User-supplied artist override"),
    album: str | None = Query(None, description="User-supplied album override"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Start an async background import for *url*.

    Returns HTTP 202 immediately with the created track ID so the client can
    poll ``GET /tracks/{id}/download-status`` for progress. title/artist/album
    let the caller pin metadata edited in the "check" preview before import;
    the extracted values only fill in fields left blank.

    Only hosts on the allow-list are accepted. The allow-list is a technical
    guard against arbitrary fetch targets – it says nothing about whether the
    caller holds the rights to the individual piece of content.
    """
    require_feature("media_downloader")

    title = title.strip() if title and title.strip() else None
    artist = artist.strip() if artist and artist.strip() else None
    album = album.strip() if album and album.strip() else None

    clean_url = _strip_playlist_params(url)
    _check_allowed_domain(clean_url)
    if clean_url != url:
        logger.info("api_create_track_from_url_playlist_stripped", original=url, clean=clean_url)
    logger.info("api_create_track_from_url", url=clean_url, title_override=title)

    existing = (
        db.query(Track)
        .filter(Track.source_uri.isnot(None))
        .filter(Track.source_uri == clean_url)
        .first()
    )
    if existing is not None:
        logger.info("api_create_track_from_url_duplicate", track_id=existing.id, url=clean_url)
        if title or artist or album:
            if title:
                existing.title = title
            if artist:
                existing.artist = artist
            if album:
                existing.album = album
            db.commit()
        return JSONResponse(
            status_code=200,
            content={"track_id": existing.id, "status": "done"},
        )

    track = Track(
        title=title or "...",
        artist=artist,
        album=album,
        source_type="file",
        source_uri=clean_url,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id = track.id

    track_dir = AUDIO_STORAGE_PATH / str(track_id)
    track_dir.mkdir(parents=True, exist_ok=True)

    _set_download_status(track_id, "pending")

    db_url = str(db.bind.url)  # type: ignore[union-attr]

    task = asyncio.create_task(
        _run_download_task(
            track_id=track_id,
            clean_url=clean_url,
            track_dir=track_dir,
            db_url=db_url,
            title_override=title,
            artist_override=artist,
            album_override=album,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info("api_create_track_from_url_accepted", track_id=track_id, url=clean_url)
    return JSONResponse(
        status_code=202,
        content={"track_id": track_id, "status": "pending"},
    )


def _discard_incomplete_track(db: Session, track_id: int) -> None:
    """Remove the placeholder row of an upload that never got its file.

    Such a row carries an empty `source_uri`; leaving it behind shows a track in
    the library that can never play.
    """
    db.rollback()
    try:
        orphan = db.query(Track).filter(Track.id == track_id).first()
        if orphan is not None and not (orphan.source_uri or "").strip():
            db.delete(orphan)
            db.commit()
            logger.info("api_upload_track_placeholder_removed", track_id=track_id)
    except Exception as exc:  # pragma: no cover - cleanup must not mask the cause
        db.rollback()
        logger.warning("api_upload_track_cleanup_failed", track_id=track_id, error=str(exc))


@router.post("/upload", response_model=TrackResponse, status_code=201)
async def upload_track(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(None),
    album: str = Form(None),
    folder_id: int | None = Form(None),
    db: Session = Depends(get_db),
) -> TrackResponse:
    logger.info("api_upload_track_started", filename=file.filename, title=title)
    config = get_config()
    if folder_id is not None:
        folder = db.query(TrackFolder).filter(TrackFolder.id == folder_id).first()
        if not folder:
            raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {folder_id} not found")

    # The row is written first because the directory is named after its id. It
    # therefore exists for a moment with an empty source_uri, and a rollback
    # cannot take it back once committed - hence the explicit cleanup in the
    # error paths below. Without it a half-created track stayed in the library
    # and could not be deleted safely.
    track = Track(title=title, artist=artist, album=album, source_type="file", source_uri="", folder_id=folder_id)
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id = track.id

    try:
        track_dir = Path(config.audio_storage_path) / str(track_id)
        file_ext = Path(file.filename).suffix if file.filename else ".mp3"
        file_path = track_dir / f"original{file_ext}"

        # Writing the upload to the SD card and parsing its tags takes seconds
        # for a large audiobook. On the event loop that freezes every other
        # request including the player WebSocket, so it runs in a thread.
        file_path, metadata = await asyncio.to_thread(
            _store_uploaded_track,
            file.file,
            track_dir,
            file_path,
            track_id,
            max_audio_upload_bytes(),
        )

        if metadata.get("duration_ms") is not None:
            track.duration_ms = metadata["duration_ms"]
        if not artist and metadata.get("artist"):
            track.artist = metadata["artist"]
        if not album and metadata.get("album"):
            track.album = metadata["album"]
        if metadata.get("cover_url"):
            track.cover_art_url = metadata["cover_url"]

        track.source_uri = str(file_path)
        db.commit()
        db.refresh(track)
        logger.info("api_upload_track_completed", track_id=track.id, title=track.title)

        # The file carried no artist/album/cover and the user has opted in to
        # third-party lookups: resolve the rest in the background so the upload
        # response stays quick. The WebUI picks the values up on its next
        # refresh.
        if online_lookup_enabled() and not (
            track.artist and track.album and track.cover_art_url
        ):
            enrich = asyncio.create_task(
                _enrich_track_online(track.id, str(db.bind.url))  # type: ignore[union-attr]
            )
            _background_tasks.add(enrich)
            enrich.add_done_callback(_background_tasks.discard)

        return TrackResponse.model_validate(track)

    except ApiError:
        # Already a shaped error (e.g. the size limit) - only clean up.
        _discard_incomplete_track(db, track_id)
        raise
    except OSError as e:
        logger.error("api_upload_track_failed", error=str(e))
        _discard_incomplete_track(db, track_id)
        if e.errno == 13:
            raise ApiError(status_code=503, code="audio_storage_readonly", detail="Audio storage path is not writable.") from e
        raise ApiError(status_code=400, code="upload_failed", detail=f"Failed to upload track: {str(e)}") from e
    except Exception as e:
        logger.error("api_upload_track_failed", error=str(e))
        _discard_incomplete_track(db, track_id)
        raise ApiError(status_code=400, code="upload_failed", detail=f"Failed to upload track: {str(e)}") from e


@router.post("/{track_id}/cover", response_model=TrackResponse)
async def upload_track_cover(track_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> TrackResponse:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")
    content = await read_image_upload(file)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVERS_DIR / f"track_{track_id}.jpg"
    cover_path.write_bytes(content)
    track.cover_art_url = f"/static/covers/track_{track_id}.jpg"
    db.commit()
    db.refresh(track)
    logger.info("track_cover_uploaded", track_id=track_id)
    return TrackResponse.model_validate(track)


@router.put("/{track_id}", response_model=TrackResponse)
def update_track(track_id: int, track_data: TrackUpdate, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_update_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")
    if track_data.title is not None:
        track.title = track_data.title
    if track_data.artist is not None:
        track.artist = track_data.artist
    if track_data.album is not None:
        track.album = track_data.album
    if track_data.duration_ms is not None:
        track.duration_ms = track_data.duration_ms
    if "folder_id" in track_data.model_fields_set:
        if track_data.folder_id is not None:
            folder = db.query(TrackFolder).filter(TrackFolder.id == track_data.folder_id).first()
            if not folder:
                raise ApiError(status_code=404, code="folder_not_found", detail=f"Folder {track_data.folder_id} not found")
        track.folder_id = track_data.folder_id
    db.commit()
    db.refresh(track)
    return TrackResponse.model_validate(track)


@router.delete("/{track_id}/cover", response_model=TrackResponse)
def delete_track_cover(track_id: int, db: Session = Depends(get_db)) -> TrackResponse:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")
    for ext in (".jpg", ".png"):
        p = COVERS_DIR / f"track_{track_id}{ext}"
        if p.exists():
            p.unlink()
    track.cover_art_url = None
    db.commit()
    db.refresh(track)
    logger.info("track_cover_deleted", track_id=track_id)
    return TrackResponse.model_validate(track)


@router.delete("/{track_id}", status_code=204)
def delete_track(track_id: int, db: Session = Depends(get_db)) -> None:
    logger.info("api_delete_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ApiError(status_code=404, code="track_not_found", detail=f"Track {track_id} not found")

    if track.source_type == "file":
        track_dir = _stored_track_dir(track)
        if track_dir is None:
            logger.info("api_delete_track_no_stored_directory", track_id=track_id)
        else:
            try:
                if track_dir.exists():
                    shutil.rmtree(track_dir)
            except OSError as e:
                logger.error("api_delete_track_file_removal_failed", track_id=track_id, error=str(e))

    # Clean up cover art
    for ext in (".jpg", ".png"):
        p = COVERS_DIR / f"track_{track_id}{ext}"
        if p.exists():
            p.unlink()

    db.delete(track)
    db.commit()
    logger.info("api_delete_track_completed", track_id=track_id)
