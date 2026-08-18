"""REST API endpoints for audio tracks."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
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

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"
AUDIO_STORAGE_PATH = Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))

MEDIA_DOWNLOADER_URL = os.environ.get("MEDIA_DOWNLOADER_URL", "http://media-downloader:8007")

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


def _extract_cover_art(file_path: Path, track_id: int) -> str | None:
    """Extract embedded cover art from audio file; save to COVERS_DIR and return URL path."""
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
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        cover_path = COVERS_DIR / f"track_{track_id}{ext}"
        cover_path.write_bytes(data)
        logger.info("track_cover_extracted", track_id=track_id, path=str(cover_path))
        return f"/static/covers/track_{track_id}{ext}"
    except Exception as e:
        logger.warning("track_cover_extract_failed", track_id=track_id, error=str(e))
        return None


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


async def _run_download_task(
    track_id: int,
    clean_url: str,
    track_dir: Path,
    db_url: str,
    title_override: str | None = None,
    artist_override: str | None = None,
    album_override: str | None = None,
) -> None:
    """Background task: download audio, update track in DB, resolve cover art.

    title_override/artist_override/album_override let the caller (WebUI's
    "edit before import" dialog) pin metadata the user typed in; yt-dlp's
    extracted values are only used as a fallback for fields left blank.
    """
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
    title: str | None = Query(None, description="User-supplied title override (takes precedence over yt-dlp metadata)"),
    artist: str | None = Query(None, description="User-supplied artist override"),
    album: str | None = Query(None, description="User-supplied album override"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Start an async background download for *url*.

    Returns HTTP 202 immediately with the created track ID so the client can
    poll ``GET /tracks/{id}/download-status`` for progress. title/artist/album
    let the caller pin metadata edited in the "check" preview before import;
    yt-dlp's extracted values only fill in fields left blank.
    """
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

    _download_status[track_id] = {"status": "pending", "error": None}

    db_url = str(db.bind.url)  # type: ignore[union-attr]

    asyncio.create_task(
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

    logger.info("api_create_track_from_url_accepted", track_id=track_id, url=clean_url)
    return JSONResponse(
        status_code=202,
        content={"track_id": track_id, "status": "pending"},
    )


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
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {folder_id} not found", "details": {"folder_id": folder_id}}},
            )
    try:
        track = Track(title=title, artist=artist, album=album, source_type="file", source_uri="", folder_id=folder_id)
        db.add(track)
        db.commit()
        db.refresh(track)

        track_dir = Path(config.audio_storage_path) / str(track.id)
        track_dir.mkdir(parents=True, exist_ok=True)

        file_ext = Path(file.filename).suffix if file.filename else ".mp3"
        file_path = track_dir / f"original{file_ext}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            audio_file = MutagenFile(str(file_path))
            if audio_file and audio_file.info:
                track.duration_ms = int(audio_file.info.length * 1000)
                if audio_file.tags:
                    if not artist and "TPE1" in audio_file.tags:
                        track.artist = str(audio_file.tags["TPE1"])
                    if not album and "TALB" in audio_file.tags:
                        track.album = str(audio_file.tags["TALB"])
        except Exception as e:
            logger.warning("api_upload_track_metadata_extraction_failed", track_id=track.id, error=str(e))

        cover_url = _extract_cover_art(file_path, track.id)
        if cover_url:
            track.cover_art_url = cover_url

        track.source_uri = str(file_path)
        db.commit()
        db.refresh(track)
        logger.info("api_upload_track_completed", track_id=track.id, title=track.title)
        return track

    except OSError as e:
        logger.error("api_upload_track_failed", error=str(e))
        db.rollback()
        if e.errno == 13:
            raise HTTPException(status_code=503, detail={"error": {"code": "AUDIO_STORAGE_READONLY", "message": "Audio storage path is not writable.", "details": {"path": config.audio_storage_path, "filename": file.filename}}}) from e
        raise HTTPException(status_code=400, detail={"error": {"code": "UPLOAD_FAILED", "message": f"Failed to upload track: {str(e)}", "details": {"filename": file.filename}}}) from e
    except Exception as e:
        logger.error("api_upload_track_failed", error=str(e))
        db.rollback()
        raise HTTPException(status_code=400, detail={"error": {"code": "UPLOAD_FAILED", "message": f"Failed to upload track: {str(e)}", "details": {"filename": file.filename}}}) from e


@router.post("/{track_id}/cover", response_model=TrackResponse)
async def upload_track_cover(track_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> TrackResponse:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found", "details": {"track_id": track_id}}})
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVERS_DIR / f"track_{track_id}.jpg"
    content = await file.read()
    cover_path.write_bytes(content)
    track.cover_art_url = f"/static/covers/track_{track_id}.jpg"
    db.commit()
    db.refresh(track)
    logger.info("track_cover_uploaded", track_id=track_id)
    return TrackResponse.model_validate(track)


@router.put("/{track_id}", response_model=TrackResponse)
async def update_track(track_id: int, track_data: TrackUpdate, db: Session = Depends(get_db)) -> TrackResponse:
    logger.info("api_update_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found", "details": {"track_id": track_id}}})
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
                raise HTTPException(
                    status_code=404,
                    detail={"error": {"code": "FOLDER_NOT_FOUND", "message": f"Folder {track_data.folder_id} not found", "details": {"folder_id": track_data.folder_id}}},
                )
        track.folder_id = track_data.folder_id
    db.commit()
    db.refresh(track)
    return TrackResponse.model_validate(track)


@router.delete("/{track_id}/cover", response_model=TrackResponse)
async def delete_track_cover(track_id: int, db: Session = Depends(get_db)) -> TrackResponse:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found", "details": {"track_id": track_id}}})
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
async def delete_track(track_id: int, db: Session = Depends(get_db)) -> None:
    logger.info("api_delete_track", track_id=track_id)
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail={"error": {"code": "TRACK_NOT_FOUND", "message": f"Track {track_id} not found", "details": {"track_id": track_id}}})

    if track.source_type == "file":
        try:
            track_dir = Path(track.source_uri).parent
            if track_dir.exists():
                shutil.rmtree(track_dir)
        except Exception as e:
            logger.error("api_delete_track_file_removal_failed", track_id=track_id, error=str(e))

    # Clean up cover art
    for ext in (".jpg", ".png"):
        p = COVERS_DIR / f"track_{track_id}{ext}"
        if p.exists():
            p.unlink()

    db.delete(track)
    db.commit()
    logger.info("api_delete_track_completed", track_id=track_id)
