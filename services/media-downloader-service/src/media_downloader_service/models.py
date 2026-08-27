"""Pydantic schemas for the Media Downloader Service."""

from pydantic import BaseModel, field_validator


class DownloadRequest(BaseModel):
    """Request body for POST /download."""

    url: str
    output_dir: str | None = None  # optional: absolute path inside the container
    job_id: str | None = None  # optional: correlation id for GET /download/progress/{job_id}

    @field_validator("url")
    @classmethod
    def url_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("url must not be empty")
        return v.strip()


class VideoInfoResponse(BaseModel):
    """Response for GET /info – metadata without import."""

    title: str
    artist: str
    duration_ms: int
    thumbnail: str
    video_id: str


class DownloadResponse(BaseModel):
    """Response for POST /download – metadata of the completed import."""

    file_path: str
    title: str
    artist: str
    album: str
    duration_ms: int
    video_id: str
    thumbnail_embedded: bool


class ProgressResponse(BaseModel):
    """Response for GET /download/progress/{job_id}.

    stage: one of "fetching_info", "downloading", "converting",
    "embedding_thumbnail", "embedding_metadata", "done" - see downloader.py's
    STAGE_* constants.
    percent, speed_bytes_per_sec, eta_seconds: only meaningful while stage is
    "downloading" - straight from yt-dlp's own progress_hooks. yt-dlp reports
    no percentage for any postprocessor, so "converting" and the embedding
    stages never carry one; there is no number to give.
    """

    stage: str
    percent: float | None = None
    speed_bytes_per_sec: float | None = None
    eta_seconds: int | None = None
