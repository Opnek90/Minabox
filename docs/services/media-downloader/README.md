# Media Downloader Service

A standalone microservice for local media import: it reads the audio track of a
given media URL, converts it to MP3, and stores it in the shared audio volume.
The backend is its only caller — the WebUI never talks to it directly.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-media-downloader` |
| Source | `services/media-downloader-service/src/media_downloader_service/` |
| Version | `services/media-downloader-service/VERSION` |
| Compose service | `media-downloader` (profile `media`) |
| Runtime | Python 3.13, FastAPI/Uvicorn, yt-dlp + ffmpeg |
| Speaks | REST only, on port `8007` (host `127.0.0.1:8007`). **No MQTT** |
| Needs | the shared `/mnt/audio` volume; nothing else |

## 1. Purpose & Responsibility

- A simple REST API for the backend: `GET /info`, `POST /download`.
- Isolate the read/convert tooling (yt-dlp, ffmpeg) in its own container.
- Offer **no** support for credentials, cookies, sessions or decryption key
  material — and therefore no built-in way to bypass access or protection
  mechanisms (section 7.1).

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| The domain allow-list | backend, user-editable in the WebUI; enforced **before** this service is called |
| Cover-art resolution for the track record | backend (`routes_tracks.py`) — this service only embeds what yt-dlp produced |
| Knowing about tracks, playlists or the database | backend |
| Retrying a failed call | backend (`MediaDownloaderClient`) |
| MQTT of any kind | — deliberately absent |

**No MQTT and no database is an architectural decision**, so the service stays
easy to extract as a standalone Python package later. That is also why the
domain allow-list is not here: this service accepts any URL it is given.

## 2. File & Folder Structure

```
services/media-downloader-service/
├── Dockerfile              multi-stage python:3.13-slim; ffmpeg in the runtime stage
├── requirements.txt        fastapi, uvicorn, yt-dlp, mutagen, structlog
├── VERSION                 service version, single source
├── src/media_downloader_service/
│   ├── main.py             ** the API ** — the four routes, the semaphore,
│   │                       the job-progress registry
│   ├── downloader.py       ** the work ** — the yt-dlp option dict, the
│   │                       progress hooks, the thumbnail embed fallback
│   ├── models.py           request/response models
│   └── config.py           the five environment variables
└── tests/
    ├── test_main.py        the routes, including output_dir containment
    ├── test_downloader.py  option building, progress hooks, cover fallback
    ├── test_models.py      request/response validation
    └── test_config.py      environment defaults
```

## 3. Runtime Flow

```
WebUI
  │  POST /api/v1/tracks/from-url?url=...  →  HTTP 202 (immediately)
  ▼
Backend  (background task)
  │  POST http://media-downloader:8007/download  {"url": ..., "output_dir": ..., "job_id": ...}
  │  └─ retries up to 3× on 5xx/timeout
  ▼
Media Downloader
  │  yt-dlp → ffmpeg → MP3, cover embedded during conversion
  ▼
/mnt/audio/tracks/{track_id}/audio.mp3
  │
  │  Backend: mutagen → extract cover from ID3
  │  (fallback: download `thumbnail` via httpx)
  │  → /data/static/covers/track_{id}.jpg
  │
  │  Backend registers the track in SQLite (title, artist, cover_art_url)
  ▼
