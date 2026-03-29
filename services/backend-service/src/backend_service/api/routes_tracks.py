"""REST API endpoints for audio tracks."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.infrastructure.media_downloader_client import (
    MediaDownloaderClient,
    MediaDownloaderError,
)
from backend_service.models.database import Track, TrackFolder
from backend_service.models.schemas import TrackCreate, TrackResponse, TrackUpdate

AUDIO_STORAGE_PATH = Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))

MEDIA_DOWNLOADER_URL = os.environ.get("MEDIA_DOWNLOADER_URL", "http://media-downloader:8007")

# Domains that are allowed to be used with the from-url import.
_ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "music.youtube.com",
    "m.youtube.com",
    "soundcloud.com",
    "www.soundcloud.com",
    "bandcamp.com",
    "vimeo.com",
    "www.vimeo.com",
})

_PLAYLIST_PARAMS = {"list", "start_radio", "index", "t"}

# In-memory download status store: track_id -> status dict
# Status values: "pending" | "downloading" | "done" | "error"
_download_status: dict[int, dict] = {}

logger = structlog.get_logger(__name__)
router = APIRouter()


def _check_allowed_domain(url: str) -> None:
    """Raise HTTP 400 if the URL's hostname is not on the allow-list."""
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        hostname = ""
    if hostname not in _ALLOWED_DOMAINS:
        logger.warning("api_domain_not_allowed", hostname=hostname, url=url)
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "DOMAIN_NOT_ALLOWED",
                    "message": f"Domain '{hostname}' is not supported. Allowed: {', '.join(sorted(_ALLOWED_DOMAINS))}",
                    "details": {"hostname": hostname},
                }
            },
        )


def _strip_playlist_params(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k not in _PLAYLIST_PARAMS}
    clean = parsed._replace(query=urlencode(filtered, doseq=True))
    return urlunparse(clean)


def _cover_path_for_track(track_id: int, ext: str = ".jpg") -> Path:
    """Return the canonical cover art path inside the track's own folder."""
    return AUDIO_STORAGE_PATH / str(track_id) / f"cover{ext}"


def _find_existing_cover(track_id: int) -> Path | None:
    """Return the first existing cover file for *track_id*, or None."""
    for ext in (".jpg", ".png"):
        p = _cover_path_for_track(track_id, ext)
        if p.exists():
            return p
    return None


def _extract_cover_art(file_path: Path, track_id: int) -> str | None:
    """Extract embedded cover art from MP3 and save to the track folder.

    yt-dlp's EmbedThumbnail postprocessor reliably embeds cover art, so
    this function reads the APIC tag from the finished MP3 and writes it
    as ``cover.jpg`` / ``cover.png`` into the track directory so the
    WebUI can serve it via ``GET /api/tracks/{id}/cover``.

    Returns the API URL path ``/api/tracks/{id}/cover``, or None on failure.
    """
    try:
        audio = MutagenFile(str(file_path))
        if not audio:
            return None
        data: bytes | None = None
        ext = ".jpg"
        if hasattr(audio, "tags") and audio.tags:
            apics = getattr(audio.tags, "getall", lambda _: [])("APIC")
            if not apics:
                for key in getattr(audio.tags, "keys", lambda: [])():
                    if key and str(key).startswith("APIC"):
                        apics = [audio.tags[key]]
                        break
            if apics:
                frame = apics[0]
                data = getattr(frame, "data", None)
                if hasattr(frame, "mime") and frame.mime and "png" in (frame.mime or "").lower():
                    ext = ".png"
        if data is None and hasattr(audio, "pictures") and audio.pictures:
            pic = audio.pictures[0]
            data = getattr(pic, "data", None)
            if getattr(pic, "mime", "") and "png" in (pic.mime or "").lower():
                ext = ".png"
        if not data or len(data) == 0:
            return None
        cover_path = _cover_path_for_track(track_id, ext)
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cover_path.write_bytes(data)
        logger.info("track_cover_extracted", track_id=track_id, path=str(cover_path))
        return f"/api/tracks/{track_id}/cover"
    except Exception as e:
        logger.warning("track_cover_extract_failed", track_id=track_id, error=str(e))
        return None


