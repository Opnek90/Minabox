"""REST API endpoints for podcasts."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Podcast, PodcastEpisode
from backend_service.models.schemas import (
    PodcastCreate,
    PodcastEpisodeResponse,
    PodcastResponse,
    PodcastUpdate,
)

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/data/static"))
COVERS_DIR = STATIC_DIR / "covers"

logger = structlog.get_logger(__name__)
router = APIRouter()


def _podcast_response_with_latest(
    podcast: Podcast, db: Session
) -> PodcastResponse:
    """Build PodcastResponse with latest episode info."""
    latest = (
        db.query(PodcastEpisode)
        .filter(PodcastEpisode.podcast_id == podcast.id)
        .order_by(PodcastEpisode.published_at.desc())
        .first()
    )
    base = PodcastResponse.model_validate(podcast)
    return base.model_copy(
        update={
            "latest_episode_title": latest.title if latest else None,
            "latest_episode_published_at": latest.published_at if latest else None,
        }
    )


@router.get("", response_model=list[PodcastResponse])
async def list_podcasts(db: Session = Depends(get_db)) -> list[PodcastResponse]:
    """List all podcasts with latest episode info."""
    logger.info("api_list_podcasts")
    podcasts = db.query(Podcast).all()
    if not podcasts:
        return []
    podcast_ids = [p.id for p in podcasts]
    episodes = (
        db.query(PodcastEpisode)
        .filter(PodcastEpisode.podcast_id.in_(podcast_ids))
        .order_by(PodcastEpisode.podcast_id, PodcastEpisode.published_at.desc())
        .all()
    )
    latest_by_podcast: dict[int, PodcastEpisode] = {}
    for ep in episodes:
        if ep.podcast_id not in latest_by_podcast:
            latest_by_podcast[ep.podcast_id] = ep
    result = []
    for p in podcasts:
        base = PodcastResponse.model_validate(p)
        ep = latest_by_podcast.get(p.id)
        result.append(
            base.model_copy(
                update={
                    "latest_episode_title": ep.title if ep else None,
                    "latest_episode_published_at": ep.published_at if ep else None,
                }
            )
        )
    return result


@router.get("/{podcast_id}", response_model=PodcastResponse)
async def get_podcast(
    podcast_id: int, db: Session = Depends(get_db)
) -> PodcastResponse:
    """Get podcast by ID with latest episode info."""
    logger.info("api_get_podcast", podcast_id=podcast_id)
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    return _podcast_response_with_latest(podcast, db)


@router.get("/{podcast_id}/episodes", response_model=list[PodcastEpisodeResponse])
async def list_podcast_episodes(
    podcast_id: int, db: Session = Depends(get_db)
) -> list[PodcastEpisodeResponse]:
    """List episodes of a podcast (newest first)."""
    logger.info("api_list_podcast_episodes", podcast_id=podcast_id)
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    episodes = (
        db.query(PodcastEpisode)
        .filter(PodcastEpisode.podcast_id == podcast_id)
        .order_by(PodcastEpisode.published_at.desc())
        .all()
    )
    return [PodcastEpisodeResponse.model_validate(e) for e in episodes]


@router.post("", response_model=PodcastResponse, status_code=201)
async def create_podcast(
    podcast_data: PodcastCreate,
    db: Session = Depends(get_db),
) -> PodcastResponse:
    """Create a new podcast."""
    logger.info("api_create_podcast", title=podcast_data.title)
    podcast = Podcast(
        title=podcast_data.title,
        rss_url=podcast_data.rss_url,
        description=podcast_data.description,
        cover_art_url=podcast_data.cover_art_url,
    )
    db.add(podcast)
    db.commit()
    db.refresh(podcast)
    logger.info("api_podcast_created", podcast_id=podcast.id, title=podcast.title)
    return PodcastResponse.model_validate(podcast)


@router.put("/{podcast_id}", response_model=PodcastResponse)
async def update_podcast(
    podcast_id: int,
    podcast_data: PodcastUpdate,
    db: Session = Depends(get_db),
) -> PodcastResponse:
    """Update an existing podcast."""
    logger.info("api_update_podcast", podcast_id=podcast_id)
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    if podcast_data.title is not None:
        podcast.title = podcast_data.title
    if podcast_data.rss_url is not None:
        podcast.rss_url = podcast_data.rss_url
    if podcast_data.description is not None:
        podcast.description = podcast_data.description
    if podcast_data.cover_art_url is not None:
        podcast.cover_art_url = podcast_data.cover_art_url
    db.commit()
    db.refresh(podcast)
    return _podcast_response_with_latest(podcast, db)


@router.delete("/{podcast_id}", status_code=204)
async def delete_podcast(
    podcast_id: int, db: Session = Depends(get_db)
) -> None:
    """Delete a podcast and its episodes."""
    logger.info("api_delete_podcast", podcast_id=podcast_id)
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    cover_path = COVERS_DIR / f"podcast_{podcast_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()
    db.delete(podcast)
    db.commit()
    logger.info("api_delete_podcast_completed", podcast_id=podcast_id)


@router.post("/{podcast_id}/cover", response_model=PodcastResponse)
async def upload_podcast_cover(
    podcast_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PodcastResponse:
    """Upload cover art for a podcast."""
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVERS_DIR / f"podcast_{podcast_id}.jpg"
    content = await file.read()
    cover_path.write_bytes(content)
    podcast.cover_art_url = f"/static/covers/podcast_{podcast_id}.jpg"
    db.commit()
    db.refresh(podcast)
    logger.info("podcast_cover_uploaded", podcast_id=podcast_id)
    return _podcast_response_with_latest(podcast, db)


@router.delete("/{podcast_id}/cover", response_model=PodcastResponse)
async def delete_podcast_cover(
    podcast_id: int,
    db: Session = Depends(get_db),
) -> PodcastResponse:
    """Remove cover art from a podcast."""
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PODCAST_NOT_FOUND",
                    "message": f"Podcast {podcast_id} not found",
                    "details": {"podcast_id": podcast_id},
                }
            },
        )
    cover_path = COVERS_DIR / f"podcast_{podcast_id}.jpg"
    if cover_path.exists():
        cover_path.unlink()
    podcast.cover_art_url = None
    db.commit()
    db.refresh(podcast)
    logger.info("podcast_cover_deleted", podcast_id=podcast_id)
    return _podcast_response_with_latest(podcast, db)
