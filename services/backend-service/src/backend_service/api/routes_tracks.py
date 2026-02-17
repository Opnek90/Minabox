"""REST API endpoints for audio tracks."""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from backend_service.config import get_config
from backend_service.core.db_manager import get_db
from backend_service.models.database import Track
from backend_service.models.schemas import TrackCreate, TrackResponse

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[TrackResponse])
async def list_tracks(db: Session = Depends(get_db)) -> list[TrackResponse]:
    """List all tracks.

    Returns:
        List of all tracks
    """
    logger.info("api_list_tracks")
    tracks: list[Track] = db.query(Track).all()
    return [TrackResponse.model_validate(t) for t in tracks]


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: int, db: Session = Depends(get_db)) -> TrackResponse:
    """Get track by ID.

    Args:
        track_id: Track ID

    Returns:
        Track details

    Raises:
        HTTPException: 404 if track not found
    """
    logger.info("api_get_track", track_id=track_id)

    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TRACK_NOT_FOUND",
                    "message": f"Track {track_id} not found",
                    "details": {"track_id": track_id},
                }
            },
        )

    return TrackResponse.model_validate(track)


@router.post("", response_model=TrackResponse, status_code=201)
async def create_track(
    track_data: TrackCreate,
    db: Session = Depends(get_db),
) -> TrackResponse:
    """Create new track (stream or manual file entry).

    Args:
        track_data: Track data

    Returns:
        Created track
    """
    logger.info(
        "api_create_track", title=track_data.title, source_type=track_data.source_type
    )

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
    return track


@router.post("/upload", response_model=TrackResponse, status_code=201)
async def upload_track(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(None),
    album: str = Form(None),
    db: Session = Depends(get_db),
) -> TrackResponse:
    """Upload audio file and create track.

    Args:
        file: Audio file (multipart upload)
        title: Track title
        artist: Artist name (optional)
        album: Album name (optional)

    Returns:
        Created track with metadata

    Raises:
        HTTPException: 400 if upload fails
    """
    logger.info("api_upload_track_started", filename=file.filename, title=title)

    config = get_config()

    try:
        # Create track entry (without source_uri yet)
        track = Track(
            title=title,
            artist=artist,
            album=album,
            source_type="file",
            source_uri="",  # Placeholder
        )
        db.add(track)
        db.commit()
        db.refresh(track)

        # Create track directory
        track_dir = Path(config.audio_storage_path) / str(track.id)
        track_dir.mkdir(parents=True, exist_ok=True)

        # Get file extension
        file_ext = Path(file.filename).suffix if file.filename else ".mp3"
        file_path = track_dir / f"original{file_ext}"

        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(
            "api_upload_track_file_saved",
            track_id=track.id,
            path=str(file_path),
        )

        # Extract metadata
        try:
            audio_file = MutagenFile(str(file_path))
            if audio_file and audio_file.info:
                track.duration_ms = int(audio_file.info.length * 1000)

                # Extract ID3 tags if not provided
                if audio_file.tags:
                    if not artist and "TPE1" in audio_file.tags:
                        track.artist = str(audio_file.tags["TPE1"])
                    if not album and "TALB" in audio_file.tags:
                        track.album = str(audio_file.tags["TALB"])

                logger.info(
                    "api_upload_track_metadata_extracted",
                    track_id=track.id,
                    duration_ms=track.duration_ms,
                )
        except Exception as e:
            logger.warning(
                "api_upload_track_metadata_extraction_failed",
                track_id=track.id,
                error=str(e),
            )

        # Update track with source_uri
        track.source_uri = str(file_path)
        db.commit()
        db.refresh(track)

        logger.info("api_upload_track_completed", track_id=track.id, title=track.title)
        return track

    except Exception as e:
        logger.error("api_upload_track_failed", error=str(e))
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "UPLOAD_FAILED",
                    "message": f"Failed to upload track: {str(e)}",
                    "details": {"filename": file.filename},
                }
            },
        ) from e


@router.delete("/{track_id}", status_code=204)
async def delete_track(track_id: int, db: Session = Depends(get_db)) -> None:
    """Delete track (and file if source_type=file).

    Args:
        track_id: Track ID

    Raises:
        HTTPException: 404 if track not found
    """
    logger.info("api_delete_track", track_id=track_id)

    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TRACK_NOT_FOUND",
                    "message": f"Track {track_id} not found",
                    "details": {"track_id": track_id},
                }
            },
        )

    # Delete file if source_type=file
    if track.source_type == "file":
        try:
            track_dir = Path(track.source_uri).parent
            if track_dir.exists():
                shutil.rmtree(track_dir)
                logger.info(
                    "api_delete_track_files_removed",
                    track_id=track_id,
                    path=str(track_dir),
                )
        except Exception as e:
            logger.error(
                "api_delete_track_file_removal_failed",
                track_id=track_id,
                error=str(e),
            )

    db.delete(track)
    db.commit()

    logger.info("api_delete_track_completed", track_id=track_id)
