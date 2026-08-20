"""Pydantic schemas for the Media Downloader Service."""

from pydantic import BaseModel, field_validator


class DownloadRequest(BaseModel):
    """Request body for POST /download."""

    url: str
    output_dir: str | None = None  # optional: absolute path inside the container

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
