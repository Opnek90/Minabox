# Media-Downloader-Service – Architecture

## 1. Zweck & Verantwortung

Der Media-Downloader-Service ist ein eigenständiger Microservice, der Videos und Audioinhalte von
uöffentlichen Plattformen (YouTube, SoundCloud, Bandcamp, Vimeo, …) herunterladet, als MP3-Datei
konvertiert und im gemeinsamen Audio-Storage speichert. Er wird ausschließlich über das Backend
aufgerufen – der WebUI-Client spricht nie direkt mit ihm.

**Ziele:**

- Bereitstellung einer einfachen REST-API für das Backend (`/validate-url`, `/download`)
- Isolation von yt-dlp und ffmpeg in einem eigenen Container
- Schutz vor missbräuchlicher Nutzung (Domain-Whitelist, Dateigrößen-Limit)
- Asynchrone Downloads mit Timeout-Handling
- Retry-Logik bei transienten Fehlern

**Nicht-Ziele:**

- Keine MQTT-Kommunikation
- Keine Datenbank
- Keine direkte Kommunikation mit dem WebUI

---

## 2. Technologie-Stack

| Komponente | Technologie |
|---|---|
| Laufzeit | Python 3.12 |
| Web-Framework | FastAPI + Uvicorn |
| Downloader | yt-dlp (regelmäßig aktualisiert) |
| Konvertierung | ffmpeg (Alpine-Paket) |
| Container | Docker (Alpine-basiert) |

---

## 3. API-Endpunkte

### `GET /health`

Healthcheck für Docker.

**Response:** `{"status": "ok"}`

---

### `GET /validate-url?url=<url>`

Prüft eine URL und gibt Metadaten zurück, ohne den Download zu starten.

**Query-Parameter:**

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ✓ | Die zu prüfende Video-URL |

**Response (200):**

```json
{
  "valid": true,
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail_url": "https://i.ytimg.com/vi/xxx/hqdefault.jpg",
  "video_id": "dQw4w9WgXcQ"
}
```

**Fehler:**

- `400` – Domain nicht auf Whitelist
- `422` – URL ungültig oder Video nicht verfügbar

---

### `POST /download?url=<url>`

Lädt das Video herunter, extrahiert den Audio-Track als MP3 und speichert ihn unter
`DOWNLOAD_PATH/<sanitized_title>.mp3`.

**Query-Parameter:**

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ✓ | Die Download-URL |

**Response (200):**

```json
{
  "filename": "beethoven_symphony_5.mp3",
  "path": "/mnt/audio/tracks/beethoven_symphony_5.mp3",
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail_url": "https://i.ytimg.com/vi/xxx/hqdefault.jpg"
}
```

**Fehler:**

- `400` – Domain nicht auf Whitelist
- `413` – Datei überschreitet `MAX_FILESIZE_MB`
- `422` – Download fehlgeschlagen
- `504` – Timeout

---

## 4. Retry-Logik

Der Backend-seitige `MediaDownloaderClient` implementiert eine automatische Retry-Logik für beide Endpoints (`/download` und `/info`):

- **Max. Versuche:** 3 (`_MAX_RETRIES = 3`)
- **Backoff:** linear – `2 * attempt` Sekunden zwischen den Versuchen (2 s, 4 s)
- **Retryable Fehler:** HTTP 5xx, `httpx.TimeoutException`, `httpx.RequestError`
- **Nicht retryable:** HTTP 4xx (z. B. ungültige URL, Domain-Whitelist) – sofortiger Abbruch
- **Logging:** Jeder Retry-Versuch wird mit `structlog` als Warning geloggt (`media_downloader_download_5xx_retry`, `media_downloader_download_transient_retry`)

Die Logik liegt in `services/backend-service/src/backend_service/infrastructure/media_downloader_client.py`.

---

## 5. Cover-Art-Download (Fallback)

Nach einem erfolgreichen Download versucht das Backend, ein Cover-Bild für den Track zu ermitteln.
Die Logik liegt in `services/backend-service/src/backend_service/api/routes_tracks.py`:

1. **Primär – eingebettetes Cover:** `_extract_cover_art()` liest mit `mutagen` eingebettete APIC-Frames (MP3/ID3) oder `pictures` (FLAC/OGG) aus der heruntergeladenen MP3-Datei.
2. **Fallback – Remote-Thumbnail:** Ist kein eingebettetes Cover vorhanden, lädt `_download_thumbnail()` die `thumbnail`-URL aus dem yt-dlp-Ergebnis asynchron via `httpx` herunter.
3. Das Cover wird unter `STATIC_DIR/covers/track_{id}.jpg|.png` gespeichert und als `/static/covers/track_{id}.jpg|.png` in `cover_art_url` des Track-DB-Eintrags geschrieben.

**Filesystem-Struktur nach Download:**

```
/mnt/audio/
  tracks/
    {track_id}/
      <title>.mp3

/data/static/
  covers/
    track_{track_id}.jpg   ← Cover Art (eingebettet oder Thumbnail-Fallback)
```

Fehler beim Cover-Download sind nicht kritisch und werden nur als Warning geloggt (`track_cover_extract_failed`, `track_thumbnail_download_failed`). Der Track-Import schlägt dadurch nicht fehl.

---

## 6. Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging-Level |
| `DOWNLOAD_PATH` | `/mnt/audio/tracks` | Zielverzeichnis für MP3-Dateien |
| `MAX_FILESIZE_MB` | `200` | Maximale Dateigröße in MB |
| `ALLOWED_DOMAINS` | `youtube.com,youtu.be,soundcloud.com,bandcamp.com,vimeo.com` | Erlaubte Domains (Komma-getrennt) |

---

## 7. Datenfluss

```
WebUI
  │
  │  POST /api/v1/tracks/from-url?url=...  →  HTTP 202 (sofort)
  ▼
Backend
  │  (Background Task)
  │  POST http://media-downloader:8007/download?url=...
  │  └─ Retry bis zu 3× bei 5xx/Timeout
  ▼
Media-Downloader
  │
  │  yt-dlp → ffmpeg → MP3
  ▼
/mnt/audio/tracks/{track_id}/<title>.mp3
  │
  │  Backend: mutagen → Cover aus ID3 extrahieren
  │  (Fallback: thumbnail_url via httpx herunterladen)
  │  → /data/static/covers/track_{id}.jpg
  │
  │  Backend registriert Track in SQLite (title, artist, cover_art_url)
  ▼
WebUI: Polling GET /tracks/{id}/download-status → status "done"
```

---

## 8. Sicherheit

- **Domain-Whitelist:** Nur explizit erlaubte Domains können verwendet werden (`_ALLOWED_DOMAINS` im Backend)
- **Dateigrößen-Limit:** Downloads über `MAX_FILESIZE_MB` werden abgebrochen
- **Kein direkter Zugriff vom WebUI:** Der Service ist nur innerhalb des Docker-Netzwerks erreichbar
- **Urheberrechts-Disclaimer:** Die WebUI zeigt vor jedem Import einen Hinweis auf die rechtliche Verantwortung des Nutzers

---

## 9. Docker-Integration

Der Service ist als `media-downloader` in `docker-compose.yml` definiert:

- **Port:** `8007` (intern), optional extern auf `8007` exponiert
- **Volume:** Teilt `/mnt/audio` mit dem Backend und Audio-Service
- **depends_on:** Backend (healthy)
- **Optionale .env-Variablen:** `MEDIA_DOWNLOADER_MAX_FILESIZE_MB`, `MEDIA_DOWNLOADER_ALLOWED_DOMAINS`
