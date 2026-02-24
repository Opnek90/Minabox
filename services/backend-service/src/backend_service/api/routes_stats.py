"""REST API endpoints for listening statistics (Parent Dashboard)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend_service.core.db_manager import get_db
from backend_service.core.playback_stats import get_today_listened_minutes, get_total_listened_minutes
from backend_service.models.database import PlaybackEvent, Playlist, Podcast, Stream, Tag, Track

router = APIRouter()

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
GENERAL_SETTINGS_PATH = DATA_PATH / "general_settings.json"


def _read_daily_limit() -> tuple[bool, int]:
    """Read daily_limit_enabled and daily_limit_minutes from general_settings.json."""
    if not GENERAL_SETTINGS_PATH.exists():
        return (False, 120)
    try:
        data = json.loads(GENERAL_SETTINGS_PATH.read_text(encoding="utf-8"))
        enabled = bool(data.get("daily_limit_enabled", False))
        minutes = max(1, min(1440, int(data.get("daily_limit_minutes", 120))))
        return (enabled, minutes)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return (False, 120)


class MinutesPerDayItem(BaseModel):
    date: str  # YYYY-MM-DD
    minutes: float


class TopTagItem(BaseModel):
    tag_id: int
    name: str | None
    scan_count: int


class TopPlaylistItem(BaseModel):
    playlist_id: int
    name: str | None
    play_count: int


class HeatmapItem(BaseModel):
    hour: int  # 0-23
    weekday: int  # 0-6, Monday=0
    minutes: float


class ListeningSummaryResponse(BaseModel):
    minutes_per_day: list[MinutesPerDayItem]
    top_tags: list[TopTagItem]
    top_playlists: list[TopPlaylistItem]
    heatmap: list[HeatmapItem]


class UsageTodayResponse(BaseModel):
    """Today's listening minutes and daily limit (for Parent Dashboard)."""
    minutes_today: float
    daily_limit_enabled: bool
    daily_limit_minutes: int


class OverviewResponse(BaseModel):
    """Dashboard overview: listening minutes and media counts."""
    minutes_today: float
    minutes_total: float
    daily_limit_enabled: bool
    daily_limit_minutes: int
    tags_count: int
    tracks_count: int
    streams_count: int
    podcasts_count: int
    playlists_count: int


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Dashboard overview (minutes + counts)",
)
async def get_overview(db: Session = Depends(get_db)) -> OverviewResponse:
    """Return listening minutes (today/total) and counts for tags, tracks, streams, podcasts, playlists."""
    minutes_today = get_today_listened_minutes(db)
    minutes_total = get_total_listened_minutes(db)
    daily_limit_enabled, daily_limit_minutes = _read_daily_limit()
    tags_count = db.query(Tag).count()
    tracks_count = db.query(Track).count()
    streams_count = db.query(Stream).count()
    podcasts_count = db.query(Podcast).count()
    playlists_count = db.query(Playlist).count()
    return OverviewResponse(
        minutes_today=round(minutes_today, 1),
        minutes_total=round(minutes_total, 1),
        daily_limit_enabled=daily_limit_enabled,
        daily_limit_minutes=daily_limit_minutes,
        tags_count=tags_count,
        tracks_count=tracks_count,
        streams_count=streams_count,
        podcasts_count=podcasts_count,
        playlists_count=playlists_count,
    )


@router.post(
    "/reset",
    status_code=204,
    summary="Reset listening statistics (Parent Dashboard)",
)
async def reset_listening_stats(db: Session = Depends(get_db)) -> None:
    """Delete all playback events. Heute gehört and Gesamt gehört become 0."""
    db.query(PlaybackEvent).delete()
    db.commit()


