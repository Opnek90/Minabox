"""REST API endpoints for podcasts."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.models.database import Podcast, PodcastEpisode
from backend_service.models.schemas import (
    PodcastCreate,
    PodcastEpisodeResponse,
    PodcastResponse,
    PodcastUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("", response_model=list[PodcastResponse])
async def list_podcasts(db: Session = Depends(get_db)) -> list[PodcastResponse]:
    """List all podcasts."""
    logger.info("api_list_podcasts")
    podcasts = db.query(Podcast).all()
    return [PodcastResponse.model_validate(p) for p in podcasts]


@router.get("/{podcast_id}", response_model=PodcastResponse)
async def get_podcast(
    podcast_id: int, db: Session = Depends(get_db)
) -> PodcastResponse:
    """Get podcast by ID."""
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
    return PodcastResponse.model_validate(podcast)


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
    return PodcastResponse.model_validate(podcast)


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
    db.delete(podcast)
    db.commit()
    logger.info("api_delete_podcast_completed", podcast_id=podcast_id)
