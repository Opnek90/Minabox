"""Optional online lookup of artist, album and cover art.

For files that carry no usable tags at all, the box can ask MusicBrainz for the
recording and the Cover Art Archive for a front cover. This is **off by
default** and lives behind ``online_metadata_lookup_enabled`` in
``general_settings.json``, because a lookup sends the track title and artist to
a third party.

Like every other reader under ``core/``, the setting is read fresh on each
call, so toggling it in the WebUI takes effect without a restart. ``lookup()``
never raises - any network error, timeout or unexpected payload yields
``None``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
import structlog
from shared_lib.version import get_version

from backend_service.core.general_settings import read_general_settings
from backend_service.core.track_metadata import COVER_MAX_BYTES

logger = structlog.get_logger(__name__)

_MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
_COVER_ART_URL = "https://coverartarchive.org/release/{mbid}/front-500"

# MusicBrainz asks for a descriptive User-Agent with contact info and rejects
# generic ones. It also rate-limits anonymous clients to roughly one request
# per second - hence the module-wide throttle below.
_USER_AGENT = f"Minabox/{get_version()} (+https://github.com/Opnek90/Minabox)"
_MIN_INTERVAL_SEC = 1.1
_HTTP_TIMEOUT_SEC = 8.0

_throttle_lock = asyncio.Lock()
_last_request_at = 0.0


@dataclass
class OnlineMeta:
    """What an online lookup could resolve. Every field is optional."""

    artist: str | None = None
    album: str | None = None
    cover: tuple[bytes, str] | None = None


def online_lookup_enabled() -> bool:
    """True when the user has opted in to third-party metadata lookups."""
    return bool(read_general_settings().get("online_metadata_lookup_enabled", False))


async def _throttled_get(
    client: httpx.AsyncClient, url: str, **kwargs: object
) -> httpx.Response:
    """GET *url*, keeping at least ``_MIN_INTERVAL_SEC`` between calls."""
    global _last_request_at
    async with _throttle_lock:
        wait = _MIN_INTERVAL_SEC - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        response = await client.get(url, **kwargs)  # type: ignore[arg-type]
        _last_request_at = time.monotonic()
        return response


async def lookup(title: str, artist: str | None = None) -> OnlineMeta | None:
    """Resolve artist, album and cover for *title* (optionally scoped by *artist*).

    Returns ``None`` if nothing usable was found or the network failed.
    """
    title = (title or "").strip()
    if not title:
        return None

    query = f'recording:"{title}"'
    if artist and artist.strip():
        query += f' AND artist:"{artist.strip()}"'

    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SEC, follow_redirects=True, headers=headers
        ) as client:
            resp = await _throttled_get(
                client,
                _MUSICBRAINZ_URL,
                params={"query": query, "fmt": "json", "limit": 5},
            )
            resp.raise_for_status()
            recordings = resp.json().get("recordings") or []
            if not recordings:
                logger.info("online_metadata_lookup_empty", title=title)
                return None

            best = recordings[0]
            meta = OnlineMeta()
            credits = best.get("artist-credit") or []
            if credits and isinstance(credits[0], dict):
                meta.artist = (credits[0].get("name") or "").strip() or None

            releases = best.get("releases") or []
            release_mbid: str | None = None
            for release in releases:
                if isinstance(release, dict) and release.get("id"):
                    release_mbid = release["id"]
                    meta.album = (release.get("title") or "").strip() or None
                    break

            if release_mbid:
                meta.cover = await _fetch_cover(client, release_mbid)

            if meta.artist or meta.album or meta.cover:
                logger.info(
                    "online_metadata_lookup_hit",
                    title=title,
                    has_artist=bool(meta.artist),
                    has_album=bool(meta.album),
                    has_cover=bool(meta.cover),
                )
                return meta
            return None
    except Exception as exc:  # noqa: BLE001 - lookup is strictly best effort
        logger.warning("online_metadata_lookup_failed", title=title, error=str(exc))
        return None


async def _fetch_cover(
    client: httpx.AsyncClient, release_mbid: str
) -> tuple[bytes, str] | None:
    """Front cover for a MusicBrainz release MBID, via the Cover Art Archive."""
    try:
        resp = await client.get(_COVER_ART_URL.format(mbid=release_mbid))
        if resp.status_code != 200:
            return None
        data = resp.content
        if not data or len(data) > COVER_MAX_BYTES:
            return None
        ext = ".png" if "png" in resp.headers.get("content-type", "").lower() else ".jpg"
        return data, ext
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "online_metadata_cover_failed", release=release_mbid, error=str(exc)
        )
        return None


__all__ = ["OnlineMeta", "lookup", "online_lookup_enabled"]
