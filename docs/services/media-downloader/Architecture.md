# Media-Downloader-Service – Architecture

## 1. Zweck & Verantwortung

Der Media-Downloader-Service ist ein eigenständiger Microservice für den lokalen Medienimport: Er
liest die Tonspur einer übergebenen Medien-URL, konvertiert sie in eine MP3-Datei und legt sie im
gemeinsamen Audio-Storage ab. Er wird ausschließlich über das Backend aufgerufen – der WebUI-Client
spricht nie direkt mit ihm.

**Ziele:**

- Bereitstellung einer einfachen REST-API für das Backend (`/validate-url`, `/download`)
- Isolation der Lese-/Konvertierungs-Werkzeuge (yt-dlp, ffmpeg) in einem eigenen Container
- Schutz vor missbräuchlicher Nutzung (Domain-Whitelist, Dateigrößen-Limit)
- Asynchrone Verarbeitung mit Timeout-Handling
- Retry-Logik bei transienten Fehlern

**Nicht-Ziele:**

- Keine MQTT-Kommunikation
- Keine Datenbank
- Keine direkte Kommunikation mit dem WebUI
- Keine Unterstützung für Zugangsdaten, Cookies, Sessions oder Schlüsselmaterial – und damit keine
  Funktion zum Umgehen von Zugangs- oder Schutzmechanismen (siehe Abschnitt 8)

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

Prüft eine URL und gibt Metadaten zurück, ohne den Import zu starten.

**Query-Parameter:**

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ✓ | Die zu prüfende Medien-URL |

**Response (200):**

```json
{
  "valid": true,
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail_url": "https://example.org/media/cover.jpg",
  "video_id": "abc123"
}
```

**Fehler:**

- `400` – Domain nicht auf Whitelist
- `422` – URL ungültig oder Medium nicht lesbar

---

### `POST /download?url=<url>`

Liest das Medium, legt die Tonspur als MP3 unter
`DOWNLOAD_PATH/<sanitized_title>.mp3` ab und gibt die Metadaten zurück.

**Query-Parameter:**

| Parameter | Pflicht | Beschreibung |
|---|---|---|
| `url` | ✓ | Die zu importierende Medien-URL |

**Response (200):**

```json
{
  "filename": "beethoven_symphony_5.mp3",
  "path": "/mnt/audio/tracks/beethoven_symphony_5.mp3",
  "title": "Beethoven Symphony No. 5",
  "artist": "Berlin Philharmonic",
  "duration_ms": 1980000,
  "thumbnail_url": "https://example.org/media/cover.jpg"
}
```

**Fehler:**

- `400` – Domain nicht auf Whitelist
- `413` – Datei überschreitet `MAX_FILESIZE_MB`
- `422` – Import fehlgeschlagen
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

## 8. Sicherheit und Nutzungsgrenzen

- **Domain-Whitelist:** Nur explizit erlaubte Hosts können verwendet werden (`_ALLOWED_DOMAINS` im Backend). Das ist ein technischer Schutz vor beliebigen Abrufzielen und keine rechtliche Freigabe der dort liegenden Inhalte.
- **Dateigrößen-Limit:** Importe über `MAX_FILESIZE_MB` werden abgebrochen
- **Kein direkter Zugriff vom WebUI:** Der Service ist nur innerhalb des Docker-Netzwerks erreichbar
- **Keine Zugangsparameter:** Weder API, UI noch Umgebungsvariablen bieten Felder für Cookie-Dateien, Browser-Cookies, Login-Daten, OAuth, Session-Tokens oder Entschlüsselungsschlüssel. An yt-dlp wird ausschließlich die URL (und optional das Zielverzeichnis) weitergereicht; die Option-Dicts werden pro Aufruf im Code aufgebaut und sind von außen nicht erweiterbar.
- **Keine Umgehungsfunktionen:** Das Projekt implementiert und dokumentiert keine Unterstützung für das Umgehen von DRM, Paywalls, Geoblocking oder vergleichbaren Zugriffssperren. Die eingesetzte Bibliothek kann eigene Fähigkeiten mitbringen; welche Schutzmechanismen im Einzelfall greifen, bewertet das Projekt nicht.
- **Bestätigung zur rechtmäßigen Nutzung:** Die WebUI zeigt vor jedem Import einen Hinweis zur rechtmäßigen Nutzung und verlangt eine ausdrückliche Bestätigung des Nutzers, bevor Prüfung oder Import möglich sind. Die Bestätigung wird nur im UI-Zustand gehalten und nicht gespeichert.

---

## 9. Docker-Integration

Der Service ist als `media-downloader` in `docker-compose.yml` definiert:

- **Port:** `8007` (intern), auf dem Host nur auf `127.0.0.1:8007` - die
  Download-API kennt keine Authentifizierung
- **Volume:** Teilt `/mnt/audio` mit dem Backend und Audio-Service
- **depends_on:** Backend (healthy)
- **Optionale .env-Variablen:** `MEDIA_DOWNLOADER_MAX_FILESIZE_MB`, `MEDIA_DOWNLOADER_ALLOWED_DOMAINS`
