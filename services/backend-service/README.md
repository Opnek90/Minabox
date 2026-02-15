text
# Backend Service

**Version:** 0.1.0  
**Letzte Änderung:** 2026-02-15

Zentraler Orchestrierungs- und Datenservice für das Minabox-Projekt.

---

## Übersicht

Der Backend-Service ist das Herzstück der Minabox. Er koordiniert alle anderen Services, verwaltet die Datenbank und fungiert als Brücke zwischen MQTT (intern) und WebSocket/REST (nach außen zur WebUI).

### Hauptaufgaben

- **Datenbank-Management:** Einziger Service mit direktem DB-Zugriff (SQLite)
- **MQTT-WebSocket-Bridge:** Echtzeit-Updates an die WebUI
- **REST-API:** Synchrone Queries und Commands
- **Orchestrierung:** Service-übergreifende Workflows (Tag-Scan → Playlist-Lookup → Audio-Trigger)
- **Config-Management:** Zentrale Verwaltung der Service-Konfigurationen
- **Audio-Upload:** Track-Upload und Metadaten-Extraktion

---

## Architektur

┌─────────────────────────────────────────────────────────┐
│ Backend Service │
├─────────────────────────────────────────────────────────┤
│ REST API (FastAPI) │ WebSocket Manager │
│ ├─ /api/v1/tags │ └─ /ws │
│ ├─ /api/v1/playlists │ │
│ ├─ /api/v1/tracks │ MQTT Client │
│ ├─ /api/v1/audio │ ├─ Subscribe: rfid, audio │
│ └─ /api/v1/health │ └─ Publish: audio commands │
├─────────────────────────────────────────────────────────┤
│ Database (SQLite + SQLAlchemy + Alembic) │
│ ├─ Tags (RFID → Content Mapping) │
│ ├─ Playlists │
│ ├─ Tracks │
│ └─ PlaylistTracks (M:N) │
├─────────────────────────────────────────────────────────┤
│ Session Manager (In-Memory Playback State) │
└─────────────────────────────────────────────────────────┘

text

---

## Technologie-Stack

- **Python:** 3.13+
- **Web Framework:** FastAPI 0.126+
- **ASGI Server:** Uvicorn 0.40+
- **Database:** SQLite + SQLAlchemy 2.0.46+
- **Migrations:** Alembic 1.15+
- **MQTT Client:** aiomqtt 2.5+
- **Logging:** structlog 25.4+
- **Validation:** Pydantic 2.12+
- **Metadata:** mutagen 1.47+

---

## Installation

### Voraussetzungen

- Python 3.13+
- Docker (für Container-Deployment)
- MQTT-Broker (Mosquitto)

### Lokale Entwicklung

