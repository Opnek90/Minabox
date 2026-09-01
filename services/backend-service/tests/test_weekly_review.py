"""Tests for the weekly listening review (issue #170).

Verifies that the aggregation obeys the honesty rules (listened_ms only, per
event capped), buckets minutes by the correct weekday, picks the most played
card and lists only cards that carry content but were never played.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend_service.core import general_settings, weekly_review
from backend_service.core.playback_stats import MAX_MINUTES_PER_EVENT
from backend_service.models.database import Base, PlaybackEvent, Tag


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _data_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    general_settings.invalidate()
    yield
    general_settings.invalidate()


def _event(db, *, ended_at, listened_ms, tag_id=None):
    db.add(
        PlaybackEvent(
            started_at=ended_at - timedelta(minutes=30),
            ended_at=ended_at,
            content_type="playlist",
            listened_ms=listened_ms,
            tag_id=tag_id,
        )
    )


def test_totals_delta_and_weekday_distribution(db):
    last_start, _ = weekly_review.week_bounds(1)
    prev_start, _ = weekly_review.week_bounds(2)

    # Last week: 20 min on Monday, 10 min on Wednesday
    _event(db, ended_at=last_start + timedelta(hours=10), listened_ms=20 * 60_000)
    _event(db, ended_at=last_start + timedelta(days=2, hours=9), listened_ms=10 * 60_000)
    # Week before: 5 min
    _event(db, ended_at=prev_start + timedelta(hours=8), listened_ms=5 * 60_000)
    db.commit()

    r = weekly_review.build(db, week_offset=1)

    assert r.total_minutes == pytest.approx(30.0)
    assert r.prev_total_minutes == pytest.approx(5.0)
    assert r.delta_minutes == pytest.approx(25.0)
    assert r.minutes_per_weekday[0] == pytest.approx(20.0)  # Monday
    assert r.minutes_per_weekday[2] == pytest.approx(10.0)  # Wednesday
    assert sum(r.minutes_per_weekday) == pytest.approx(30.0)
    assert r.average_minutes_per_day == pytest.approx(30.0 / 7.0, abs=0.1)


def test_per_event_cap_and_null_listened_ms(db):
    last_start, _ = weekly_review.week_bounds(1)
    # A runaway event and one with no reliable figure.
    _event(db, ended_at=last_start + timedelta(hours=1), listened_ms=10 * 60 * 60_000)
    _event(db, ended_at=last_start + timedelta(hours=3), listened_ms=None)
    db.commit()

    r = weekly_review.build(db, week_offset=1)

    assert r.total_minutes == pytest.approx(MAX_MINUTES_PER_EVENT)


def test_open_event_is_ignored(db):
    last_start, _ = weekly_review.week_bounds(1)
    db.add(
        PlaybackEvent(
            started_at=last_start + timedelta(hours=1),
            ended_at=None,
            content_type="playlist",
            listened_ms=15 * 60_000,
        )
    )
    db.commit()

    r = weekly_review.build(db, week_offset=1)
    assert r.total_minutes == pytest.approx(0.0)


def test_most_played_card(db):
    last_start, _ = weekly_review.week_bounds(1)
    quiet = Tag(tag_id="AA", name="Quiet", content_type="playlist", content_id=1)
    loud = Tag(tag_id="BB", name="Loud", content_type="playlist", content_id=2)
    db.add_all([quiet, loud])
    db.flush()

    for _ in range(3):
        _event(db, ended_at=last_start + timedelta(hours=2), listened_ms=60_000, tag_id=loud.id)
    _event(db, ended_at=last_start + timedelta(hours=4), listened_ms=60_000, tag_id=quiet.id)
    db.commit()

    r = weekly_review.build(db, week_offset=1)
    assert r.most_played is not None
    assert r.most_played.tag_id == loud.id
    assert r.most_played.play_count == 3


def test_never_played_lists_only_unplayed_content_cards(db):
    last_start, _ = weekly_review.week_bounds(1)
    played = Tag(tag_id="AA", name="Played", content_type="playlist", content_id=1)
    ignored = Tag(tag_id="BB", name="Ignored", content_type="playlist", content_id=2)
    empty = Tag(tag_id="CC", name="Empty card", content_type=None, content_id=None)
    db.add_all([played, ignored, empty])
    db.flush()

    _event(db, ended_at=last_start + timedelta(hours=1), listened_ms=60_000, tag_id=played.id)
    db.commit()

    r = weekly_review.build(db, week_offset=1)
    names = {n.name for n in r.never_played}
    assert names == {"Ignored"}
    assert r.never_played_total == 1


def test_daily_limit_snapshot(db):
    (
        # written directly so read_daily_limit_settings picks it up
        general_settings.general_settings_path()
    ).write_text(
        json.dumps({"daily_limit_enabled": True, "daily_limit_minutes": 60}),
        encoding="utf-8",
    )
    general_settings.invalidate()

    r = weekly_review.build(db, week_offset=1)
    assert r.daily_limit_enabled is True
    assert r.daily_limit_minutes == 60