WebUI: polls GET /tracks/{id}/download-status until status is "done"
```

**One download at a time.** The yt-dlp/ffmpeg work runs through
`asyncio.to_thread` behind an `asyncio.Semaphore(1)`. ffmpeg is CPU-heavy and
this runs on a Raspberry Pi, so a second concurrent conversion would fight the
first for the same cores rather than genuinely run in parallel. It also keeps
`GET /health` answering while a download is in progress — and it means at most
one `job_id` is ever tracked.

**Retries live in the backend**, not here:
`backend_service/infrastructure/media_downloader_client.py` retries up to three
times with linear backoff (2 s, 4 s) on HTTP 5xx, `httpx.TimeoutException` and
`httpx.RequestError`. HTTP 4xx — an invalid URL — fails immediately. Every
attempt is logged (`media_downloader_download_5xx_retry`,
`media_downloader_download_transient_retry`).

## 4. Public Interfaces

REST only. Two different services expose endpoints in this flow: the table
below is this service's own API. The backend's public API
(`GET /api/v1/tracks/validate-url`, `POST /api/v1/tracks/from-url`) is a
separate, thin proxy documented with the backend.

### 4.1 REST

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Docker health check |
| `GET` | `/info?url=<url>` | metadata without importing |
| `POST` | `/download` | import the audio track |
| `GET` | `/download/progress/{job_id}` | stage of a running import |

**`GET /health`**

```json
{ "status": "healthy", "service": "media-downloader-service", "version": "...", "uptime_seconds": 1234 }
```

**`GET /info?url=<url>`** — 200, or 422 when the URL is invalid or the media
cannot be read.

```json
{
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail": "https://example.org/media/cover.jpg",
  "video_id": "abc123"
}
```

**`POST /download`** — stores the audio track as `audio.mp3` under
`output_dir` (or `AUDIO_TRACKS_DIR` when omitted) and returns its metadata.
`job_id` is optional; with it, `/download/progress/{job_id}` can be polled on a
separate connection while this request is in flight.

```json
{ "url": "https://example.org/media", "output_dir": "/mnt/audio/tracks/42", "job_id": "42" }
```

201:

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

422 (`DOWNLOAD_FAILED`) when the import fails, when `output_dir` does not
resolve inside `AUDIO_BASE_DIR`, or when the download exceeds
`MAX_FILESIZE_MB` — that limit is enforced here, inside the yt-dlp call itself.

> `video_id` is the identifier assigned by the source. The field name is from
> the first version of the API and stays for compatibility.

**`GET /download/progress/{job_id}`** — the stage of a download started with a
matching `job_id`, straight from yt-dlp's own `progress_hooks` and
`postprocessor_hooks`. Not a simulated timer, so a stalled or restarted
download shows up as such.

```json
{ "stage": "downloading", "percent": 42.3 }
```

`stage` is one of `fetching_info`, `downloading`, `converting`, `finalizing`,
`done`. `done` is also reported for any `job_id` not currently tracked — either
it finished, or the `/download` request never set one. `percent` is only
meaningful while `stage` is `downloading` and `null` otherwise. The backend
adds one further stage of its own, `saving`, for the DB write and cover-art
resolution that happen after this service returns (`routes_tracks.py`).

## 5. Configuration

Environment only — no config file.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIO_TRACKS_DIR` | `/mnt/audio/tracks/downloads` | default target directory, used only when the caller omits `output_dir`. Compose sets `/mnt/audio/tracks` |
| `AUDIO_BASE_DIR` | `/mnt/audio` | shared audio mount; `output_dir` must resolve inside it, anything else is rejected with 422 |
| `AUDIO_QUALITY` | `192` | MP3 bitrate in kbps |
| `MAX_FILESIZE_MB` | `200` | wired into yt-dlp's `max_filesize`; compose maps `MEDIA_DOWNLOADER_MAX_FILESIZE_MB` |
| `LOG_LEVEL` | `INFO` | filters output and switches the renderer (DEBUG → console, otherwise JSON) |

**No other variables exist, deliberately** — in particular none for credentials
or cookies (7.1). The domain allow-list is not configured on this container: it
lives in the backend, is user-editable (Admin → General → media import) and is
read fresh on every request.

Compose: profile `media`, port `8007` bound to `127.0.0.1` only (the whole
download API is unauthenticated, not just `/health`), the shared
`${AUDIO_FILES_PATH}:/mnt/audio` volume, `depends_on: backend (healthy)`.

## 6. Dependencies

**System.** `ffmpeg`, installed in the runtime stage.

**Python.** `yt-dlp` (the read/extraction library, updated frequently),
`mutagen` (ID3 manipulation, the cover fallback), FastAPI + uvicorn,
`structlog`. **Not** shared-lib — this service is deliberately free of the
common Minabox packages so it can be extracted later.

**Volume.** `/mnt/audio` must be shared with the `backend` and `audio`
services; the backend reads back what this service wrote.

**Backend.** The only caller. It enforces the allow-list, supplies
`output_dir`, retries, and does the cover and database work afterwards.

### 6.1 Cover art

Two independent fallback chains exist, one in each service:

1. **Here (`downloader.py`):** yt-dlp's `EmbedThumbnail` postprocessor embeds
   the cover into the MP3 during conversion. If that step left a stray
   thumbnail file behind, `_embed_thumbnail_fallback()` embeds it manually via
   `mutagen` as an ID3 `APIC` frame. The response reports the outcome as
   `thumbnail_embedded`.
2. **In the backend (`routes_tracks.py`):** after a successful download the
   backend resolves a cover regardless of what this service reported —
   `_extract_cover_art()` reads an embedded APIC (MP3/ID3) or `pictures`
   (FLAC/OGG) frame; failing that, `_download_thumbnail()` fetches the
   `thumbnail` URL over httpx. The result is stored as
   `STATIC_DIR/covers/track_{id}.jpg|.png` and written to `cover_art_url`.

Cover failures are warnings only (`track_cover_extract_failed`,
`track_thumbnail_download_failed`) — a failed cover fetch never fails the
import.

## 7. Errors, Health & Logging

`GET /health` reports `healthy` plus uptime; it has no dependencies to be
degraded by. The Docker health check calls it every 30 s.