@router.get(
    "/usage-today",
    response_model=UsageTodayResponse,
    summary="Today's usage and daily limit (Parent Dashboard)",
)
async def get_usage_today(db: Session = Depends(get_db)) -> UsageTodayResponse:
    """Return minutes listened today and daily limit settings."""
    minutes_today = get_today_listened_minutes(db)
    daily_limit_enabled, daily_limit_minutes = _read_daily_limit()
    return UsageTodayResponse(
        minutes_today=round(minutes_today, 1),
        daily_limit_enabled=daily_limit_enabled,
        daily_limit_minutes=daily_limit_minutes,
    )


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


@router.get(
    "/listening-summary",
    response_model=ListeningSummaryResponse,
    summary="Listening summary for Parent Dashboard",
)
async def get_listening_summary(
    from_date: str = Query(..., description="Start date YYYY-MM-DD"),
    to_date: str = Query(..., description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> ListeningSummaryResponse:
    """Return aggregated listening stats: minutes per day, top tags, top playlists, heatmap."""
    start = _parse_date(from_date)
    end = _parse_date(to_date)
    if not start or not end or start > end:
        return ListeningSummaryResponse(
            minutes_per_day=[],
            top_tags=[],
            top_playlists=[],
            heatmap=[],
        )
    # End of to_date day
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Events with ended_at set (completed sessions)
    events = (
        db.query(PlaybackEvent)
        .filter(
            PlaybackEvent.started_at >= start,
            PlaybackEvent.started_at <= end,
            PlaybackEvent.ended_at.isnot(None),
        )
        .all()
    )

    minutes_per_day: dict[str, float] = defaultdict(float)
    tag_counts: dict[int, int] = defaultdict(int)
    playlist_counts: dict[int, int] = defaultdict(int)
    heatmap_grid: dict[tuple[int, int], float] = defaultdict(float)

    for e in events:
        duration_sec = (e.ended_at - e.started_at).total_seconds()
        minutes = duration_sec / 60.0
        day_key = e.started_at.strftime("%Y-%m-%d")
        minutes_per_day[day_key] += minutes
        wd = e.started_at.weekday()
        hour = e.started_at.hour
        heatmap_grid[(hour, wd)] += minutes
        if e.tag_id is not None:
            tag_counts[e.tag_id] += 1
        if e.playlist_id is not None:
            playlist_counts[e.playlist_id] += 1

    # Build minutes_per_day list (all days in range)
    days: list[MinutesPerDayItem] = []
    d = start.date()
    end_date = end.date()
    while d <= end_date:
        days.append(
            MinutesPerDayItem(date=d.isoformat(), minutes=minutes_per_day[d.isoformat()])
        )
        d += timedelta(days=1)

    # Top tags by scan count – top 3
    tag_ids_sorted = sorted(tag_counts.keys(), key=lambda x: -tag_counts[x])[:3]
    top_tags = []
    for tid in tag_ids_sorted:
        tag = db.query(Tag).filter(Tag.id == tid).first()
        top_tags.append(
            TopTagItem(
                tag_id=tid,
                name=tag.name if tag else None,
                scan_count=tag_counts[tid],
            )
        )

    # Top playlists by play count – top 3
    pl_ids_sorted = sorted(playlist_counts.keys(), key=lambda x: -playlist_counts[x])[:3]
    top_playlists = []
    for pid in pl_ids_sorted:
        pl = db.query(Playlist).filter(Playlist.id == pid).first()
        top_playlists.append(
            TopPlaylistItem(
                playlist_id=pid,
                name=pl.name if pl else None,
                play_count=playlist_counts[pid],
            )
        )

    # Heatmap: all 24*7 cells (hour 0-23, weekday 0-6)
    heatmap: list[HeatmapItem] = []
    for hour in range(24):
        for weekday in range(7):
            heatmap.append(
                HeatmapItem(
                    hour=hour,
                    weekday=weekday,
                    minutes=heatmap_grid[(hour, weekday)],
                )
            )

    return ListeningSummaryResponse(
        minutes_per_day=days,
        top_tags=top_tags,
        top_playlists=top_playlists,
        heatmap=heatmap,
    )
