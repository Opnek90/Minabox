"""HTTP client for the media-downloader-service."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DOWNLOAD_TIMEOUT = 300.0
_INFO_TIMEOUT = 30.0


class MediaDownloaderError(Exception):
    """Raised when the media-downloader-service returns an error or is unreachable."""


class MediaDownloaderClient:
    """Async HTTP client for the media-downloader-service."""

    def __init__(self, base_url: str = "http://media-downloader:8007") -> None:
        self.base_url = base_url.rstrip("/")

    async def download_video(self, url: str, output_dir: str | None = None) -> dict[str, Any]:
        """POST /download – download *url* as MP3.

        Args:
            url: Video URL supported by yt-dlp.
            output_dir: Optional absolute container path for the MP3.
                        When provided the media-downloader writes directly
                        into that directory (e.g. /mnt/audio/tracks/{id}/).
        """
        logger.info("media_downloader_download_requested", url=url, output_dir=output_dir)
        payload: dict[str, Any] = {"url": url}
        if output_dir:
            payload["output_dir"] = output_dir
        try:
            async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
                response = await client.post(f"{self.base_url}/download", json=payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                logger.info("media_downloader_download_success", title=data.get("title"))
                return data
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc)
            logger.warning("media_downloader_download_http_error", status=exc.response.status_code, detail=detail)
            raise MediaDownloaderError(detail) from exc
        except httpx.RequestError as exc:
            logger.error("media_downloader_unreachable", error=str(exc))
            raise MediaDownloaderError(f"media-downloader-service unreachable: {exc}") from exc

    async def get_video_info(self, url: str) -> dict[str, Any]:
        """GET /info – fetch metadata without downloading."""
        logger.info("media_downloader_info_requested", url=url)
        try:
            async with httpx.AsyncClient(timeout=_INFO_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/info", params={"url": url})
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                logger.debug("media_downloader_info_success", video_id=data.get("video_id"))
                return data
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc)
            logger.warning("media_downloader_info_http_error", status=exc.response.status_code, detail=detail)
            raise MediaDownloaderError(detail) from exc
        except httpx.RequestError as exc:
            logger.error("media_downloader_unreachable", error=str(exc))
            raise MediaDownloaderError(f"media-downloader-service unreachable: {exc}") from exc


def _extract_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
        if isinstance(body, dict):
            err = body.get("error") or body
            if isinstance(err, dict):
                return str(err.get("message") or err)
            return str(body.get("detail", str(exc)))
    except Exception:  # noqa: BLE001
        pass
    return str(exc)