Failures surface as HTTP status codes, not as states: `422` with
`DOWNLOAD_FAILED` covers an unreadable URL, a rejected `output_dir`, and a file
over the size limit. There is no partial-success path — either an MP3 exists at
the returned path, or the call failed.

Logging is structlog: DEBUG renders human-readable, everything else JSON.

### 7.1 Security and usage limits

- **Lawful use.** Import is only permitted if the user holds the necessary
  usage and reproduction rights, or a statutory exception applies. Neither this
  service nor the backend can verify that for a given URL.
- **Domain allow-list.** Only explicitly allowed hosts can be used. The list is
  user-editable in the backend (Admin → General → media import,
  `core/media_settings.py`), read fresh on every request, and defaults to
  SoundCloud and Bandcamp only — **not** YouTube: unlike the other two, YouTube
  has no built-in download feature a rights holder opts into, which makes
  importing from it a meaningfully bigger legal question. This is a technical
  guard against arbitrary fetch targets, not a legal clearance of the content
  hosted there. **It is enforced by the backend only** — this service accepts
  any URL it is given, so reaching it directly bypasses the check. That is why
  its port is bound to loopback.
- **File size limit.** `MAX_FILESIZE_MB` (default 200), enforced here through
  yt-dlp's own `max_filesize`.
- **No credential parameters.** Neither the API, the UI, nor any environment
  variable offers fields for cookie files, browser cookies, login credentials,
  OAuth, session tokens or decryption keys. Only the URL (and optionally the
  target directory) reaches yt-dlp; the option dict is built from scratch on
  every call in code and cannot be extended from outside.
- **No circumvention features.** The project implements and documents no
  support for bypassing DRM, paywalls, geoblocking or comparable access
  restrictions. The underlying library may have its own capabilities; which
  protection mechanisms apply in a given case is not something this project
  evaluates.
- **No authentication on the API itself.** This service trusts whoever can
  reach it on the Docker network or the bound host port.
- **User confirmation.** The WebUI shows a lawful-use notice before every
  import and requires explicit confirmation before a check or import can start.
  The confirmation is held in UI state only and not persisted.

## 8. Development & Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/media-downloader-service/tests -q
```

| File | Covers |
| --- | --- |
| `test_main.py` | the four routes, the `output_dir` containment check, error mapping |
| `test_downloader.py` | the yt-dlp option dict, progress hooks, the thumbnail embed fallback |
| `test_models.py` | request/response validation |
| `test_config.py` | environment defaults |

No network access and no ffmpeg are involved — yt-dlp is stubbed.

```bash
.venv/bin/ruff check services/media-downloader-service
```

```bash
./scripts/build-local.sh media-downloader
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| change output format or bitrate | `downloader.py` (the yt-dlp option dict) | `AUDIO_QUALITY` in `config.py`, the backend's expectation of `audio.mp3`, the audio service's supported formats |
| add a response field | `models.py` | `downloader.py` to fill it, the backend's `MediaDownloaderClient`, section 4.1 |
| add a progress stage | the hooks in `downloader.py` | the `stage` list in 4.1, the WebUI's progress display, the backend's own `saving` stage |
| allow concurrent downloads | the semaphore in `main.py` | measure on a Pi first; the job-progress registry assumes one job |
| add an environment variable | `config.py` | `docker-compose.yml`, the table in 5 — and check 7.1 first: this service takes no credentials by design |
| change the allow-list | **not here** — `backend_service/core/media_settings.py` | the WebUI admin page |
| add retry behaviour | **not here** — `backend_service/infrastructure/media_downloader_client.py` | section 3 |

### Invariants

- **No credentials, cookies, tokens or keys — ever.** The option dict is built
  from scratch in code on every call and must stay unreachable from outside.
  This is the project's position, not an oversight to be fixed.
- **No MQTT, no database, no shared-lib.** The isolation is what keeps this
  service extractable; adding any of them is a design change, not a feature.
- **`output_dir` must resolve inside `AUDIO_BASE_DIR`.** It is the only thing
  standing between a caller and an arbitrary write on the volume.
- **The port stays bound to loopback.** The API is unauthenticated and does not
  enforce the allow-list; exposing it would bypass the backend's only guard.
- **One download at a time.** The semaphore is a Raspberry Pi decision, and the
  progress registry depends on it.
- **The backend owns retries and cover resolution.** Duplicating either here
  would create two behaviours to keep in step.

## 10. Related Documents

- [`services/media-downloader-service/README.md`](../../../services/media-downloader-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/backend/README.md`](../backend/README.md) — the only caller: allow-list, retries, cover art, track records
- [`docs/services/webui/README.md`](../webui/README.md) — the import dialog and its lawful-use notice
