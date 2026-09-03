"""The duration of a recording the browser made.

A voice message recorded in the WebUI arrives as WebM/Opus in Chrome and
Android - a container mutagen has no parser for, so the stored file yields no
duration at all. The recorder counted the seconds while the microphone was
open and sends that number along; these tests pin what the upload route is
allowed to do with it, because it is the one duration in the library that a
client, not the file, supplies.
"""

from __future__ import annotations

import pytest

from backend_service.api import routes_tracks
from backend_service.core.track_metadata import TrackTags


def _upload(client, **data):
    return client.post(
        "/api/v1/tracks/upload",
        files={"file": ("message.webm", b"x" * 512, "audio/webm")},
        data={"title": "Gute Nacht", **data},
    )


def test_a_recording_without_readable_tags_keeps_the_measured_duration(
    client, monkeypatch
):
    monkeypatch.setattr(routes_tracks, "read_tags", lambda _path: TrackTags())

    response = _upload(client, duration_ms=42_000)

    assert response.status_code == 201, response.text
    assert response.json()["duration_ms"] == 42_000


def test_the_files_own_duration_wins_over_the_measured_one(client, monkeypatch):
    """An .m4a recording (Safari) does carry a duration - that one is the truth."""
    monkeypatch.setattr(
        routes_tracks, "read_tags", lambda _path: TrackTags(duration_ms=17_000)
    )

    response = _upload(client, duration_ms=42_000)

    assert response.status_code == 201, response.text
    assert response.json()["duration_ms"] == 17_000


@pytest.mark.parametrize("sent", [0, -1, routes_tracks.MAX_CLIENT_DURATION_MS + 1])
def test_an_impossible_measured_duration_is_dropped_not_stored(
    client, monkeypatch, sent
):
    """No duration is better than one that poisons the listening statistics."""
    monkeypatch.setattr(routes_tracks, "read_tags", lambda _path: TrackTags())

    response = _upload(client, duration_ms=sent)

    assert response.status_code == 201, response.text
    assert response.json()["duration_ms"] is None


def test_an_ordinary_upload_still_needs_no_duration_field(client, monkeypatch):
    monkeypatch.setattr(routes_tracks, "read_tags", lambda _path: TrackTags())

    response = _upload(client)

    assert response.status_code == 201, response.text
    assert response.json()["duration_ms"] is None
