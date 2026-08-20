"""FastAPI application entry point for the Media Downloader Service."""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
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

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger("media_downloader_service")

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
    version=os.environ.get("APP_VERSION", "0.0.0-dev"),
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        {
            "status": "healthy",
            "service": "media-downloader-service",
            # Dieser Dienst bindet shared-lib nicht ein; die Variable setzt der
            # Dockerfile aus dem Build-Arg (docs/Versionierung.md).
            "version": os.environ.get("APP_VERSION", "0.0.0-dev"),
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
        }
    )


@app.post("/download", response_model=DownloadResponse, status_code=201)
async def download_video(request: DownloadRequest) -> DownloadResponse:
    """Download a video URL as MP3.

    If *output_dir* is provided the MP3 is placed there; otherwise the
    service default (AUDIO_TRACKS_DIR) is used.
    """
    output_dir = Path(request.output_dir) if request.output_dir else config.audio_tracks_dir
    downloader = MediaDownloader(audio_quality=config.audio_quality)
    try:
        result = downloader.download_video(request.url, output_dir)
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
    """Return video metadata without downloading."""
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
