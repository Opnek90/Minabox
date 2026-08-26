# Media Downloader Service – Architecture

## 1. Purpose & Responsibility

The media downloader service is a standalone microservice for local media
import: it reads the audio track of a given media URL, converts it to an MP3
file, and stores it in the shared audio storage. It is called exclusively by
the backend – the WebUI client never talks to it directly.

**Goals:**

- A simple REST API for the backend (`GET /info`, `POST /download`)
- Isolating the read/convert tooling (yt-dlp, ffmpeg) in its own container
- No support for credentials, cookies, sessions or decryption key material –
  and therefore no built-in way to bypass access or protection mechanisms
  (see section 8)

The service does not use MQTT and has no database, deliberately, so it stays
easy to extract as a standalone Python package later. The actual `yt-dlp`/
`ffmpeg` work runs via `asyncio.to_thread`, one download at a time
(`asyncio.Semaphore(1)`) – ffmpeg is CPU-heavy and this runs on a Raspberry
Pi, so a second concurrent conversion would fight the first for the same
cores rather than genuinely run in parallel. This also keeps `GET /health`
answering while a download is in progress – see the
[Go-Live review](GoLive-Review.md#1-functional-defects) for what it looked
like before.

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.13 |
| Web framework | FastAPI + Uvicorn |
| Downloader | yt-dlp (updated frequently) |
| Conversion | ffmpeg (Debian package) |
| Container | Docker, `python:3.13-slim` (Debian), multi-stage build |

---

## 3. API Endpoints

Two different services expose endpoints in this flow. The table below is the
media downloader's own API – the one this document describes. The backend's
public API (`GET /api/v1/tracks/validate-url`, `POST /api/v1/tracks/from-url`)
is a separate, thin proxy documented in `backend-service`.

### `GET /health`

Docker health check.

**Response:** `{"status": "healthy", "service": "media-downloader-service", "version": "...", "uptime_seconds": ...}`

---

### `GET /info?url=<url>`

Reads the media metadata without starting an import.

| Parameter | Required | Description |
|---|---|---|
| `url` | ✓ | The media URL to inspect |

**Response (200):**

```json
{
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail": "https://example.org/media/cover.jpg",
  "video_id": "abc123"
}
```

**Errors:**

- `422` – URL invalid or the media could not be read

---

### `POST /download`

Reads the media, stores the audio track as `audio.mp3` under the given
`output_dir` (or `AUDIO_TRACKS_DIR` if omitted), and returns its metadata.

**Request body:**

```json
{ "url": "https://example.org/media", "output_dir": "/mnt/audio/tracks/42" }
```

**Response (201):**

```json
{
  "file_path": "/mnt/audio/tracks/42/audio.mp3",
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "album": "Downloads",
  "duration_ms": 1980000,
  "video_id": "abc123",
  "thumbnail_embedded": true
}
```

**Errors:**

- `422` – import failed (`DOWNLOAD_FAILED`)

The domain allow-list is enforced by the backend, before it ever calls this
service – see section 8. The file size limit (`max_filesize`, from
`MAX_FILESIZE_MB`) is enforced here, inside the `yt-dlp` call itself.

> `video_id` is the identifier assigned by the source. The field name is from
> the first version of the API and stays for compatibility.

---

## 4. Retry Logic

The backend's `MediaDownloaderClient` implements automatic retries for both
endpoints (`/download` and `/info`):

- **Max. attempts:** 3 (`_MAX_RETRIES = 3`)
- **Backoff:** linear – `2 * attempt` seconds between attempts (2 s, 4 s)
- **Retryable errors:** HTTP 5xx, `httpx.TimeoutException`, `httpx.RequestError`
- **Not retryable:** HTTP 4xx (e.g. invalid URL) – fails immediately
- **Logging:** every retry attempt is logged as a warning via `structlog`
  (`media_downloader_download_5xx_retry`, `media_downloader_download_transient_retry`)

The logic lives in
`services/backend-service/src/backend_service/infrastructure/media_downloader_client.py`.

---

## 5. Cover Art

Two independent fallback chains exist, one in each service:

1. **In this service (`downloader.py`):** yt-dlp's `EmbedThumbnail`
   postprocessor embeds the cover into the MP3 during conversion. If that step
   left a stray thumbnail file behind, `_embed_thumbnail_fallback()` embeds it
   manually via `mutagen` as an ID3 `APIC` frame and reports whether the MP3
   ends up with cover art (`thumbnail_embedded` in the response).
2. **In the backend (`routes_tracks.py`):** after a successful download, the
   backend tries to resolve a cover for the track regardless of what the
   downloader reported:
   1. **Primary – embedded cover:** `_extract_cover_art()` reads an embedded
      APIC frame (MP3/ID3) or `pictures` (FLAC/OGG) from the downloaded file
      with `mutagen`.
   2. **Fallback – remote thumbnail:** if no embedded cover is found,
      `_download_thumbnail()` fetches the `thumbnail` URL from the
      media downloader's response asynchronously via `httpx`.
   3. The cover is stored as `STATIC_DIR/covers/track_{id}.jpg|.png` and
      written to `cover_art_url` on the track's DB row.

**Filesystem layout after a download:**

```
/mnt/audio/
  tracks/
    {track_id}/
      audio.mp3

/data/static/
  covers/
    track_{track_id}.jpg   ← cover art (embedded, or the thumbnail fallback)
```

Cover download errors are not critical and are only logged as warnings
(`track_cover_extract_failed`, `track_thumbnail_download_failed`) – a failed
cover fetch never fails the track import.

---

## 6. Environment Variables

Read by this service (`config.py`):

| Variable | Default | Description |
|---|---|---|
| `AUDIO_TRACKS_DIR` | `/mnt/audio/tracks/downloads` | Default target directory for MP3 files, used only when the caller omits `output_dir` |
| `AUDIO_BASE_DIR` | `/mnt/audio` | Shared audio volume mount point; `output_dir` must resolve inside it – anything else is rejected with `422` |
| `AUDIO_QUALITY` | `192` | MP3 bitrate in kbps |
| `MAX_FILESIZE_MB` | `200` | Wired into `yt-dlp`'s own `max_filesize` option; a download exceeding it fails with `422` |
| `LOG_LEVEL` | `INFO` | Filters log output and switches the renderer (`DEBUG` -> human-readable console, otherwise structured JSON) |

The domain allow-list is **not** configured on this container – it lives
entirely in the backend, is user-editable (Admin UI -> General -> media
import), and is enforced before the backend ever calls this service. See
section 8.

No other variables exist, deliberately – in particular none for credentials
or cookies (see section 8).

---

## 7. Data Flow

```
WebUI
  │
  │  POST /api/v1/tracks/from-url?url=...  →  HTTP 202 (immediately)
  ▼
Backend
  │  (background task)
  │  POST http://media-downloader:8007/download  {"url": ..., "output_dir": ...}
  │  └─ retries up to 3× on 5xx/timeout
  ▼
Media Downloader
  │
  │  yt-dlp → ffmpeg → MP3
  ▼
/mnt/audio/tracks/{track_id}/audio.mp3
  │
  │  Backend: mutagen → extract cover from ID3
  │  (fallback: download thumbnail_url via httpx)
  │  → /data/static/covers/track_{id}.jpg
  │
  │  Backend registers the track in SQLite (title, artist, cover_art_url)
  ▼
WebUI: polls GET /tracks/{id}/download-status until status is "done"
```

---

## 8. Security and Usage Limits

- **Lawful use:** import is only permitted if the user holds the necessary
  usage and reproduction rights, or a statutory exception applies. Neither
  this service nor the backend can verify that for a given URL – see
  `README.md`.
- **Domain allow-list:** only explicitly allowed hosts can be used. The list
  is user-editable in the backend (Admin UI -> General -> media import,
  `core/media_settings.py`), read fresh on every request, and defaults to
  SoundCloud and Bandcamp only – **not** YouTube: unlike the other two,
  YouTube has no built-in download feature a rights holder opts into, which
  makes importing from it a meaningfully bigger legal question. This is a
  technical guard against arbitrary fetch targets, not a legal clearance of
  the content hosted there. It is enforced by the backend only – this
  service accepts any URL it is given, so reaching it directly (see below)
  bypasses the check.
- **File size limit:** `MAX_FILESIZE_MB` (default 200) is enforced here via
  `yt-dlp`'s own `max_filesize` option.
- **No credential parameters:** neither the API, the UI, nor any environment
  variable offers fields for cookie files, browser cookies, login
  credentials, OAuth, session tokens, or decryption keys. Only the URL (and
  optionally the target directory) reaches yt-dlp; the option dict is built
  from scratch on every call in code and cannot be extended from outside.
- **No circumvention features:** the project implements and documents no
  support for bypassing DRM, paywalls, geoblocking, or comparable access
  restrictions. The underlying library may have its own capabilities; which
  protection mechanisms apply in a given case is not something this project
  evaluates.
- **No authentication on the API itself:** this service trusts whoever can
  reach it on the Docker network or the bound host port. See section 9 for
  where that port is exposed.
- **User confirmation:** the WebUI shows a lawful-use notice before every
  import and requires explicit user confirmation before a check or import can
  start. The confirmation is held only in UI state and not persisted.

---

## 9. Docker Integration

The service is defined as `media-downloader` in `docker-compose.yml`:

- **Port:** `8007` (internal), bound on the host to `127.0.0.1:8007` only –
  the download API has no authentication of its own.
- **Volume:** shares `/mnt/audio` with the backend and the audio service.
- **depends_on:** backend (healthy).
- **Optional `.env` variable:** `MEDIA_DOWNLOADER_MAX_FILESIZE_MB`. The
  allowed-domains list is not a `.env` setting – it is configured in the
  WebUI and stored in `general_settings.json` (backend), see section 8.
