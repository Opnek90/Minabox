"""Tests for the analytics-retention purge (issue #170)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend_service.core import analytics_retention, general_settings
from backend_service.models.database import Base, PlaybackEvent, TagScanEvent


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


def _settings(**values):
    general_settings.general_settings_path().write_text(
        json.dumps(values), encoding="utf-8"
    )
    general_settings.invalidate()


def _seed(db):
    now = datetime.now(UTC)
    old = now - timedelta(weeks=60)
    recent = now - timedelta(weeks=2)
    db.add_all(
        [
            PlaybackEvent(started_at=old, ended_at=old, content_type="playlist", listened_ms=1000),
            PlaybackEvent(started_at=recent, ended_at=recent, content_type="playlist", listened_ms=1000),
            TagScanEvent(tag_uid="AA", action="play", scanned_at=old),
            TagScanEvent(tag_uid="BB", action="play", scanned_at=recent),
        ]
    )
    db.commit()


def test_purge_removes_only_old_rows_in_both_tables(db):
    _settings(analytics_retention_weeks=52)
    _seed(db)

    deleted = analytics_retention.purge_once(db)

    assert deleted == 2
    assert db.query(PlaybackEvent).count() == 1
    assert db.query(TagScanEvent).count() == 1


def test_zero_weeks_keeps_everything(db):
    _settings(analytics_retention_weeks=0)
    _seed(db)

    deleted = analytics_retention.purge_once(db)

    assert deleted == 0
    assert db.query(PlaybackEvent).count() == 2
    assert db.query(TagScanEvent).count() == 2


def test_default_is_one_year(db):
    # No setting written at all -> default 52 weeks applies.
    _seed(db)
    analytics_retention.purge_once(db)
    assert db.query(PlaybackEvent).count() == 1
