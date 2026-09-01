"""The optional MusicBrainz / Cover Art Archive lookup.

It is strictly best effort: every network failure has to come back as ``None``
rather than an exception, and the MusicBrainz rate limit has to be respected.
"""

from __future__ import annotations

import httpx
import pytest

from backend_service.core import online_metadata


class _FakeResponse:
    def __init__(
        self,
        payload: dict | None = None,
        *,
        status_code: int = 200,
        content: bytes = b"",
        content_type: str = "image/jpeg",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Serves a queued response per GET call; records the URLs it saw."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_a) -> bool:
        return False

    async def get(self, url: str, **_kw: object):
        self.calls.append(url)
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture(autouse=True)
def _reset_throttle(monkeypatch):
    monkeypatch.setattr(online_metadata, "_last_request_at", 0.0)
    yield


def _install(monkeypatch, client: _FakeClient) -> None:
    monkeypatch.setattr(online_metadata.httpx, "AsyncClient", lambda *a, **kw: client)


@pytest.mark.asyncio
async def test_lookup_resolves_artist_album_and_cover(monkeypatch):
    recording = {
        "artist-credit": [{"name": "Fredrik Vahle"}],
        "releases": [{"id": "rel-123", "title": "Anne Kaffeekanne"}],
    }
    client = _FakeClient(
        [
            _FakeResponse({"recordings": [recording]}),
            _FakeResponse(content=b"JPEGBYTES", content_type="image/jpeg"),
        ]
    )
    _install(monkeypatch, client)

    meta = await online_metadata.lookup("Anne Kaffeekanne", "Fredrik Vahle")

    assert meta is not None
    assert meta.artist == "Fredrik Vahle"
    assert meta.album == "Anne Kaffeekanne"
    assert meta.cover == (b"JPEGBYTES", ".jpg")
    assert "rel-123" in client.calls[1]


@pytest.mark.asyncio
async def test_lookup_returns_none_without_matches(monkeypatch):
    _install(monkeypatch, _FakeClient([_FakeResponse({"recordings": []})]))
    assert await online_metadata.lookup("Nothing here") is None


@pytest.mark.asyncio
async def test_lookup_swallows_network_errors(monkeypatch):
    _install(monkeypatch, _FakeClient([httpx.ConnectError("no route")]))
    assert await online_metadata.lookup("Whatever") is None


@pytest.mark.asyncio
async def test_lookup_skips_empty_title(monkeypatch):
    _install(monkeypatch, _FakeClient([]))
    assert await online_metadata.lookup("   ") is None


@pytest.mark.asyncio
async def test_throttled_get_waits_between_calls(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(online_metadata.asyncio, "sleep", fake_sleep)
    client = _FakeClient([_FakeResponse(), _FakeResponse()])

    await online_metadata._throttled_get(client, "http://a")
    await online_metadata._throttled_get(client, "http://b")

    assert slept and slept[-1] > 0
