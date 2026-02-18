# Backend-Service – Architecture

## 1. Zweck & Verantwortung

Der Backend-Service ist das zentrale Orchestrierungs- und Datenzentrum der Minabox. Er koordiniert alle Services, verwaltet die Datenbank und fungiert als Brücke zwischen MQTT (intern) und WebSocket/REST (nach außen zur WebUI).

Ziele:

- Einziger Service mit direktem Datenbankzugriff (Tag-Mappings, Playlists, Tracks, Metadaten)
- MQTT-WebSocket-Bridge für Real-Time Updates an die WebUI
- REST-API für synchrone Queries und Commands
- Zentrale Orchestrierung von Service-übergreifenden Workflows (z.B. Tag-Scan → Playlist-Lookup → Audio-Trigger)
- Config-Management für andere Services (Button, LED, RFID, Audio)
- Audio-Upload und Metadaten-Verwaltung

Nicht-Ziele:

- Keine direkte Hardware-Anbindung (GPIO, I2C etc.)
- Keine Audio-Wiedergabe (delegiert an Audio-Service)
- Keine Button-/RFID-Hardware-Logik (nur Event-Verarbeitung)
- Keine User-Authentication (kann später ergänzt werden)
- Keine Multi-Tenancy (eine Box = eine Instanz)

---

## 2. Öffentliche Schnittstellen

### 2.1 REST-API

**Base-Path:** `/api/v1`

**Tags & Content:**

- `GET /api/v1/tags` – Liste aller RFID-Tags
- `GET /api/v1/tags/{tag_id}` – Details zu einem Tag inkl. Mapping
- `POST /api/v1/tags` – Neuen Tag anlegen/zuordnen (Lern-Modus)
- `PUT /api/v1/tags/{tag_id}` – Tag-Mapping aktualisieren
- `DELETE /api/v1/tags/{tag_id}` – Tag löschen

**Playlists:**

- `GET /api/v1/playlists` – Liste aller Playlists
- `GET /api/v1/playlists/{playlist_id}` – Playlist-Details inkl. Tracks
- `POST /api/v1/playlists` – Neue Playlist erstellen
- `PUT /api/v1/playlists/{playlist_id}` – Playlist bearbeiten
- `DELETE /api/v1/playlists/{playlist_id}` – Playlist löschen

**Tracks:**

- `GET /api/v1/tracks` – Liste aller Tracks
- `GET /api/v1/tracks/{track_id}` – Track-Details
- `POST /api/v1/tracks/upload` – Track hochladen (multipart/form-data)
- `POST /api/v1/tracks` – Stream oder Track anlegen (JSON)
  - Für Streams: `{ "title": "...", "artist": "...", "album": "...", "source_type": "stream", "source_uri": "https://..." }`
  - Für manuelle File-Einträge: `{ "title": "...", "source_type": "file", "source_uri": "/mnt/audio/..." }`
- `PUT /api/v1/tracks/{track_id}` – Track-Metadaten bearbeiten
- `DELETE /api/v1/tracks/{track_id}` – Track löschen (inkl. Datei bei source_type="file")

**Audio-Control:**

- `POST /api/v1/audio/play` – Wiedergabe starten (optional mit track_id oder playlist_id)
- `POST /api/v1/audio/pause` – Wiedergabe pausieren
- `POST /api/v1/audio/stop` – Wiedergabe stoppen
- `POST /api/v1/audio/next` – Nächster Track
- `POST /api/v1/audio/prev` – Vorheriger Track
- `POST /api/v1/audio/volume` – Lautstärke setzen
- `GET /api/v1/audio/status` – Aktueller Wiedergabe-Status

**RFID-Control:**

- `POST /api/v1/rfid/learning-mode` – Lern-Modus aktivieren/deaktivieren

**Service-Config:**

- `GET /api/v1/config/buttons` – Button-Konfiguration abrufen
- `PUT /api/v1/config/buttons` – Button-Konfiguration aktualisieren
- `GET /api/v1/config/leds` – LED-Konfiguration abrufen
- `PUT /api/v1/config/leds` – LED-Konfiguration aktualisieren
- `GET /api/v1/config/audio` – Audio-Konfiguration abrufen
- `PUT /api/v1/config/audio` – Audio-Konfiguration aktualisieren
- `GET /api/v1/config/rfid` – RFID-Konfiguration abrufen
- `PUT /api/v1/config/rfid` – RFID-Konfiguration aktualisieren