async def _run_download_task(
    track_id: int,
    clean_url: str,
    track_dir: Path,
    db_url: str,
) -> None:
    """Background task: download audio, update track in DB, extract cover art."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)

    _download_status[track_id] = {"status": "downloading", "error": None}
    client = MediaDownloaderClient(base_url=MEDIA_DOWNLOADER_URL)
    db = SessionLocal()
    try:
        result = await client.download_video(clean_url, output_dir=str(track_dir))

        mp3_path = Path(result["file_path"])
        track = db.query(Track).filter(Track.id == track_id).first()
        if track is None:
            logger.error("download_task_track_missing", track_id=track_id)
            _download_status[track_id] = {"status": "error", "error": "Track record not found"}
            return

        track.title = result["title"]
        track.artist = result.get("artist")
        track.album = result.get("album", "Downloads")
        track.duration_ms = result.get("duration_ms")
        track.source_uri = str(mp3_path)
        db.commit()
        db.refresh(track)

        # Extract cover art embedded by yt-dlp into the MP3
        cover_url = _extract_cover_art(mp3_path, track_id)
        if cover_url:
            track.cover_art_url = cover_url
            db.commit()

        logger.info("download_task_completed", track_id=track_id, title=track.title)
        _download_status[track_id] = {"status": "done", "error": None}

    except MediaDownloaderError as exc:
        logger.error("download_task_failed", track_id=track_id, error=str(exc))
        _download_status[track_id] = {"status": "error", "error": str(exc)}
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
        _download_status[track_id] = {"status": "error", "error": "Unexpected error during download"}
    finally:
        db.close()


@router.get("", response_model=list[TrackResponse])
async def list_tracks(
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
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
            )
        query = query.filter(Track.folder_id == folder_id)
    return [TrackResponse.model_validate(t) for t in query.all()]


@router.get("/validate-url", response_model=dict)
async def validate_media_url(
    url: str = Query(..., description="Video URL to preview (no download)"),
) -> dict:
    """Proxy to media-downloader GET /info – used for frontend preview."""
    clean_url = _strip_playlist_params(url)
    _check_allowed_domain(clean_url)
    if clean_url != url:
        logger.info("api_validate_media_url_playlist_stripped", original=url, clean=clean_url)
    logger.info("api_validate_media_url", url=clean_url)
    client = MediaDownloaderClient(base_url=MEDIA_DOWNLOADER_URL)
    try:
        info = await client.get_video_info(clean_url)
    except MediaDownloaderError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "MEDIA_URL_INVALID", "message": str(exc), "details": {"url": clean_url}}},
        ) from exc
    return {
        "valid": True,
        "title": info.get("title", ""),
        "artist": info.get("artist"),
        "duration_ms": info.get("duration_ms"),
        "thumbnail_url": info.get("thumbnail"),
        "video_id": info.get("video_id", ""),
    }


@router.get("/{track_id}/cover")
async def get_track_cover(track_id: int) -> FileResponse:
    """Stream the cover art image for *track_id* directly from its track folder.

    Looks for ``cover.jpg`` first, then ``cover.png``.
    Returns HTTP 404 if no cover file is present.
    """
    cover = _find_existing_cover(track_id)
    if cover is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "COVER_NOT_FOUND", "message": f"No cover art for track {track_id}"}},
        )
    media_type = "image/png" if cover.suffix == ".png" else "image/jpeg"
    return FileResponse(path=str(cover), media_type=media_type)


@router.get("/{track_id}/download-status", response_model=dict)
async def get_download_status(track_id: int, db: Session = Depends(get_db)) -> dict:
    """Return the async download status for a track imported via POST /from-url."""
    status_entry = _download_status.get(track_id)
    if status_entry is None:
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found"}},
            )
        return {"track_id": track_id, "status": "unknown", "error": None}
    return {"track_id": track_id, **status_entry}


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: int, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_get_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found", "details": {"track_id": track_id}}})
    return TrackResponse.model_validate(track)


@router.post("", response_model=TrackResponse, status_code=201)
async def create_track(track_data: TrackCreate, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_create_track", title=track_data.title, source_type=track_data.source_type)
    if track_data.folder_id is not None:
        folder = db.query(TrackFolder).filter(TrackFolder.id == track_data.folder_id).first()
        if not folder:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {track_data.folder_id} not found", "details": {"folder_id": track_data.folder_id}}},
            )
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
    url: str = Query(..., description="Video URL to download as audio track"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Start an async background download for *url*.

    Returns HTTP 202 immediately with the created track ID so the client can
    poll ``GET /tracks/{id}/download-status`` for progress.
    """
    clean_url = _strip_playlist_params(url)
    _check_allowed_domain(clean_url)
    if clean_url != url:
        logger.info("api_create_track_from_url_playlist_stripped", original=url, clean=clean_url)
    logger.info("api_create_track_from_url", url=clean_url)

    existing = (
        db.query(Track)
        .filter(Track.source_uri.isnot(None))
        .filter(Track.source_uri == clean_url)
        .first()
    )
    if existing is not None:
        logger.info("api_create_track_from_url_duplicate", track_id=existing.id, url=clean_url)
        return JSONResponse(
            status_code=200,
            content={"track_id": existing.id, "status": "done"},
        )

    track = Track(
        title="...",
        source_type="file",
        source_uri=clean_url,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id = track.id

    track_dir = AUDIO_STORAGE_PATH / str(track_id)
    track_dir.mkdir(parents=True, exist_ok=True)

    _download_status[track_id] = {"status": "pending", "error": None}

    db_url = str(db.bind.url)  # type: ignore[union-attr]

    asyncio.create_task(
        _run_download_task(
            track_id=track_id,
            clean_url=clean_url,
            track_dir=track_dir,
            db_url=db_url,
        )
    )

    logger.info("api_create_track_from_url_accepted", track_id=track_id, url=clean_url)
    return JSONResponse(
        status_code=202,
        content={"track_id": track_id, "status": "pending"},
    )
