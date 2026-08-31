# media-downloader-service

A standalone Minabox microservice for **local media import**: it takes a media
URL and puts the audio track into the local library.

## Job

The service receives a URL from the `backend-service`, reads the audio track,
stores it technically as **MP3 (192 kbps)** in the shared audio storage, embeds
the metadata (title, artist, cover) and returns the file path and metadata. It
communicates **only via REST** with the `backend-service` - no MQTT, no direct
access from the web UI.

## Lawful media import

Import is only permitted if you hold the necessary usage and reproduction
rights or a statutory exception applies - for example your own recordings,
public domain works, or content with the explicit permission or licence of the
rights holder.

Responsibility for this rests with you as the user. Neither this service nor
the backend can check whether you hold the necessary rights for a given URL;
the domain whitelist is a technical safeguard against arbitrary fetch targets
and not a legal assessment. The project is not intended to circumvent technical
protection measures or access restrictions.

*Deutsch:* Der Import ist nur zulässig, wenn du die erforderlichen Nutzungs-
und Vervielfältigungsrechte besitzt oder eine gesetzliche Erlaubnis greift -
etwa bei eigenen Aufnahmen, gemeinfreien Werken oder Inhalten mit
ausdrücklicher Erlaubnis bzw. Lizenz des Rechteinhabers. Die Verantwortung
liegt bei dir; weder dieser Service noch das Backend können die Rechtslage
einer konkreten URL bewerten. Das Projekt ist nicht dafür bestimmt, technische
Schutzmaßnahmen oder Zugangsbeschränkungen zu umgehen.

## Technical limits

The integration only passes the URL (and optionally a target directory) on to
the download library. It offers **no** parameters, fields or environment
variables for:

- cookie files or browser cookie import
- login data, username/password, OAuth or session tokens
- decryption or licence keys
- deliberately bypassing geoblocking, paywalls or DRM

So through this API you can practically only import sources that are readable
without such details. The library used (yt-dlp) may bring further capabilities
of its own - the project does not pass those on and does not document them as a
use case. A statement about which access-protection mechanisms apply in a
particular case is something the project cannot and will not make.

## API endpoints

| Method | Path | Description |
|---------|------|--------------|
| `GET` | `/health` | health check |
| `GET` | `/info?url=<url>` | metadata without import (preview) |
| `POST` | `/download` | import the audio track, return MP3 metadata |

### POST /download

```json
// Request
{ "url": "https://example.org/media" }

// Response 201
{
  "file_path": "/mnt/audio/tracks/downloads/audio.mp3",
  "title": "Track Title",
  "artist": "Creator Name",
  "album": "Downloads",
  "duration_ms": 195000,
  "video_id": "abc123",
  "thumbnail_embedded": true
}
```

### GET /info

```json
// Response 200
{
  "title": "Track Title",
  "artist": "Creator Name",
  "duration_ms": 195000,
  "thumbnail": "https://example.org/media/cover.jpg",
  "video_id": "abc123"
}
```

> `video_id` is the identifier assigned by the source. The field name comes
> from the first version of the API and is kept for compatibility.

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|--------------|
| `AUDIO_TRACKS_DIR` | `/mnt/audio/tracks/downloads` | target directory for MP3 files, if no `output_dir` is passed |
| `AUDIO_BASE_DIR` | `/mnt/audio` | shared audio volume; `output_dir` must be inside it, otherwise `422` |
| `AUDIO_QUALITY` | `192` | MP3 bitrate in kbps |
| `MAX_FILESIZE_MB` | `200` | maximum file size of a download in MB (yt-dlp `max_filesize`) |
| `LOG_LEVEL` | `INFO` | log level |

There are deliberately no further variables - in particular none for
credentials or cookies (see *Technical limits*). The allowed domains are not an
environment variable of this service: they are managed in the backend and are
editable in the web UI under *Admin → General → media import* (default without
YouTube - see the rationale there).

## Dependencies

- **ffmpeg** (runtime dependency in the Dockerfile)
- **yt-dlp** - the read/extraction library
- **mutagen** - ID3 tag manipulation (fallback for cover art)
- **FastAPI + uvicorn** - HTTP server
- **structlog** - logging

## Shared volume

The service writes MP3 files to `/mnt/audio/tracks/downloads/`. That directory
must be shared with the `backend` service and the `audio` service (see
`docker-compose.yml`).

## Architecture decision

The service is deliberately implemented as a standalone microservice with no
MQTT dependency, so it can later be extracted as a standalone Python package.

## Questions and reports

For questions or notes about rights to importable content:
[GitHub Issues](https://github.com/Opnek90/Minabox/issues). The project does not
currently have a separate contact address.