**System & Health:**

- `GET /api/v1/health` – Backend-Health
- `GET /api/v1/system/status` – Gesamtsystem-Status (alle Services)
- `POST /api/v1/system/restart` – Service-Neustart triggern (optional)

### 2.2 WebSocket

**Endpoint:** `/ws`

Das Backend bietet eine WebSocket-Verbindung für Real-Time Updates an die WebUI.

**Outgoing Messages (Backend → WebUI):**

Audio-Status:

```json
{
  "type": "audio_status",
  "data": {
    "state": "playing",
    "track_id": "track_123",
    "source_type": "file",
    "source_uri": "/mnt/audio/tracks/123/original.mp3",
    "position_ms": 12345,
    "duration_ms": 240000,
    "volume": 55,
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

RFID-Event:

```json
{
  "type": "rfid_scanned",
  "data": {
    "tag_id": "04A224BC19",
    "reader_id": "pn532_01",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

RFID-Lern-Modus:

```json
{
  "type": "rfid_scanned_learning",
  "data": {
    "tag_id": "04A224BC19",
    "reader_id": "pn532_01",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Button-Action:

```json
{
  "type": "button_action",
  "data": {
    "action": "play_pause",
    "source": "btn_1",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Service-Status:

```json
{
  "type": "service_status",
  "data": {
    "service": "audio",
    "state": "online",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

**Incoming Messages (WebUI → Backend):**

Optional kann die WebUI Commands via WebSocket senden (alternativ REST):

```json
{
  "type": "command",
  "command": "audio_play",
  "payload": {
    "track_id": "track_123"
  }
}
```

### 2.3 MQTT – Subscribe Topics

Der Backend subscribed auf folgende MQTT-Topics:

**RFID:**

- `minabox/<device-id>/rfid/tag-scanned`
- `minabox/<device-id>/rfid/tag-scanned-learning`
- `minabox/<device-id>/rfid/tag-removed`
- `minabox/<device-id>/rfid/status`

**Audio:**

- `minabox/<device-id>/audio/status`
- `minabox/<device-id>/audio/error`

**Button:**

- `minabox/<device-id>/button/+` (alle Button-Actions)
- `minabox/<device-id>/button/config/response`

**LED:**

- `minabox/<device-id>/led/config/response`

**System:**

- `minabox/<device-id>/system/+`

### 2.4 MQTT – Publish Topics

**Audio-Commands:**

- `minabox/<device-id>/audio/play`
- `minabox/<device-id>/audio/pause`
- `minabox/<device-id>/audio/stop`
- `minabox/<device-id>/audio/next`
- `minabox/<device-id>/audio/prev`
- `minabox/<device-id>/audio/set-volume`
- `minabox/<device-id>/audio/volume-up`
- `minabox/<device-id>/audio/volume-down`

**RFID-Commands:**

- `minabox/<device-id>/rfid/cmd/set-mode`
- `minabox/<device-id>/rfid/cmd/reload-config`

**Config-Updates:**

- `minabox/<device-id>/button/config/update`
- `minabox/<device-id>/button/config/get`
- `minabox/<device-id>/led/config/update`
- `minabox/<device-id>/led/config/get`
- `minabox/<device-id>/audio/config/update`
- `minabox/<device-id>/audio/config/get`

### 2.5 System-/Host-Operationen

Aktionen, die direkt auf dem Host ausgeführt werden müssen (z.B. Dateien verschieben, später ggf. Netz- oder Mount-Konfiguration), werden **nicht** vom Backend selbst ausgeführt. Das Backend delegiert solche Anfragen an den **Host-Helper-Service**, der mit erweiterten Rechten läuft und nur intern erreichbar ist. Das Backend validiert die von der WebUI übergebenen Parameter und leitet sie an den Host-Helper weiter; Host-Details oder Fehler des Host-Helpers werden nicht ungefiltert an die WebUI durchgereicht. Details zu Rolle, Sicherheit und Schnittstelle des Host-Helpers: [docs/services/host-helper/Architecture.md](../host-helper/Architecture.md).

---

## 3. Datenbank-Schema

Der Backend verwendet SQLite mit SQLAlchemy und Alembic für Migrations.

### 3.1 Tags

```python
class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    tag_id = Column(String, unique=True, nullable=False, index=True)  # z.B. "04A224BC19"
    name = Column(String, nullable=True)  # z.B. "Benjamin Blümchen"
    content_type = Column(String, nullable=False)  # "playlist" | "track"
    content_id = Column(Integer, nullable=False)  # Playlist-ID oder Track-ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### 3.2 Playlists

```python
class Playlist(Base):
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    tracks = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan")
```

### 3.3 Tracks

```python
class Track(Base):
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    album = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    source_type = Column(String, nullable=False)  # "file" | "stream"
    source_uri = Column(String, nullable=False)  # Pfad oder URL
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 3.4 PlaylistTrack (M:N)

```python
class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    
    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    position = Column(Integer, nullable=False)  # Reihenfolge in Playlist (0-basiert)
    
    playlist = relationship("Playlist", back_populates="tracks")
    track = relationship("Track")
    
    __table_args__ = (
        UniqueConstraint('playlist_id', 'position', name='unique_playlist_position'),
    )
```

### 3.5 Alembic Migrations

Der Backend verwendet Alembic für Schema-Migrationen:

**Setup:**

```bash
alembic init alembic
```

**env.py konfigurieren:**

```python
from backend_service.models import Base
target_metadata = Base.metadata
```

**Neue Migration erstellen:**

```bash
alembic revision --autogenerate -m "Add cover_image to playlists"
```

**Migrations anwenden:**

```bash
alembic upgrade head
```

Beim Service-Start wird automatisch `alembic upgrade head` ausgeführt, um sicherzustellen, dass die DB aktuell ist.

---

## 4. Kern-Funktionen / Workflows

### 4.1 Tag-Scan → Wiedergabe (Normal-Modus)

Ablauf:

1. Backend empfängt `minabox/<device-id>/rfid/tag-scanned` mit `tag_id`.
2. Lookup in DB: `Tag` → `content_type` + `content_id`.
3. Falls Tag nicht gefunden:
   - Logge `tag_not_found`.
   - Optional: Pushe Fehler-Event via WebSocket an WebUI.
   - Abbruch.
4. Falls `content_type == "playlist"`:
   - Lade Playlist mit allen zugeordneten Tracks (sortiert nach `position`).
   - Erstelle neue Playback-Session mit erstem Track (Index 0).
5. Falls `content_type == "track"`:
   - Lade Track-Details.
   - Erstelle Session mit einem Track.
6. Sende `minabox/<device-id>/audio/play` mit Track-Daten (`source_type`, `source_uri`, `start_position_ms=0`) an Audio-Service.
7. Pushe Event via WebSocket an WebUI:

```json
{
  "type": "rfid_scanned",
  "data": {
    "tag_id": "04A224BC19",
    "content_type": "playlist",
    "content_name": "Benjamin Blümchen",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

### 4.2 Tag anlernen (Lern-Modus)

Ablauf:

1. WebUI aktiviert Lern-Modus via `POST /api/v1/rfid/learning-mode` mit `{"enabled": true}`.
2. Backend sendet `minabox/<device-id>/rfid/cmd/set-mode` mit Payload `{"mode": "learning"}`.
3. RFID-Service wechselt in Lern-Modus.
4. Backend empfängt `minabox/<device-id>/rfid/tag-scanned-learning` mit `tag_id`.
5. Backend prüft, ob Tag bereits in DB existiert:
   - Falls ja: Info an WebUI, dass Tag bereits zugeordnet ist.
   - Falls nein: neuer Tag.
6. Backend pusht Event via WebSocket:

```json
{
  "type": "rfid_scanned_learning",
  "data": {
    "tag_id": "04A224BC19",
    "already_assigned": false,
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

7. WebUI zeigt Dialog: "Welchem Content soll dieser Tag zugeordnet werden?"
8. User wählt Playlist oder Track aus.
9. WebUI sendet `POST /api/v1/tags` mit:

```json
{
  "tag_id": "04A224BC19",
  "name": "Benjamin Blümchen",
  "content_type": "playlist",
  "content_id": 5
}
```

10. Backend speichert Tag-Mapping in DB.
11. Backend deaktiviert Lern-Modus (sendet `set-mode` mit `normal`).
12. Bestätigung an WebUI.

### 4.3 Button-Action → Audio-Control

Ablauf:

1. Backend empfängt `minabox/<device-id>/button/play-pause`.
2. Backend prüft aktuellen Audio-Status (gecacht aus letztem `audio/status`-Event).
3. Falls `state == "playing"`:
   - Backend sendet `minabox/<device-id>/audio/pause`.
4. Falls `state == "paused"`:
   - Backend sendet `minabox/<device-id>/audio/play` (ohne Payload → Resume).
5. Falls `state == "stopped"` und Session existiert:
   - Backend sendet `audio/play` mit aktuellem Track aus Session.
6. Pushe Action via WebSocket an WebUI:

```json
{
  "type": "button_action",
  "data": {
    "action": "play_pause",
    "source": "btn_1",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

### 4.4 Next/Prev – Playlist-Navigation

Der Backend verwaltet eine **Playback-Session** im Memory:

```python
class PlaybackSession:
    playlist_id: int | None
    current_track_index: int
    tracks: List[Track]  # Sortiert nach position
```

**Next:**

1. Backend empfängt `minabox/<device-id>/button/next` oder REST-Call `POST /api/v1/audio/next`.
2. Falls keine Session aktiv → Fehler oder Nichts tun.
3. Inkrementiere `current_track_index`.
4. Falls Index >= Anzahl Tracks:
   - **Playlist zu Ende → Stop**
   - Backend sendet `minabox/<device-id>/audio/stop`.
   - Session bleibt bestehen (Index bleibt am Ende).
   - Abbruch.
5. Lade Track an Index `current_track_index`.
6. Sende `minabox/<device-id>/audio/play` mit neuem Track.

**Prev:**

1. Backend empfängt `minabox/<device-id>/button/prev` oder REST-Call `POST /api/v1/audio/prev`.
2. Falls keine Session → Fehler.
3. Dekrementiere `current_track_index`.
4. Falls Index < 0:
   - Setze Index auf 0 (bleibt beim ersten Track).
5. Lade Track an Index `current_track_index`.
6. Sende `minabox/<device-id>/audio/play` mit Track.

**Track-Ende (EOS - End of Stream):**

Der Audio-Service sendet bei Track-Ende ein Event (z.B. via `audio/status` mit `state="stopped"` oder speziellem Event). Der Backend kann darauf reagieren:

1. Backend empfängt Track-Ende-Event.
2. Falls Session aktiv und weitere Tracks vorhanden:
   - Automatisch `next` triggern (wie oben).
3. Falls letzter Track:
   - Stop (wie oben beschrieben).

### 4.5 Config-Management

Ablauf:

1. WebUI sendet `PUT /api/v1/config/buttons` mit neuer Config (JSON-Payload entsprechend Service-Schema).
2. Backend validiert Config gegen Service-Schema (Pydantic-Model).
3. Falls ungültig:
   - Return HTTP 400 mit Fehlerdetails.
4. Falls gültig:
   - Speichere Config in Service-JSON-Datei (z.B. `services/button-service/config/buttons.json`).
   - Optional: Speichere auch in DB (für Backup/Audit-Log).
   - Sende `minabox/<device-id>/button/config/update` via MQTT mit Config als Payload.
   - Warte auf `minabox/<device-id>/button/config/response`.
5. Falls Service antwortet mit `success=true`:
   - Return HTTP 200 mit Bestätigung.
6. Falls Service antwortet mit `success=false`:
   - Return HTTP 500 mit Service-Fehlerdetails.

### 4.6 Audio-Upload

**Endpoint:** `POST /api/v1/tracks/upload`

**Request:**

```http
POST /api/v1/tracks/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="track.mp3"
Content-Type: audio/mpeg

<binary data>
------WebKitFormBoundary
Content-Disposition: form-data; name="title"

Benjamin Blümchen - Folge 1
------WebKitFormBoundary
Content-Disposition: form-data; name="artist"

Kiddinx
------WebKitFormBoundary
Content-Disposition: form-data; name="album"

Benjamin Blümchen
------WebKitFormBoundary--
```

**Backend-Logik:**

1. Empfange Upload (FastAPI FileUpload).
2. Erstelle neuen Track-Eintrag in DB (noch ohne `source_uri`, `duration_ms`):

```python
track = Track(
    title=form_data.title,
    artist=form_data.artist,
    album=form_data.album,
    source_type="file",
    source_uri=""  # Platzhalter
)
db.add(track)
db.commit()
track_id = track.id
```

3. Erstelle Zielverzeichnis: `/mnt/audio/tracks/{track_id}/`.
4. Speichere Datei: `/mnt/audio/tracks/{track_id}/original.mp3` (oder `.ogg`, `.flac` je nach Upload).
5. Extrahiere Metadaten mit `mutagen`:

```python
from mutagen import File

audio_file = File(file_path)
duration_ms = int(audio_file.info.length * 1000) if audio_file.info else None

# Optional: Überschreibe Titel/Artist/Album aus ID3-Tags, falls nicht im Form angegeben
if not form_data.title and audio_file.tags:
    title = audio_file.tags.get("TIT2", [None])[0]
```

6. Update Track in DB:

```python
track.source_uri = f"/mnt/audio/tracks/{track_id}/original.mp3"
track.duration_ms = duration_ms
db.commit()
```

7. Return Track-Objekt als JSON:

```json
{
  "id": 123,
  "title": "Benjamin Blümchen - Folge 1",
  "artist": "Kiddinx",
  "album": "Benjamin Blümchen",
  "duration_ms": 2400000,
  "source_type": "file",
  "source_uri": "/mnt/audio/tracks/123/original.mp3",
  "created_at": "2026-02-14T22:30:00Z"
}
```

**Filesystem-Struktur:**

```
/mnt/audio/
  tracks/
    1/
      original.mp3
    2/
      original.mp3
    123/
      original.mp3
```

**Vorteil:** Track-ID eindeutig, Dateien isoliert, einfach zu löschen (Track löschen → Verzeichnis löschen).

### 4.7 Stream-Hinzufügen

**Endpoint:** `POST /api/v1/tracks`

**Request:**

```http
POST /api/v1/tracks HTTP/1.1
Content-Type: application/json

{
  "title": "Radio Beispiel",
  "artist": "Radio Station",
  "album": null,
  "source_type": "stream",
  "source_uri": "https://stream.example.com/radio.mp3"
}
```

**Backend-Logik:**

1. Validiere Request-Body (Pydantic-Schema).
2. Erstelle neuen Track-Eintrag in DB:

```python
track = Track(
    title=request.title,
    artist=request.artist,
    album=request.album,
    source_type="stream",
    source_uri=request.source_uri,
    duration_ms=None  # Streams haben keine feste Dauer
)
db.add(track)
db.commit()
```

3. Return Track-Objekt als JSON:

```json
{
  "id": 124,
  "title": "Radio Beispiel",
  "artist": "Radio Station",
  "album": null,
  "duration_ms": null,
  "source_type": "stream",
  "source_uri": "https://stream.example.com/radio.mp3",
  "created_at": "2026-02-14T22:35:00Z"
}
```

---

## 5. Abhängigkeiten

**Services:**

- RFID-Service (Tag-Events)
- Audio-Service (Wiedergabe-Commands & Status)
- Button-Service (Action-Events, Config-Responses)
- LED-Service (Config-Responses, optional)
- WebUI-Service (REST/WebSocket Client)

**Infrastruktur:**

- MQTT-Broker (Mosquitto)
- SQLite-Datenbank (lokal, z.B. `/data/minabox.db`)
- Dateisystem (Audio-Dateien unter `/mnt/audio/tracks/` oder konfigurierbar)

**Python-Libraries:**

- `fastapi` – REST-API & WebSocket
- `uvicorn` – ASGI-Server
- `sqlalchemy` – ORM
- `alembic` – DB-Migrations
- `aiomqtt` – asynchroner MQTT-Client
- `pydantic` – Config-Validierung & API-Schemas
- `mutagen` – Audio-Metadaten-Extraktion
- `structlog` – Logging

**Konfiguration:**

- Globale `.env` (Root):
  - `MINABOX_DEVICE_ID` – Box-ID für MQTT-Topics
  - `MQTT_BROKER`, `MQTT_PORT` – MQTT-Broker-Verbindung
  - `DATABASE_PATH` – z.B. `/data/minabox.db`
  - `AUDIO_STORAGE_PATH` – z.B. `/mnt/audio/tracks`
  - `LOG_LEVEL` – `DEBUG` | `INFO` | `WARNING` | `ERROR`

- Service-spezifisch `config/backend.json`:
  - `api_port` – z.B. `8080`
  - `ws_enabled` – `true` | `false`
  - `session_timeout_min` – Session-Timeout (z.B. `60`)

---

## 6. Fehler & Status

### 6.1 Typische Fehlerfälle

- `tag_not_found` – Tag-ID nicht in Datenbank
- `content_not_found` – Zugeordneter Content (Playlist/Track) existiert nicht mehr
- `database_error` – DB-Verbindung/Schreibfehler
- `service_unreachable` – Audio/RFID-Service antwortet nicht
- `invalid_config` – Config-Validierung fehlgeschlagen
- `file_upload_failed` – Fehler beim Speichern der Upload-Datei
- `metadata_extraction_failed` – Metadaten konnten nicht extrahiert werden (nicht kritisch)

### 6.2 REST Error-Format

Standard-Fehlerformat für alle REST-Endpoints:

```json
{
  "error": {
    "code": "TAG_NOT_FOUND",
    "message": "Tag 04A224BC19 not found in database",
    "details": {
      "tag_id": "04A224BC19"
    }
  }
}
```

HTTP-Status-Codes:

- `200 OK` – Erfolg
- `201 Created` – Ressource erstellt (z.B. Track-Upload, Tag-Mapping)
- `400 Bad Request` – Ungültige Anfrage (z.B. ungültige Config, fehlende Felder)
- `404 Not Found` – Ressource nicht gefunden (z.B. Tag, Playlist, Track)
- `500 Internal Server Error` – Server-/DB-Fehler

### 6.3 Logging

Der Backend loggt strukturiert (structlog, JSON) u.a.:

- `tag_scanned_received` mit `tag_id`, Mapping-Result, `content_type`, `content_id`
- `audio_command_sent` mit Command (`play`, `pause`, etc.) und Payload
- `button_action_received` mit Action (`play_pause`, `next`, etc.)
- `config_update_requested` / `config_update_success` / `config_update_failed` mit Service und Fehlerdetails
- `websocket_connected` / `websocket_disconnected` mit Client-Info
- `database_query` / `database_error` mit Query-Details
- `track_upload_started` / `track_upload_success` / `track_upload_failed` mit Track-ID und Dateiname
- `session_created` / `session_updated` mit Playlist/Track-Info

Die Log-Konfiguration folgt den globalen Logging-Regeln aus dem Framework (structlog, JSON-Logging, Level-Definitionen).

---

## 7. Nicht-Ziele / Abgrenzung

- Keine direkte Hardware-Anbindung (GPIO, I2C, SPI etc.)
- Keine Audio-Dekodierung oder Wiedergabe (Audio-Service)
- Keine Button-Debouncing oder LED-Pattern-Steuerung
- Keine User-Authentication (kann später ergänzt werden für Multi-User-Zugriff)
- Keine Multi-Tenancy (eine Box = eine Backend-Instanz)
- Kein Streaming-Server (Audio-Files werden lokal gespeichert und via Pfad referenziert)
- Keine erweiterten Playlist-Modi (Shuffle, Repeat) in Phase 1 (kann später ergänzt werden)
