"""REST API endpoints for playlists."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Playlist, PlaylistTrack, Track
from backend_service.models.schemas import (
    PlaylistCreate,
    PlaylistDetailResponse,
    PlaylistResponse,
    PlaylistUpdate,
)

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[PlaylistResponse])
def list_playlists(db: Session = Depends(get_db)) -> list[PlaylistResponse]:
    """List all playlists.

    Returns:
        List of all playlists
    """
    logger.info("api_list_playlists")
    playlists: list[Playlist] = db.query(Playlist).all()
    return [PlaylistResponse.model_validate(p) for p in playlists]


@router.get("/{playlist_id}", response_model=PlaylistDetailResponse)
def get_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
) -> PlaylistDetailResponse:
    """Get playlist with tracks.

    Args:
        playlist_id: Playlist ID

    Returns:
        Playlist details with tracks

    Raises:
        HTTPException: 404 if playlist not found
    """
    logger.info("api_get_playlist", playlist_id=playlist_id)

    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PLAYLIST_NOT_FOUND",
                    "message": f"Playlist {playlist_id} not found",
                    "details": {"playlist_id": playlist_id},
                }
            },
        )

    # Load tracks in order
    playlist_tracks = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position)
        .all()
    )

    tracks = [pt.track for pt in playlist_tracks]

    return PlaylistDetailResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
        tracks=tracks,
    )


@router.post("", response_model=PlaylistResponse, status_code=201)
def create_playlist(
    playlist_data: PlaylistCreate,
    db: Session = Depends(get_db),
) -> PlaylistResponse:
    """Create new playlist.

    Args:
        playlist_data: Playlist data

    Returns:
        Created playlist
    """
    logger.info("api_create_playlist", name=playlist_data.name)

    # Create playlist
    playlist = Playlist(
        name=playlist_data.name,
        description=playlist_data.description,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)

    # Add tracks
    for position, track_id in enumerate(playlist_data.track_ids):
        # Verify track exists
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            logger.warning("api_track_not_found_in_playlist_create", track_id=track_id)
            continue

        playlist_track = PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track_id,
            position=position,
        )
        db.add(playlist_track)

    db.commit()
    db.refresh(playlist)

    logger.info("api_playlist_created", playlist_id=playlist.id, name=playlist.name)
    return playlist


@router.put("/{playlist_id}", response_model=PlaylistResponse)
def update_playlist(
    playlist_id: int,
    playlist_data: PlaylistUpdate,
    db: Session = Depends(get_db),
) -> PlaylistResponse:
    """Update existing playlist.

    Args:
        playlist_id: Playlist ID
        playlist_data: Updated playlist data

    Returns:
        Updated playlist

    Raises:
        HTTPException: 404 if playlist not found
    """
    logger.info("api_update_playlist", playlist_id=playlist_id)

    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PLAYLIST_NOT_FOUND",
                    "message": f"Playlist {playlist_id} not found",
                    "details": {"playlist_id": playlist_id},
                }
            },
        )

    # Update fields
    if playlist_data.name is not None:
        playlist.name = playlist_data.name
    if playlist_data.description is not None:
        playlist.description = playlist_data.description

    # Update tracks if provided
    if playlist_data.track_ids is not None:
        # Remove existing tracks
        db.query(PlaylistTrack).filter(
            PlaylistTrack.playlist_id == playlist_id
        ).delete()

        # Add new tracks
        for position, track_id in enumerate(playlist_data.track_ids):
            track = db.query(Track).filter(Track.id == track_id).first()
            if not track:
                logger.warning(
                    "api_track_not_found_in_playlist_update", track_id=track_id
                )
                continue

            playlist_track = PlaylistTrack(
                playlist_id=playlist.id,
                track_id=track_id,
                position=position,
            )
            db.add(playlist_track)

    db.commit()
    db.refresh(playlist)

    logger.info("api_playlist_updated", playlist_id=playlist_id)
    return PlaylistResponse.model_validate(playlist)


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, db: Session = Depends(get_db)) -> None:
    """Delete playlist.

    Args:
        playlist_id: Playlist ID

    Raises:
        HTTPException: 404 if playlist not found
    """
    logger.info("api_delete_playlist", playlist_id=playlist_id)

    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PLAYLIST_NOT_FOUND",
                    "message": f"Playlist {playlist_id} not found",
                    "details": {"playlist_id": playlist_id},
                }
            },
        )

    # Remove cover art if present
    cover_path = COVERS_DIR / f"playlist_{playlist_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()

    db.delete(playlist)
    db.commit()

    logger.info("api_playlist_deleted", playlist_id=playlist_id)


@router.post("/{playlist_id}/cover", response_model=PlaylistResponse)
async def upload_playlist_cover(
    playlist_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PlaylistResponse:
    """Upload cover art for a playlist."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail={"error": {"code": "PLAYLIST_NOT_FOUND", "message": f"Playlist {playlist_id} not found"}})

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVERS_DIR / f"playlist_{playlist_id}.jpg"
    content = await file.read()
    cover_path.write_bytes(content)

    playlist.cover_art_url = f"/static/covers/playlist_{playlist_id}.jpg"
    db.commit()
    db.refresh(playlist)
    logger.info("playlist_cover_uploaded", playlist_id=playlist_id)
    return PlaylistResponse.model_validate(playlist)


@router.delete("/{playlist_id}/cover", response_model=PlaylistResponse)
def delete_playlist_cover(
    playlist_id: int,
    db: Session = Depends(get_db),
) -> PlaylistResponse:
    """Remove cover art from a playlist."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail={"error": {"code": "PLAYLIST_NOT_FOUND", "message": f"Playlist {playlist_id} not found"}})

    cover_path = COVERS_DIR / f"playlist_{playlist_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()

    playlist.cover_art_url = None
    db.commit()
    db.refresh(playlist)
    logger.info("playlist_cover_deleted", playlist_id=playlist_id)
    return PlaylistResponse.model_validate(playlist)
