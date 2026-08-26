"""Tests for the request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from media_downloader_service.models import DownloadRequest


def test_url_must_not_be_empty_rejects_blank():
    with pytest.raises(ValidationError):
        DownloadRequest(url="   ")


def test_url_is_trimmed():
    request = DownloadRequest(url="  https://example.org/x  ")
    assert request.url == "https://example.org/x"


def test_output_dir_defaults_to_none():
    request = DownloadRequest(url="https://example.org/x")
    assert request.output_dir is None