```bash
# Repository klonen
cd services/backend-service

# Virtual Environment erstellen
python3.13 -m venv venv
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Datenbank initialisieren
alembic upgrade head

# Service starten
python -m backend_service.main
Docker
bash
# Image bauen
docker build -t minabox/backend:latest .

# Container starten
docker run -d \
  --name backend \
  -p 8080:8080 \
  -e MINABOX_BACKEND_DEVICE_ID=box1 \
  -e MINABOX_BACKEND_MQTT_BROKER=mosquitto \
  -v /data/minabox:/data \
  -v /mnt/audio:/mnt/audio \
  minabox/backend:latest
Konfiguration
Environment Variables (.env)
bash
MINABOX_BACKEND_DEVICE_ID=box1          # Device ID für MQTT-Topics
MINABOX_BACKEND_MQTT_BROKER=mosquitto   # MQTT-Broker Hostname
MINABOX_BACKEND_MQTT_PORT=1883          # MQTT-Broker Port
MINABOX_BACKEND_LOG_LEVEL=INFO          # Logging Level
Service Config (config/backend.json)
json
{
  "api_port": 8080,
  "ws_enabled": true,
  "session_timeout_min": 60,
  "health_check_interval_sec": 30,
  "max_upload_size_mb": 100,
  "audio_storage_path": "/mnt/audio/tracks",
  "database_path": "/data/minabox.db"
}
API-Dokumentation
REST API
Base URL: http://localhost:8080/api/v1

Tags
GET /tags - Liste aller RFID-Tags

GET /tags/{tag_id} - Tag-Details

POST /tags - Tag anlegen (Lern-Modus)

PUT /tags/{tag_id} - Tag aktualisieren

DELETE /tags/{tag_id} - Tag löschen

Playlists
GET /playlists - Liste aller Playlists

GET /playlists/{playlist_id} - Playlist mit Tracks

POST /playlists - Playlist erstellen

PUT /playlists/{playlist_id} - Playlist bearbeiten

DELETE /playlists/{playlist_id} - Playlist löschen

Tracks
GET /tracks - Liste aller Tracks

GET /tracks/{track_id} - Track-Details

POST /tracks - Track erstellen (Stream/Manuell)

POST /tracks/upload - Audio-Datei hochladen

DELETE /tracks/{track_id} - Track löschen

Audio Control
POST /audio/play - Wiedergabe starten

POST /audio/pause - Pause

POST /audio/stop - Stop

POST /audio/next - Nächster Track

POST /audio/prev - Vorheriger Track

POST /audio/volume - Lautstärke setzen

System
GET /health - Health-Check

WebSocket
Endpoint: ws://localhost:8080/ws

Outgoing Messages (Backend → WebUI):

json
{
  "type": "audio_status",
  "data": { "state": "playing", "track_id": 123, ... },
  "timestamp": "2026-02-15T12:00:00Z"
}
json
{
  "type": "rfid_scanned",
  "data": { "tag_id": "04A224BC19", "content_type": "playlist", ... },
  "timestamp": "2026-02-15T12:00:00Z"
}
MQTT-Topics
Subscribe (Backend empfängt)
minabox/<device-id>/rfid/tag-scanned

minabox/<device-id>/rfid/tag-scanned-learning

minabox/<device-id>/audio/status

minabox/<device-id>/button/+ (alle Button-Actions)

Publish (Backend sendet)
minabox/<device-id>/audio/play

minabox/<device-id>/audio/pause

minabox/<device-id>/audio/stop

minabox/<device-id>/audio/next

minabox/<device-id>/rfid/cmd/set-mode

minabox/<device-id>/button/config/update

Datenbank-Schema
Tags
id (PK)

tag_id (UNIQUE, RFID UID)

name (Optional, Human-readable)

content_type ('playlist' | 'track')

content_id (FK zu Playlist oder Track)

Playlists
id (PK)

name

description (Optional)

Tracks
id (PK)

title

artist (Optional)

album (Optional)

duration_ms (Optional, NULL für Streams)

source_type ('file' | 'stream')

source_uri (Dateipfad oder URL)

PlaylistTracks
id (PK)

playlist_id (FK)

track_id (FK)

position (0-basiert, sortiert)

Workflows
1. Tag-Scan → Wiedergabe
Backend empfängt rfid/tag-scanned mit tag_id

Lookup in DB: Tag → Content (Playlist/Track)

Falls Playlist: Lade alle Tracks, erstelle Session

Sende audio/play mit erstem Track an Audio-Service

Pushe Event via WebSocket an WebUI

2. Tag anlernen (Lern-Modus)
WebUI aktiviert Lern-Modus via POST /api/v1/rfid/learning-mode

Backend sendet rfid/cmd/set-mode → learning

RFID-Service scannt Tag, sendet rfid/tag-scanned-learning

Backend prüft, ob Tag existiert

WebUI zeigt Dialog: "Welchem Content zuordnen?"

WebUI sendet POST /api/v1/tags mit Mapping

Backend speichert in DB, deaktiviert Lern-Modus

3. Button → Audio-Control
Backend empfängt button/play-pause

Prüft aktuellen Audio-Status (gecacht)

Sendet entsprechenden Audio-Command (play/pause)

Pushe Action via WebSocket an WebUI

Logging
Strukturiertes JSON-Logging mit structlog:

json
{
  "event": "rfid_tag_scanned_received",
  "tag_id": "04A224BC19",
  "level": "info",
  "timestamp": "2026-02-15T12:00:00Z"
}
Wichtige Events:

backend_service_starting / backend_service_started_successfully

rfid_tag_scanned_received / tag_found / tag_not_found

playlist_playback_started / track_playback_started

api_* (alle API-Calls)

mqtt_* (MQTT-Events)

websocket_* (WebSocket-Events)

Testing
bash
# Unit-Tests
pytest tests/unit

# Integration-Tests
pytest tests/integration

# Mit Coverage
pytest --cov=backend_service tests/
Deployment
Docker Compose
Siehe docker-compose.yml im Root-Repository.

text
services:
  backend:
    build: ./services/backend-service
    ports:
      - "8080:8080"
    environment:
      - MINABOX_BACKEND_DEVICE_ID=box1
      - MINABOX_BACKEND_MQTT_BROKER=mosquitto
    volumes:
      - ./data:/data
      - ./audio:/mnt/audio
    depends_on:
      - mosquitto
Troubleshooting
Service startet nicht
bash
# Logs prüfen
docker logs backend

# Health-Check
curl http://localhost:8080/api/v1/health
MQTT-Verbindung fehlgeschlagen
Prüfe, ob Mosquitto läuft: docker ps | grep mosquitto

Prüfe MQTT_BROKER Environment Variable

Network-Verbindung: docker network inspect minabox-network

Datenbank-Fehler
bash
# Migrations prüfen
alembic current
alembic upgrade head

# Datenbank neu erstellen (ACHTUNG: Löscht alle Daten!)
rm /data/minabox.db
alembic upgrade head
Weitere Dokumentation
Framework.md - Technische Standards

Backend Architecture.md - Detaillierte Architektur

DEVELOPMENT_INSTRUCTIONS.md - Entwicklungsrichtlinien

Maintainer: Minabox Team
Lizenz: MIT
Version: 0.1.0