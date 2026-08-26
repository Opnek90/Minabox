"""Tests for the media-import domain allow-list (core/media_settings.py).

Covers the WebUI-configurable list itself, not the HTTP layer around it -
`_check_allowed_domain` in routes_tracks.py is a thin wrapper that just calls
`read_allowed_domains()` on every request.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_service.core.media_settings import (
    DEFAULT_ALLOWED_DOMAINS,
    clamp_allowed_domains,
    read_allowed_domains,
)


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    def write(**values: object) -> None:
        (tmp_path / "general_settings.json").write_text(json.dumps(values), encoding="utf-8")

    return write


def test_default_excludes_youtube():
    """YouTube has no built-in download feature a rights holder opts into,
    unlike SoundCloud/Bandcamp - it must not ship as a default source."""
    assert not any("youtube" in d or d == "youtu.be" for d in DEFAULT_ALLOWED_DOMAINS)
    assert "soundcloud.com" in DEFAULT_ALLOWED_DOMAINS
    assert "bandcamp.com" in DEFAULT_ALLOWED_DOMAINS


def test_read_allowed_domains_falls_back_to_default_when_unset(settings_file):
    settings_file(sleep_timer_minutes=30)
    assert read_allowed_domains() == DEFAULT_ALLOWED_DOMAINS


def test_read_allowed_domains_reflects_saved_setting(settings_file):
    settings_file(media_import_allowed_domains=["example.org", "EXAMPLE.NET"])
    assert read_allowed_domains() == frozenset({"example.org", "example.net"})


def test_clamp_allowed_domains_deduplicates_and_lowercases():
    result = clamp_allowed_domains(["Example.org", "example.org", " example.net "])
    assert result == ["example.org", "example.net"]


def test_clamp_allowed_domains_drops_non_strings():
    result = clamp_allowed_domains(["good.org", 123, None, ""])
    assert result == ["good.org"]


def test_clamp_allowed_domains_caps_list_length():
    result = clamp_allowed_domains([f"host{i}.example" for i in range(30)])
    assert len(result) == 20


def test_clamp_allowed_domains_empty_list_falls_back_to_default():
    """An explicit empty list would silently accept no domain at all - not a
    usable state for a feature that exists to import from *some* source."""
    assert clamp_allowed_domains([]) == sorted(DEFAULT_ALLOWED_DOMAINS)


def test_clamp_allowed_domains_malformed_input_falls_back_to_default():
    assert clamp_allowed_domains("not-a-list") == sorted(DEFAULT_ALLOWED_DOMAINS)
