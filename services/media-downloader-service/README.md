# media-downloader-service

Eigenständiger Minabox-Microservice für den **lokalen Medienimport**: Er nimmt
eine Medien-URL entgegen und legt die Tonspur in der lokalen Bibliothek ab.

## Aufgabe

Der Service erhält vom `backend-service` eine URL, liest die Tonspur, speichert
sie technisch als **MP3 (192 kbps)** im gemeinsamen Audio-Storage, bettet die
Metadaten (Titel, Interpret, Cover) ein und gibt Dateipfad und Metadaten
zurück. Er kommuniziert **nur via REST** mit dem `backend-service` – kein MQTT,
kein direkter Zugriff aus der WebUI.

## Rechtmäßiger Medienimport (Lawful media import)

Der Import ist nur zulässig, wenn du die erforderlichen Nutzungs- und
Vervielfältigungsrechte besitzt oder eine gesetzliche Erlaubnis greift – etwa
bei eigenen Aufnahmen, gemeinfreien Werken oder Inhalten mit ausdrücklicher
Erlaubnis bzw. Lizenz des Rechteinhabers.

Die Verantwortung dafür liegt bei dir als Nutzer. Weder dieser Service noch das
Backend können prüfen, ob du für eine konkrete URL die nötigen Rechte hast; die
Domain-Whitelist ist ein technischer Schutz vor beliebigen Abrufzielen und
keine rechtliche Bewertung. Das Projekt ist nicht dafür bestimmt, technische
Schutzmaßnahmen oder Zugangsbeschränkungen zu umgehen.

*English:* Import content only if you hold the necessary usage and reproduction
rights or a statutory exception applies – for example your own recordings,
public domain works, or content licensed or explicitly permitted by the rights
holder. Responsibility rests with you; neither this service nor the backend can
assess the rights situation of a given URL. The project is not intended to
circumvent technical protection measures or access restrictions.

## Technische Grenzen

Die Integration reicht ausschließlich die URL (und optional ein Zielverzeichnis)
an die Download-Bibliothek weiter. Sie bietet **keine** Parameter, Felder oder
Umgebungsvariablen für:

- Cookie-Dateien oder Browser-Cookie-Import
- Login-Daten, Benutzername/Passwort, OAuth oder Session-Tokens
- Entschlüsselungs- oder Lizenzschlüssel
- gezieltes Umgehen von Geoblocking, Paywalls oder DRM

Damit lassen sich über diese API praktisch nur Quellen importieren, die ohne
solche Angaben lesbar sind. Die eingesetzte Bibliothek (yt-dlp) kann
eigenständig weitere Fähigkeiten mitbringen – das Projekt gibt sie nicht weiter
und dokumentiert sie nicht als Anwendungsfall. Eine Aussage darüber, welche
Zugriffsschutzmechanismen im Einzelfall greifen, kann und will das Projekt
nicht treffen.

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `GET` | `/health` | Health-Check |
| `GET` | `/info?url=<url>` | Metadaten ohne Import (Preview) |
| `POST` | `/download` | Tonspur importieren, MP3-Metadaten zurückgeben |

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

> `video_id` ist die von der Quelle vergebene Kennung. Der Feldname stammt aus
> der ersten Fassung der API und bleibt aus Kompatibilitätsgründen erhalten.

## Konfiguration (Umgebungsvariablen)

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `AUDIO_TRACKS_DIR` | `/mnt/audio/tracks/downloads` | Zielverzeichnis für MP3-Dateien |
| `AUDIO_QUALITY` | `192` | MP3-Bitrate in kbps |
| `SERVICE_PORT` | `8000` | HTTP-Port |
| `LOG_LEVEL` | `INFO` | Log-Level |

Weitere Variablen gibt es bewusst nicht – insbesondere keine für Zugangsdaten
oder Cookies (siehe *Technische Grenzen*).

## Abhängigkeiten

- **ffmpeg** (Runtime-Abhängigkeit im Dockerfile)
- **yt-dlp** – Lese-/Extraktions-Bibliothek
- **mutagen** – ID3-Tag-Manipulation (Fallback für Cover-Art)
- **FastAPI + uvicorn** – HTTP-Server
- **structlog** – Logging

## Shared Volume

Der Service schreibt MP3-Dateien nach `/mnt/audio/tracks/downloads/`. Dieses
Verzeichnis muss mit dem `backend`-Service und dem `audio`-Service geteilt
werden (siehe `docker-compose.yml`).

## Architektur-Entscheidung

Der Service ist bewusst als eigenständiger Microservice ohne
MQTT-Abhängigkeit implementiert, damit er später als eigenständiges
Python-Package extrahiert werden kann.

## Fragen und Meldungen

Für Rückfragen oder Hinweise zu Rechten an importierbaren Inhalten:
[GitHub Issues](https://github.com/Opnek90/Minabox/issues). Eine gesonderte
Kontaktadresse führt das Projekt derzeit nicht.
