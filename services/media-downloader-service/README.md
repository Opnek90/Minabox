# media-downloader-service

Eigenständiger Minabox-Microservice für den Download von Audio aus Online-Videoplattformen via **yt-dlp**.

## Aufgabe

Dieser Service nimmt eine Video-URL entgegen, lädt das Audio als **MP3 (192 kbps)** herunter, bettet Metadaten (Titel, Künstler, Cover-Art) ein und gibt den Dateipfad sowie die Metadaten zurück. Er kommuniziert **nur via REST** mit dem `backend-service` – kein MQTT.

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `GET` | `/health` | Health-Check |
| `GET` | `/info?url=<url>` | Metadaten ohne Download (Preview) |
| `POST` | `/download` | Audio herunterladen, MP3 zurückgeben |

### POST /download

```json
// Request
{ "url": "https://www.youtube.com/watch?v=..." }

// Response 201
{
  "file_path": "/mnt/audio/tracks/downloads/VIDEO_ID.mp3",
  "title": "Song Title",
  "artist": "Channel Name",
  "album": "Downloads",
  "duration_ms": 195000,
  "video_id": "VIDEO_ID",
  "thumbnail_embedded": true
}
```

### GET /info

```json
// Response 200
{
  "title": "Song Title",
  "artist": "Channel Name",
  "duration_ms": 195000,
  "thumbnail": "https://i.ytimg.com/...",
  "video_id": "VIDEO_ID"
}
```

## Konfiguration (Umgebungsvariablen)

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `AUDIO_TRACKS_DIR` | `/mnt/audio/tracks/downloads` | Zielverzeichnis für MP3-Dateien |
| `AUDIO_QUALITY` | `192` | MP3-Bitrate in kbps |
| `SERVICE_PORT` | `8000` | HTTP-Port |
| `LOG_LEVEL` | `INFO` | Log-Level |

## Abhängigkeiten

- **ffmpeg** (Runtime-Abhängigkeit im Dockerfile)
- **yt-dlp** – Download-Engine
- **mutagen** – ID3-Tag-Manipulation (Fallback für Cover-Art)
- **FastAPI + uvicorn** – HTTP-Server
- **structlog** – Logging

## Shared Volume

Der Service schreibt MP3-Dateien nach `/mnt/audio/tracks/downloads/`. Dieses Verzeichnis muss mit dem `backend`-Service und dem `audio`-Service geteilt werden (siehe `docker-compose.yml`).

## Architektur-Entscheidung

Der Service ist bewusst als eigenständiger Microservice ohne MQTT-Abhängigkeit implementiert, damit er später als eigenständiges Python-Package extrahiert werden kann.
