"""Tests for _check_allowed_domain in routes_tracks.py.

Only the domain gate itself - `/validate-url` and `/from-url` need a full DB
session and are out of scope here. This pins the one behaviour that matters
for go-live: the check reads the WebUI-configurable list fresh, so a saved
change is enforced without a restart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_service.api.routes_tracks import _check_allowed_domain
from backend_service.core.api_errors import ApiError


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    def write(**values: object) -> None:
        (tmp_path / "general_settings.json").write_text(json.dumps(values), encoding="utf-8")

    return write


def test_default_allows_soundcloud(settings_file):
    settings_file()
    _check_allowed_domain("https://soundcloud.com/artist/track")  # must not raise


def test_default_rejects_youtube(settings_file):
    settings_file()
    with pytest.raises(ApiError) as exc_info:
        _check_allowed_domain("https://www.youtube.com/watch?v=abc123")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "domain_not_allowed"


def test_admin_added_domain_is_enforced_without_restart(settings_file):
    settings_file()
    with pytest.raises(ApiError):
        _check_allowed_domain("https://vimeo.com/12345")

    settings_file(media_import_allowed_domains=["vimeo.com"])
    _check_allowed_domain("https://vimeo.com/12345")  # must not raise anymore
