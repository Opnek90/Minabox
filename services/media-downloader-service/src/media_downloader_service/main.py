"""FastAPI application entry point for the Media Downloader Service."""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

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

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger("media_downloader_service")

# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------
config = load_config()
_start_time = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
    description="Minabox microservice for yt-dlp based audio extraction",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "media-downloader-service",
            "version": "0.1.0",
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
        }
    )


@app.post("/download", response_model=DownloadResponse, status_code=201)
async def download_video(request: DownloadRequest) -> DownloadResponse:
    """Download a video URL as MP3 with embedded metadata.

    The MP3 is saved to *AUDIO_TRACKS_DIR* and the metadata is returned
    so the backend-service can create a Track DB entry.
    """
    downloader = MediaDownloader(audio_quality=config.audio_quality)
    try:
        result = downloader.download_video(request.url, config.audio_tracks_dir)
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
async def get_video_info(url: str = Query(..., description="Video URL")) -> VideoInfoResponse:
    """Return video metadata without downloading.

    Used by the frontend for a preview before the user confirms the import.
    """
    downloader = MediaDownloader()
    try:
        info = downloader.get_video_info(url)
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
