"""FastAPI application entry point for the Media Downloader Service."""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from media_downloader_service.config import load_config
from media_downloader_service.downloader import DownloadError, MediaDownloader
from media_downloader_service.models import (
    DownloadRequest,
    DownloadResponse,
    VideoInfoResponse,
)

config = load_config()

# DEBUG -> human-readable console output; INFO and above -> structured JSON,
# the format the rest of the fleet's log aggregation expects. Mirrors
# shared_lib.logging.setup_structlog(), inlined rather than imported so this
# service keeps no dependency on shared-lib (see README.md).
_log_level = getattr(logging, config.log_level.upper(), logging.INFO)
_renderer = (
    structlog.dev.ConsoleRenderer()
    if config.log_level.upper() == "DEBUG"
    else structlog.processors.JSONRenderer()
)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        _renderer,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
)
logger = structlog.get_logger("media_downloader_service")

_start_time = time.monotonic()

# Only one conversion at a time: ffmpeg is CPU-heavy and this runs on a
# Raspberry Pi. Without this, moving the blocking yt-dlp/ffmpeg call off the
# event loop (below) would let concurrent /download requests fight each
# other for the same cores instead of the previous, accidental
# serialization.
_download_semaphore = asyncio.Semaphore(1)


def _resolve_output_dir(output_dir: str | None) -> Path:
    """Resolve the caller-supplied output_dir, or the configured default.

    Raises DownloadError if the path would land outside the shared audio
    volume - the API has no authentication, so nothing else stops a caller
    from pointing a download anywhere the container user can write to.
    """
    path = Path(output_dir) if output_dir else config.audio_tracks_dir
    base = config.audio_base_dir.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise DownloadError(f"output_dir must be inside {base}") from exc
    return resolved


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info(
        "service_startup",
        audio_tracks_dir=str(config.audio_tracks_dir),
        audio_quality=config.audio_quality,
    )
    config.audio_tracks_dir.mkdir(parents=True, exist_ok=True)
    yield
    logger.info("service_shutdown")


app = FastAPI(
    title="Media Downloader Service",
    description=(
        "Minabox microservice for local media import. Reads a media URL supplied by "
        "the backend and stores its audio track in the local library as MP3. It "
        "offers no options for credentials, cookies, sessions or decryption keys and "
        "is not intended to access restricted content – see README.md."
    ),
    version=os.environ.get("APP_VERSION", "0.0.0-dev"),
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        {
            "status": "healthy",
            "service": "media-downloader-service",
            # This service does not depend on shared-lib; the Dockerfile sets
            # this variable from its build arg (docs/Versionierung.md).
            "version": os.environ.get("APP_VERSION", "0.0.0-dev"),
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
        }
    )


@app.post("/download", response_model=DownloadResponse, status_code=201)
async def download_video(request: DownloadRequest) -> DownloadResponse:
    """Import the audio of a media URL into the local library as MP3.

    If *output_dir* is provided the MP3 is placed there; otherwise the
    service default (AUDIO_TRACKS_DIR) is used.

    The request carries a URL and nothing else – no credentials, cookies or
    keys are accepted, so only sources that are readable without them can be
    imported.
    """
    try:
        output_dir = _resolve_output_dir(request.output_dir)
        downloader = MediaDownloader(
            audio_quality=config.audio_quality, max_filesize_mb=config.max_filesize_mb
        )
        async with _download_semaphore:
            result = await asyncio.to_thread(downloader.download_video, request.url, output_dir)
    except DownloadError as exc:
        logger.warning("download_request_failed", url=request.url, error=str(exc))
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DOWNLOAD_FAILED",
                    "message": str(exc),
                    "details": {"url": request.url},
                }
            },
        ) from exc

    return DownloadResponse(**result)


@app.get("/info", response_model=VideoInfoResponse)
async def get_video_info(url: str = Query(..., description="Media URL")) -> VideoInfoResponse:
    """Return the media metadata without importing anything."""
    try:
        downloader = MediaDownloader()
        info = await asyncio.to_thread(downloader.get_video_info, url)
    except DownloadError as exc:
        logger.warning("info_request_failed", url=url, error=str(exc))
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "INFO_FAILED",
                    "message": str(exc),
                    "details": {"url": url},
                }
            },
        ) from exc

    return VideoInfoResponse(
        title=info["title"],
        artist=info["artist"],
        duration_ms=info["duration_ms"],
        thumbnail=info["thumbnail"],
        video_id=info["video_id"],
    )
