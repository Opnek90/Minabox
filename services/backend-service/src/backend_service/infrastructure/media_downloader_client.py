"""HTTP client for the media-downloader-service."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Timeout for the actual download (large files may take several minutes)
_DOWNLOAD_TIMEOUT = 300.0
# Timeout for metadata-only requests
_INFO_TIMEOUT = 30.0


class MediaDownloaderError(Exception):
    """Raised when the media-downloader-service returns an error or is unreachable."""


class MediaDownloaderClient:
    """Async HTTP client for the media-downloader-service.

    The service URL is read from the MEDIA_DOWNLOADER_URL environment variable
    (default: http://media-downloader:8000) so that it can be overridden in
    development without code changes.
    """

    def __init__(self, base_url: str = "http://media-downloader:8000") -> None:
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def download_video(self, url: str) -> dict[str, Any]:
        """Request the media-downloader-service to download *url* as MP3.

        Args:
            url: Video URL supported by yt-dlp.

        Returns:
            Dict with file_path, title, artist, album, duration_ms,
            video_id, thumbnail_embedded.

        Raises:
            MediaDownloaderError: On HTTP error or connection failure.
        """
        logger.info("media_downloader_download_requested", url=url)
        try:
            async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/download",
                    json={"url": url},
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                logger.info(
                    "media_downloader_download_success",
                    video_id=data.get("video_id"),
                    title=data.get("title"),
                )
                return data
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc)
            logger.warning(
                "media_downloader_download_http_error",
                status=exc.response.status_code,
                detail=detail,
            )
            raise MediaDownloaderError(detail) from exc
        except httpx.RequestError as exc:
            logger.error("media_downloader_unreachable", error=str(exc))
            raise MediaDownloaderError(
                f"media-downloader-service unreachable: {exc}"
            ) from exc

    async def get_video_info(self, url: str) -> dict[str, Any]:
        """Fetch video metadata from *url* without downloading.

        Args:
            url: Video URL supported by yt-dlp.

        Returns:
            Dict with title, artist, duration_ms, thumbnail, video_id.

        Raises:
            MediaDownloaderError: On HTTP error or connection failure.
        """
        logger.info("media_downloader_info_requested", url=url)
        try:
            async with httpx.AsyncClient(timeout=_INFO_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/info",
                    params={"url": url},
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                logger.debug(
                    "media_downloader_info_success",
                    video_id=data.get("video_id"),
                )
                return data
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc)
            logger.warning(
                "media_downloader_info_http_error",
                status=exc.response.status_code,
                detail=detail,
            )
            raise MediaDownloaderError(detail) from exc
        except httpx.RequestError as exc:
            logger.error("media_downloader_unreachable", error=str(exc))
            raise MediaDownloaderError(
                f"media-downloader-service unreachable: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Try to extract a human-readable error message from the response body."""
    try:
        body = exc.response.json()
        # Our own error format: {"error": {"message": "..."}}
        if isinstance(body, dict):
            err = body.get("error") or body
            if isinstance(err, dict):
                return str(err.get("message") or err)
            return str(body.get("detail", str(exc)))
    except Exception:  # noqa: BLE001
        pass
    return str(exc)
