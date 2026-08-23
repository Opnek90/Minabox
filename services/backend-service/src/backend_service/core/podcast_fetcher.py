"""Background task to fetch podcast RSS feeds and store new episodes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import feedparser
import httpx
import structlog
from sqlalchemy.orm import Session

from backend_service.models.database import Podcast, PodcastEpisode

if TYPE_CHECKING:
    from backend_service.core.db_manager import DatabaseManager

logger = structlog.get_logger(__name__)

FETCH_INTERVAL_SECONDS = 24 * 3600  # 24 hours


def _parse_published(entry: dict) -> datetime | None:
    """Parse entry published date to timezone-aware datetime."""
    parsed = entry.get("published_parsed")
    if parsed and len(parsed) >= 6:
        try:
            return datetime(
                parsed[0], parsed[1], parsed[2],
                parsed[3] if len(parsed) > 3 else 0,
                parsed[4] if len(parsed) > 4 else 0,
                parsed[5] if len(parsed) > 5 else 0,
                tzinfo=UTC,
            )
        except (ValueError, TypeError):
            pass
    return None


def _get_audio_url(entry: dict) -> str | None:
    """Get first audio enclosure URL from feed entry."""
    enclosures = entry.get("enclosures") or []
    for enc in enclosures:
        href = enc.get("href") if isinstance(enc, dict) else getattr(enc, "href", None)
        if not href:
            continue
        enc_type = (enc.get("type") if isinstance(enc, dict) else getattr(enc, "type", "")) or ""
        if "audio" in enc_type.lower() or not enc_type:
            return href
    if enclosures:
        first = enclosures[0]
        return first.get("href") if isinstance(first, dict) else getattr(first, "href", None)
    return None


def _duration_seconds_to_ms(entry: dict) -> int | None:
    """Try to get duration in ms from itunes_duration or similar."""
    duration = entry.get("itunes_duration")
    if duration is None:
        return None
    if isinstance(duration, (int, float)):
        if duration > 3600 * 24:
            return None
        return int(duration * 1000)
    if isinstance(duration, str):
        parts = duration.replace(",", ".").split(":")
        try:
            if len(parts) == 1:
                return int(float(parts[0]) * 1000)
            if len(parts) == 2:
                return (int(parts[0]) * 60 + int(float(parts[1]))) * 1000
            if len(parts) == 3:
                return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))) * 1000
        except (ValueError, TypeError):
            pass
    return None


def fetch_and_store_episodes(session: Session, podcast: Podcast) -> int:
    """Fetch RSS for one podcast and insert new episodes. Returns count of new episodes."""
    try:
        response = httpx.get(podcast.rss_url, timeout=30.0)
        response.raise_for_status()
    except Exception as e:
        logger.warning("podcast_fetch_failed", podcast_id=podcast.id, error=str(e))
        return 0

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        logger.warning("podcast_parse_failed", podcast_id=podcast.id)
        return 0

    added = 0
    for entry in parsed.entries:
        audio_url = _get_audio_url(entry)
        if not audio_url:
            continue
        title = (entry.get("title") or "").strip() or "Untitled"
        guid = entry.get("id") or entry.get("link") or audio_url
        published = _parse_published(entry)
        duration_ms = _duration_seconds_to_ms(entry)

        existing = (
            session.query(PodcastEpisode)
            .filter(
                PodcastEpisode.podcast_id == podcast.id,
                PodcastEpisode.source_uri == audio_url,
            )
            .first()
        )
        if existing:
            continue
        session.add(
            PodcastEpisode(
                podcast_id=podcast.id,
                title=title[:512],
                source_uri=audio_url[:1024],
                guid=guid[:512] if guid else None,
                published_at=published,
                duration_ms=duration_ms,
            )
        )
        added += 1

    podcast.last_fetched_at = datetime.now(UTC)
    session.commit()
    if added > 0:
        logger.info("podcast_fetched", podcast_id=podcast.id, new_episodes=added)
    else:
        logger.debug("podcast_fetched", podcast_id=podcast.id, new_episodes=0)
    return added


def fetch_all_podcasts(db_manager: DatabaseManager) -> int:
    """Fetch every feed once. Returns the number of new episodes.

    Blocking from start to finish - both the HTTP request and the feed parsing
    are synchronous - so it opens its own session and is only ever called
    through a worker thread. See `run_podcast_fetch_loop`.
    """
    added = 0
    session = db_manager.get_session()
    try:
        for podcast in session.query(Podcast).all():
            try:
                added += fetch_and_store_episodes(session, podcast)
            except Exception as e:
                logger.exception("podcast_fetch_error", podcast_id=podcast.id, error=str(e))
    finally:
        session.close()
    return added


async def run_podcast_fetch_loop(db_manager: DatabaseManager | None) -> None:
    """Background task: fetch all podcast RSS feeds after an initial delay, then every 24h.

    The work runs in a worker thread. It used to run directly on the event
    loop, where a single unreachable feed blocked everything the service does
    for the full 30 second timeout - no REST, no WebSocket, no MQTT dispatch.
    With a handful of feeds that added up to minutes of a frozen box.
    """
    if not db_manager:
        return
    await asyncio.sleep(60)  # first run 1 minute after start
    while True:
        try:
            await asyncio.to_thread(fetch_all_podcasts, db_manager)
        except asyncio.CancelledError:
            break
        except Exception as e:
            # A failed round must not end the background task.
            logger.warning("podcast_fetch_round_failed", error=str(e))

        try:
            await asyncio.sleep(FETCH_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break

    logger.info("podcast_fetch_loop_stopped")
