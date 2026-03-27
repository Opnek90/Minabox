"""yt-dlp wrapper for audio extraction with metadata embedding."""

from pathlib import Path
from typing import Any

import structlog
import yt_dlp
from mutagen.id3 import APIC, ID3, ID3NoHeaderError

logger = structlog.get_logger("media_downloader_service.downloader")

# yt-dlp extractor args to reduce YouTube bot-detection false positives.
# The android client is less aggressively rate-limited than the web client.
_YT_EXTRACTOR_ARGS: dict[str, Any] = {
    "youtube": {
        "player_client": ["web_creator", "android"],
    }
}


class DownloadError(Exception):
    """Raised when a download or metadata operation fails."""


class MediaDownloader:
    """Handles yt-dlp downloads and MP3 metadata embedding."""

    def __init__(self, audio_quality: str = "192") -> None:
        self.audio_quality = audio_quality

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download_video(self, url: str, output_base_dir: Path) -> dict[str, Any]:
        """Download audio from *url* as MP3 into a per-video subdirectory.

        Each download is stored as::

            <output_base_dir>/<video_id>/audio.mp3

        This mirrors the upload endpoint's layout of
        ``tracks/<track_id>/original.mp3``.

        Returns:
            Dict with file_path, title, artist, album, duration_ms,
            video_id, thumbnail_embedded.
        """
        # First pass: extract info only to get the video_id so we can create
        # the per-video directory before the actual download.
        info_opts: dict[str, Any] = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }
        try:
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                pre_info: dict[str, Any] = ydl.extract_info(url, download=False)  # type: ignore[assignment]
        except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
            logger.error("yt_dlp_prefetch_failed", url=url, error=str(exc))
            raise DownloadError(f"Metadata prefetch failed: {exc}") from exc

        video_id: str = pre_info.get("id", "unknown")
        output_dir = output_base_dir / video_id
        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.audio_quality,
                },
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            # Save as audio.mp3 inside the per-video folder
            "outtmpl": str(output_dir / "audio.%(ext)s"),
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info: dict[str, Any] = ydl.extract_info(url, download=True)  # type: ignore[assignment]
        except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
            logger.error("yt_dlp_download_failed", url=url, error=str(exc))
            raise DownloadError(f"Download failed: {exc}") from exc

        mp3_path = output_dir / "audio.mp3"

        if not mp3_path.exists():
            raise DownloadError(f"Expected MP3 not found after download: {mp3_path}")

        thumbnail_embedded = self._embed_thumbnail_fallback(mp3_path, output_dir, "audio")

        result: dict[str, Any] = {
            "file_path": str(mp3_path),
            "title": info.get("title", "Unknown Title"),
            "artist": info.get("uploader") or info.get("channel") or "Unknown Artist",
            "album": "Downloads",
            "duration_ms": int(info.get("duration", 0) * 1000),
            "video_id": video_id,
            "thumbnail_embedded": thumbnail_embedded,
        }

        logger.info(
            "download_complete",
            video_id=video_id,
            title=result["title"],
            file_path=result["file_path"],
        )
        return result

    def get_video_info(self, url: str) -> dict[str, Any]:
        """Fetch video metadata *without* downloading.

        Returns:
            Dict with title, artist, duration_ms, thumbnail, video_id.
        """
        ydl_opts: dict[str, Any] = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info: dict[str, Any] = ydl.extract_info(url, download=False)  # type: ignore[assignment]
        except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
            logger.error("yt_dlp_info_failed", url=url, error=str(exc))
            raise DownloadError(f"Metadata extraction failed: {exc}") from exc

        return {
            "title": info.get("title", "Unknown Title"),
            "artist": info.get("uploader") or info.get("channel") or "Unknown Artist",
            "duration_ms": int(info.get("duration", 0) * 1000),
            "thumbnail": info.get("thumbnail", ""),
            "video_id": info.get("id", "unknown"),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed_thumbnail_fallback(
        self,
        mp3_path: Path,
        output_dir: Path,
        stem: str,
    ) -> bool:
        """Try to embed a leftover thumbnail file as APIC cover art."""
        thumbnail_path: Path | None = None
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = output_dir / f"{stem}.{ext}"
            if candidate.exists():
                thumbnail_path = candidate
                break

        if thumbnail_path is None:
            return True

        try:
            try:
                audio = ID3(mp3_path)
            except ID3NoHeaderError:
                audio = ID3()

            mime = "image/jpeg" if thumbnail_path.suffix in (".jpg", ".jpeg") else "image/png"
            with open(thumbnail_path, "rb") as img:
                audio["APIC"] = APIC(
                    encoding=3,
                    mime=mime,
                    type=3,
                    desc="Cover",
                    data=img.read(),
                )
            audio.save(str(mp3_path))
            thumbnail_path.unlink()
            logger.debug("thumbnail_embedded_fallback", video_id=stem)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("thumbnail_embed_failed", video_id=stem, error=str(exc))
            return False
