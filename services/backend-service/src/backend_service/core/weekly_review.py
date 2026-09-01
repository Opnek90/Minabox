"""Build the weekly listening review for parents (issue #170).

Turns the raw rows in ``playback_events`` (and the ``tags`` table) into one
readable weekly story: total listening time, the change from the previous week,
the distribution across weekdays, the most played card and the cards that have
never been played at all.

The honesty rules from :mod:`backend_service.core.playback_stats` apply here
too: only ``listened_ms`` is counted and every event is capped at
``MAX_MINUTES_PER_EVENT``. This module never computes minutes on its own - it
calls :func:`minutes_for_event` - so a summary can never inflate itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend_service.core.playback_stats import minutes_for_event
from backend_service.core.usage_limits import read_daily_limit_settings
from backend_service.models.database import PlaybackEvent, Tag

# How many never-played cards to list in detail; the full count is reported
# separately so a large ignored library still shows the honest number.
NEVER_PLAYED_LIMIT = 20


@dataclass
class MostPlayed:
    tag_id: int
    name: str | None
    play_count: int
    minutes: float


@dataclass
class NeverPlayed:
    tag_id: int
    name: str | None
    created_at: str  # ISO date (YYYY-MM-DD)


@dataclass
class WeeklyReview:
    week_start: str  # YYYY-MM-DD, Monday (local)
    week_end: str  # YYYY-MM-DD, Sunday (local)
    total_minutes: float
    prev_total_minutes: float
    delta_minutes: float
    minutes_per_weekday: list[float]  # length 7, Monday .. Sunday
    daily_limit_enabled: bool
    daily_limit_minutes: int
    average_minutes_per_day: float
    most_played: MostPlayed | None
    never_played: list[NeverPlayed] = field(default_factory=list)
    never_played_total: int = 0


def _local_now() -> datetime:
    """Timezone-aware 'now' in the host timezone (TZ env), UTC as fallback."""
    now_utc = datetime.now(UTC)
    try:
        return now_utc.astimezone()
    except Exception:
        return now_utc


def week_bounds(week_offset: int) -> tuple[datetime, datetime]:
    """UTC start/end for one ISO week. ``week_offset`` 0 = current week, 1 = last.

    A week runs from Monday 00:00 local time to the following Monday 00:00.
    """
    local_now = _local_now()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    this_monday = midnight - timedelta(days=midnight.weekday())
    start_local = this_monday - timedelta(weeks=week_offset)
    end_local = start_local + timedelta(weeks=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _completed_events_in(db: Session, start_utc: datetime, end_utc: datetime) -> list[PlaybackEvent]:
    """Completed playback events that ENDED in the window.

    Filtering on ``ended_at`` (not ``started_at``) keeps this consistent with
    the daily-limit accounting in :func:`get_today_listened_minutes`: a session
    counts towards the week in which it finished.
    """
    return (
        db.query(PlaybackEvent)
        .filter(
            PlaybackEvent.ended_at.isnot(None),
            PlaybackEvent.ended_at >= start_utc,
            PlaybackEvent.ended_at < end_utc,
        )
        .all()
    )


def _sum_minutes(events: list[PlaybackEvent]) -> float:
    return sum(minutes_for_event(e) for e in events)


def _local_weekday(dt: datetime) -> int:
    """Weekday (Monday=0) of a naive-UTC timestamp, converted to local time."""
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    try:
        return aware.astimezone().weekday()
    except Exception:
        return aware.weekday()


def _most_played(db: Session, events: list[PlaybackEvent]) -> MostPlayed | None:
    counts: dict[int, int] = {}
    minutes: dict[int, float] = {}
    for e in events:
        if e.tag_id is None:
            continue
        counts[e.tag_id] = counts.get(e.tag_id, 0) + 1
        minutes[e.tag_id] = minutes.get(e.tag_id, 0.0) + minutes_for_event(e)
    if not counts:
        return None
    # Most events wins; ties broken by more minutes, then lowest id for stability.
    tag_id = max(counts, key=lambda t: (counts[t], minutes[t], -t))
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    return MostPlayed(
        tag_id=tag_id,
        name=tag.name if tag else None,
        play_count=counts[tag_id],
        minutes=round(minutes[tag_id], 1),
    )


def _never_played(db: Session) -> tuple[list[NeverPlayed], int]:
    """Cards that carry content but have never had a single playback event."""
    played_ids = {
        row[0]
        for row in db.query(PlaybackEvent.tag_id)
        .filter(PlaybackEvent.tag_id.isnot(None))
        .distinct()
    }
    candidates = (
        db.query(Tag)
        .filter(Tag.content_type.isnot(None), Tag.content_id.isnot(None))
        .order_by(Tag.created_at)
        .all()
    )
    never = [t for t in candidates if t.id not in played_ids]
    items = [
        NeverPlayed(
            tag_id=t.id,
            name=t.name,
            created_at=t.created_at.date().isoformat() if t.created_at else "",
        )
        for t in never[:NEVER_PLAYED_LIMIT]
    ]
    return items, len(never)


def build(db: Session, week_offset: int) -> WeeklyReview:
    """Assemble the weekly review for the ISO week ``week_offset`` weeks back."""
    start_utc, end_utc = week_bounds(week_offset)
    prev_start_utc, prev_end_utc = week_bounds(week_offset + 1)

    events = _completed_events_in(db, start_utc, end_utc)
    prev_events = _completed_events_in(db, prev_start_utc, prev_end_utc)

    total = _sum_minutes(events)
    prev_total = _sum_minutes(prev_events)

    per_weekday = [0.0] * 7
    for e in events:
        per_weekday[_local_weekday(e.ended_at)] += minutes_for_event(e)

    limit_enabled, limit_minutes = read_daily_limit_settings()
    never_items, never_total = _never_played(db)

    start_local = start_utc.astimezone()
    sunday_local = (end_utc - timedelta(days=1)).astimezone()

    return WeeklyReview(
        week_start=start_local.date().isoformat(),
        week_end=sunday_local.date().isoformat(),
        total_minutes=round(total, 1),
        prev_total_minutes=round(prev_total, 1),
        delta_minutes=round(total - prev_total, 1),
        minutes_per_weekday=[round(m, 1) for m in per_weekday],
        daily_limit_enabled=limit_enabled,
        daily_limit_minutes=limit_minutes,
        average_minutes_per_day=round(total / 7.0, 1),
        most_played=_most_played(db, events),
        never_played=never_items,
        never_played_total=never_total,
    )


__all__ = [
    "MostPlayed",
    "NeverPlayed",
    "WeeklyReview",
    "build",
    "week_bounds",
]
