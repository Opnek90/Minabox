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
    "finalizing", "done" - see downloader.py's _STAGE_* callbacks.
    percent: 0-100 while stage is "downloading"; None otherwise (the other
    stages have no natural progress fraction to report).
    """

    stage: str
    percent: float | None = None
