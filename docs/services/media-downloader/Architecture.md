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

## 4. Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging-Level |
| `DOWNLOAD_PATH` | `/mnt/audio/tracks` | Zielverzeichnis für MP3-Dateien |
| `MAX_FILESIZE_MB` | `200` | Maximale Dateigröße in MB |
| `ALLOWED_DOMAINS` | `youtube.com,youtu.be,soundcloud.com,bandcamp.com,vimeo.com` | Erlaubte Domains (Komma-getrennt) |

---

## 5. Datenfluss

```
WebUI
  │
  │  POST /api/v1/tracks/from-url?url=...
  ▼
Backend
  │
  │  POST http://media-downloader:8007/download?url=...
  ▼
Media-Downloader
  │
  │  yt-dlp → ffmpeg → MP3
  ▼
/mnt/audio/tracks/<title>.mp3
  │
  │  Backend registriert Track in SQLite
  ▼
WebUI (Track in Mediathek sichtbar)
```

---

## 6. Sicherheit

- **Domain-Whitelist:** Nur explizit erlaubte Domains können verwendet werden (`ALLOWED_DOMAINS`)
- **Dateigrößen-Limit:** Downloads über `MAX_FILESIZE_MB` werden abgebrochen
- **Kein direkter Zugriff vom WebUI:** Der Service ist nur innerhalb des Docker-Netzwerks erreichbar
- **Urheberrechts-Disclaimer:** Die WebUI zeigt vor jedem Import einen Hinweis auf die rechtliche Verantwortung des Nutzers

---

## 7. Docker-Integration

Der Service ist als `media-downloader` in `docker-compose.yml` definiert:

- **Port:** `8007` (intern), optional extern auf `8007` exponiert
- **Volume:** Teilt `/mnt/audio` mit dem Backend und Audio-Service
- **depends_on:** Backend (healthy)
- **Optionale .env-Variablen:** `MEDIA_DOWNLOADER_MAX_FILESIZE_MB`, `MEDIA_DOWNLOADER_ALLOWED_DOMAINS`
