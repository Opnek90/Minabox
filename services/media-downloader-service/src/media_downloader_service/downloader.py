"""Media import back end: reads a media URL and writes an MP3 with metadata.

Only the URL is passed through to yt-dlp. The wrapper deliberately builds its
option dict from scratch for every call, so no credential, cookie, session or
key material can reach the extractor through this service.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
import yt_dlp
from mutagen.id3 import APIC, ID3, ID3NoHeaderError

logger = structlog.get_logger("media_downloader_service.downloader")

# Extractor defaults for a single site whose default client selection tends to
# break metadata reads. This picks between clients the extractor already offers
# for openly readable media; it supplies no credentials and unlocks nothing that
# is otherwise restricted.
_YT_EXTRACTOR_ARGS: dict[str, Any] = {
    "youtube": {
        "player_client": ["web_creator", "android"],
    }
}

# The stage names reported through on_progress / GET /download/progress/{job_id}.
STAGE_FETCHING_INFO = "fetching_info"
STAGE_DOWNLOADING = "downloading"
STAGE_CONVERTING = "converting"
STAGE_FINALIZING = "finalizing"

OnProgress = Callable[[str, float | None], None]

# d["postprocessor"] in a postprocessor_hooks callback is each PP's
# pp_key(), not its class name - e.g. FFmpegExtractAudioPP reports
# "ExtractAudio", FFmpegMetadataPP reports "Metadata" (verified against the
# installed yt-dlp package - see test_postprocessor_hook_names_match_the_
# real_yt_dlp_classes, which pulls the real values rather than hardcoding a
# second, previously-wrong, copy of this mapping).
_POSTPROCESSOR_STAGES: dict[str, str] = {
    "ExtractAudio": STAGE_CONVERTING,
    "EmbedThumbnail": STAGE_FINALIZING,
    "Metadata": STAGE_FINALIZING,
}


def postprocessor_stage_for(pp_key: str) -> str | None:
    """The STAGE_* this service reports for a given postprocessor, or None."""
    return _POSTPROCESSOR_STAGES.get(pp_key)


class DownloadError(Exception):
    """Raised when a download or metadata operation fails."""


class _YtDlpLogger:
    """Routes yt-dlp's own text output through structlog.

    Without this, yt-dlp prints its progress bar and any debug/warning text
    straight to stdout as plain lines, interleaved with this service's own
    structured JSON log lines - two different formats in the same stream.
    `noprogress` below silences the (now redundant, see progress_hooks)
    percentage spam; this catches everything else yt-dlp would otherwise
    print itself.

    The extra field is named "text", not "message": the WebUI's log viewer
    (ServiceLogsModal.tsx) treats "message"/"msg" as alternate spellings of
    "event" and drops them from the displayed data, on the assumption that
    every other structlog call in this codebase puts the actual content in
    the event itself (e.g. logger.warning("api_domain_not_allowed",
    hostname=...)) rather than behind a generic event name plus a duplicate
    "message" field - which is what this class did at first, and which made
    every yt-dlp warning show up with nothing in its data column.
    """

    def debug(self, msg: str) -> None:
        logger.debug("yt_dlp_message", text=msg)

    def info(self, msg: str) -> None:
        logger.debug("yt_dlp_message", text=msg)

    def warning(self, msg: str) -> None:
        logger.warning("yt_dlp_warning", text=msg)

    def error(self, msg: str) -> None:
        logger.error("yt_dlp_error", text=msg)


class MediaDownloader:
    """Reads a media URL via yt-dlp and embeds the metadata into the MP3."""

    def __init__(self, audio_quality: str = "192", max_filesize_mb: int = 200) -> None:
        self.audio_quality = audio_quality
        self.max_filesize_mb = max_filesize_mb

    def download_video(
        self, url: str, output_dir: Path, on_progress: OnProgress | None = None
    ) -> dict[str, Any]:
        """Download audio from *url* as ``audio.mp3`` into *output_dir*.

        The caller is responsible for creating an appropriate output_dir
        (e.g. ``tracks/<track_id>/``) so the file layout stays consistent
        with manually uploaded tracks.

        *on_progress*, if given, is called from yt-dlp's own hook threads with
        a stage name (see the STAGE_* constants) and, while downloading, a
        percentage - real numbers straight from yt-dlp, not a simulated
        stepper, so a stalled or restarted download shows up as such.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Stage transitions and, while downloading, 25% milestones go to the
        # log too - not just on_progress()/the polling endpoint - so someone
        # watching the log (rather than the WebUI) can also see what a
        # multi-minute import is doing instead of silence between
        # yt_dlp_warning lines and the final download_complete.
        last_stage: str | None = None
        last_percent_milestone = -1

        def report(stage: str, percent: float | None = None) -> None:
            nonlocal last_stage, last_percent_milestone
            if stage != last_stage:
                last_stage = stage
                last_percent_milestone = -1
                logger.info("download_stage", stage=stage)
            elif stage == STAGE_DOWNLOADING and percent is not None:
                milestone = int(percent // 25) * 25
                if milestone > last_percent_milestone:
                    last_percent_milestone = milestone
                    logger.info("download_stage", stage=stage, percent=milestone)
            if on_progress is not None:
                on_progress(stage, percent)

        def progress_hook(d: dict[str, Any]) -> None:
            if d.get("status") != "downloading":
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")
            percent = 100.0 * downloaded / total if total and downloaded is not None else None
            report(STAGE_DOWNLOADING, percent)

        def postprocessor_hook(d: dict[str, Any]) -> None:
            if d.get("status") != "started":
                return
            stage = postprocessor_stage_for(d.get("postprocessor", ""))
            if stage is not None:
                report(stage)

        report(STAGE_FETCHING_INFO)

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
            "outtmpl": str(output_dir / "audio.%(ext)s"),
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _YtDlpLogger(),
            "extractor_args": _YT_EXTRACTOR_ARGS,
            "max_filesize": self.max_filesize_mb * 1024 * 1024,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info: dict[str, Any] = ydl.extract_info(url, download=True)  # type: ignore[assignment]
        except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
            logger.error("yt_dlp_download_failed", url=url, error=str(exc))
            raise DownloadError(f"Download failed: {exc}") from exc

        video_id: str = info.get("id", "unknown")
        mp3_path = output_dir / "audio.mp3"

        if not mp3_path.exists():
            raise DownloadError(f"Expected MP3 not found after download: {mp3_path}")

        thumbnail_embedded = self._embed_thumbnail_fallback(mp3_path, output_dir)

        # Best-quality thumbnail URL from yt-dlp: info["thumbnails"] is sorted
        # ascending by preference (worst first), so the best one is the last
        # entry. Fall back to the top-level "thumbnail" field if the list is
        # absent or empty.
        thumbnail_url: str = ""
        thumbnails = info.get("thumbnails")
        if thumbnails and isinstance(thumbnails, list):
            thumbnail_url = thumbnails[-1].get("url", "") or ""
        if not thumbnail_url:
            thumbnail_url = info.get("thumbnail", "") or ""

        result: dict[str, Any] = {
            "file_path": str(mp3_path),
            "title": info.get("title", "Unknown Title"),
            "artist": info.get("uploader") or info.get("channel") or "Unknown Artist",
            "album": "Downloads",
            # info["duration"] is present but None for livestreams and some
            # extractors, so `.get(key, default)` alone would still crash.
            "duration_ms": int((info.get("duration") or 0) * 1000),
            "video_id": video_id,
            "thumbnail": thumbnail_url,
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
        """Fetch the media metadata *without* importing anything."""
        ydl_opts: dict[str, Any] = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "logger": _YtDlpLogger(),
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
            "duration_ms": int((info.get("duration") or 0) * 1000),
            "thumbnail": info.get("thumbnail", ""),
            "video_id": info.get("id", "unknown"),
        }

    def _embed_thumbnail_fallback(self, mp3_path: Path, output_dir: Path) -> bool:
        """Embed leftover thumbnail as APIC cover art (fallback if EmbedThumbnail PP failed)."""
        thumbnail_path: Path | None = None
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = output_dir / f"audio.{ext}"
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
                audio["APIC"] = APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img.read())
            audio.save(str(mp3_path))
            thumbnail_path.unlink()
            logger.debug("thumbnail_embedded_fallback", path=str(mp3_path))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("thumbnail_embed_failed", path=str(mp3_path), error=str(exc))
            return False
