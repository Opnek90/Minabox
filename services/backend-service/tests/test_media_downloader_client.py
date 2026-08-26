"""Tests for MediaDownloaderClient.get_progress().

download_video()'s retry logic is exercised implicitly by the rest of the
suite through routes_tracks.py; this covers only the progress poller, which
is new and must never raise regardless of what the media-downloader is doing.
"""

from __future__ import annotations

import httpx
import pytest

from backend_service.infrastructure import media_downloader_client as client_module
from backend_service.infrastructure.media_downloader_client import MediaDownloaderClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://media-downloader/x")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    response: _FakeResponse | Exception = _FakeResponse(200, {"stage": "downloading", "percent": 50.0})

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        if isinstance(type(self).response, Exception):
            raise type(self).response
        return type(self).response


@pytest.fixture(autouse=True)
def fake_httpx(monkeypatch):
    monkeypatch.setattr(client_module.httpx, "AsyncClient", _FakeAsyncClient)
    yield


@pytest.mark.asyncio
async def test_get_progress_returns_the_reported_stage():
    client = MediaDownloaderClient()
    _FakeAsyncClient.response = _FakeResponse(200, {"stage": "converting", "percent": None})
    result = await client.get_progress("42")
    assert result == {"stage": "converting", "percent": None}


@pytest.mark.asyncio
async def test_get_progress_never_raises_on_network_error():
    client = MediaDownloaderClient()
    _FakeAsyncClient.response = httpx.ConnectError("refused")
    result = await client.get_progress("42")
    assert result == {"stage": "unknown", "percent": None}


@pytest.mark.asyncio
async def test_get_progress_never_raises_on_http_error():
    client = MediaDownloaderClient()
    _FakeAsyncClient.response = _FakeResponse(500, {})
    result = await client.get_progress("42")
    assert result == {"stage": "unknown", "percent": None}
