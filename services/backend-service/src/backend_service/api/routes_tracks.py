"""REST API endpoints for audio tracks."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.infrastructure.media_downloader_client import (
    MediaDownloaderClient,
    MediaDownloaderError,
)
from backend_service.models.database import Track
from backend_service.models.schemas import TrackCreate, TrackResponse, TrackUpdate

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"
AUDIO_STORAGE_PATH = Path(os.environ.get("AUDIO_STORAGE_PATH", "/mnt/audio/tracks"))

MEDIA_DOWNLOADER_URL = os.environ.get("MEDIA_DOWNLOADER_URL", "http://media-downloader:8007")

_PLAYLIST_PARAMS = {"list", "start_radio", "index", "t"}

logger = structlog.get_logger(__name__)
router = APIRouter()


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
        return f"/static/covers/track_{track_id}{ext}"
    except Exception as e:
        logger.warning("track_cover_extract_failed", track_id=track_id, error=str(e))
        return None


@router.get("", response_model=list[TrackResponse])
async def list_tracks(db: Session = Depends(get_db)) -> list[TrackResponse]:
    logger.info("api_list_tracks")
    return [TrackResponse.model_validate(t) for t in db.query(Track).all()]


@router.get("/validate-url", response_model=dict)
async def validate_media_url(
    url: str = Query(..., description="Video URL to preview (no download)"),
) -> dict:
    """Proxy to media-downloader GET /info – used for frontend preview."""
    clean_url = _strip_playlist_params(url)
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
    track = Track(
        title=track_data.title,
        artist=track_data.artist,
        album=track_data.album,
        duration_ms=track_data.duration_ms,
        source_type=track_data.source_type.value,
        source_uri=track_data.source_uri,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    logger.info("api_track_created", track_id=track.id, title=track.title)
    return TrackResponse.model_validate(track)


@router.post("/from-url", response_model=TrackResponse, status_code=201)
async def create_track_from_url(
    url: str = Query(..., description="Video URL to download as audio track"),
    db: Session = Depends(get_db),
) -> TrackResponse:
    """Create Track in DB first, then download MP3 into tracks/{track_id}/."""
    clean_url = _strip_playlist_params(url)
    if clean_url != url:
        logger.info("api_create_track_from_url_playlist_stripped", original=url, clean=clean_url)
    logger.info("api_create_track_from_url", url=clean_url)

    # 1. Reserve a DB row so we get the track_id before downloading
    track = Track(
        title="...",  # placeholder, updated after download
        source_type="file",
        source_uri="",
    )
    db.add(track)
    db.commit()
    db.refresh(track)

    # 2. Target directory mirrors the upload layout: tracks/{track_id}/
    track_dir = AUDIO_STORAGE_PATH / str(track.id)
    track_dir.mkdir(parents=True, exist_ok=True)

    client = MediaDownloaderClient(base_url=MEDIA_DOWNLOADER_URL)
    try:
        result = await client.download_video(clean_url, output_dir=str(track_dir))
    except MediaDownloaderError as exc:
        # Clean up the placeholder row and directory on failure
        db.delete(track)
        db.commit()
        try:
            shutil.rmtree(track_dir)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "DOWNLOAD_FAILED", "message": str(exc), "details": {"url": clean_url}}},
        ) from exc

    # 3. Update track with real metadata from download result
    mp3_path = Path(result["file_path"])
    track.title = result["title"]
    track.artist = result.get("artist")
    track.album = result.get("album", "Downloads")
    track.duration_ms = result.get("duration_ms")
    track.source_uri = str(mp3_path)
    db.commit()
    db.refresh(track)

    # 4. Extract cover art from embedded thumbnail
    cover_url = _extract_cover_art(mp3_path, track.id)
    if cover_url:
        track.cover_art_url = cover_url
        db.commit()
        db.refresh(track)

    logger.info("api_track_from_url_created", track_id=track.id, title=track.title)
    return TrackResponse.model_validate(track)


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
    db.commit()
    db.refresh(track)
    return TrackResponse.model_validate(track)


@router.post("/upload", response_model=TrackResponse, status_code=201)
async def upload_track(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(None),
    album: str = Form(None),
    db: Session = Depends(get_db),
) -> TrackResponse:
    logger.info("api_upload_track_started", filename=file.filename, title=title)
    config = get_config()
    try:
        track = Track(title=title, artist=artist, album=album, source_type="file", source_uri="")
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

    db.delete(track)
    db.commit()
    logger.info("api_delete_track_completed", track_id=track_id)
