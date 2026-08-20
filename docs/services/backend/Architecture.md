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
- Asynchroner URL-Import via Media-Downloader-Service

Nicht-Ziele:

- Keine direkte Hardware-Anbindung (GPIO, I2C etc.)
- Keine Audio-Wiedergabe (delegiert an Audio-Service)
- Keine Button-/RFID-Hardware-Logik (nur Event-Verarbeitung)
- Keine User-Authentication (kann später ergänzt werden)
- Keine Multi-Tenancy (eine Box = eine Instanz)

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/backend-service/src/backend_service/`

```text
backend_service/
├── __init__.py              # Package-Init, __version__
├── main.py                  # Einstiegspunkt: Config, Logging, BackendService, SIGTERM/SIGINT, Graceful Shutdown
├── app_factory.py           # FastAPI-App-Factory, BackendService: Router-Mount, CORS, Static, MQTT/API/Podcast/Temperature-Start
├── config.py                # load_app_config(), get_config(): Env, general_settings, backend.json
├── config_manager.py        # Thin Wrapper um shared_lib JsonConfigManager für Backend-Config, Hot-Reload
├── config_schema.py         # Pydantic: EnvConfig, BackendServiceConfig, AppConfig (Session-Timeout, Health-Intervall, Upload-Size)
├── exceptions.py            # Backend-Exception-Hierarchie: MinaboxBackendError, ServiceCommunicationError, MQTT*, DatabaseError, TagNotFoundError, ContentNotFoundError
├── api/
│   ├── __init__.py          # Router-Mount: auth, tags, playlists, tracks, streams, podcasts, audio, rfid, config, stats, system, host unter /api/v1
│   ├── routes_audio.py      # REST Audio: play/pause/stop, volume, Sleep-Timer, Session (repeat/shuffle), Status-Proxy; nutzt MQTT-Handlers
│   ├── routes_config.py     # REST Config für andere Services (LED, Button, RFID, Audio, Display): GET/PUT JSON-Configs, Static-Upload, MQTT-Reload, Element-Typen
│   ├── routes_system.py     # System/Health: Service-Health-URLs, Uptime, DB-Check, MQTT-Connected, System-Status-Response
│   ├── routes_tags.py       # REST RFID-Tags: Liste, Get, Create, Update, Delete (tag_id, name, content_type, content_id)
│   ├── routes_host.py       # Host-Helper-Proxy: Audio-Pfad, Move/Copy, Temperatur, Current-Alert; Pfad-Validierung, erlaubte Basen
│   ├── routes_stats.py      # Listening-Stats (Parent-Dashboard): heute/gesamt (inkl. laufendem Event), minutes_per_day, top_tags, Scan-Counts; general_settings + DB
│   ├── routes_auth.py       # Web-Auth-API: Login/Logout, Passwort-Änderung, geschützte Bereiche; Cookie-Session
│   ├── routes_tracks.py     # REST Tracks: Liste, Get, Create, Update, Delete; Upload, Cover in static/; async URL-Import
│   ├── routes_streams.py    # REST Streams: CRUD inkl. optional Cover
│   ├── routes_podcasts.py   # REST Podcasts: CRUD, neueste Episode in Response
│   ├── routes_playlists.py  # REST Playlists: CRUD, Detail inkl. Tracks und Cover
│   ├── routes_rfid.py       # REST RFID: Lern-Modus an/aus via MQTT-Command
│   └── websocket.py         # WebSocket-Manager: Verbindungen, letzter Audio-Status, Broadcast (audio_status, rfid_scanned, button_action, …)
├── core/
│   ├── __init__.py          # Re-Export: DatabaseManager, get_db, init_db, MQTTClient, PlaybackSession, SessionManager, session_manager
│   ├── mqtt_handlers.py     # MQTT-Handler: RFID (Scan/Learning/Removed/Presence), Audio-Status, Button-Actions, Playback-Events, Sleep-Timer, Bedtime-Fade, Loop-Guard, Stream-Reconnect
│   ├── mqtt_client.py       # MQTT-Client: Reconnect/Retry, Subscriptions (RFID/Audio/Button), Dispatch an MQTTHandlers, Publish Audio/RFID-Commands
│   ├── db_manager.py        # SQLite: Engine, Sessions, WAL, Foreign Keys; DatabaseManager, get_db, init_db
│   ├── session_manager.py   # In-Memory Playback-Session: PlaybackSession/SessionTrack, current_track_index, Shuffle, Repeat, Schleifen-Zustand (loop_requires_tag, loop_started_at); SessionManager, session_manager
│   ├── sleep_settings.py    # Liest sleep_timer_minutes und Bedtime-Fade (Dauer, Intervall, Step) aus general_settings.json
│   ├── playback_settings.py # Liest playback_end_behavior (stop|repeat|repeat_while_tag) und playback_loop_guard_minutes aus general_settings.json
│   ├── usage_limits.py      # Eltern/Nutzung: erlaubte Zeiten und Daily-Limit aus general_settings; Prüfung ob aktuell erlaubt; Stop-on-Tag-Remove
│   ├── playback_stats.py    # Playback-Statistik: minutes_for_event, get_today_listened_minutes, get_total_listened_minutes, get_live_listened_minutes aus PlaybackEvent
│   ├── podcast_fetcher.py   # Hintergrund-Loop: Podcast-RSS fetchen, Episoden parsen, in DB upserten (Podcast/PodcastEpisode)
│   ├── temperature_logger.py # Hintergrund-Loop: Host-Temperatur via Host-Helper lesen, in DB loggen, bei Überhitzung MQTT/WebSocket
│   └── auth.py              # Web-Auth: auth_settings lesen/schreiben (Passwort-Hash, geschützte Bereiche), bcrypt, JWT-Session
├── infrastructure/
│   └── media_downloader_client.py  # HTTP-Client für Media-Downloader-Service; Retry-Logik (3x, linearer Backoff)
└── models/
    ├── __init__.py          # Re-Export Schemas und Modell-Typen für backend_service.models
    ├── database.py          # SQLAlchemy-Modelle: PlaybackEvent, Tag, Track, Playlist, PlaylistTrack, Stream, Podcast, PodcastEpisode, TemperatureReading
    ├── schemas.py           # Re-Export Pydantic-Schemas aus Domain-Modulen (audio, config, content, error, rfid, system, ws, enums)
    ├── schemas_error.py     # Pydantic ErrorDetail, ErrorResponse für API-Fehler
    ├── schemas_ws.py        # Pydantic WebSocketMessage (type, data, timestamp)
    ├── schemas_rfid.py      # Pydantic RFID: RFIDLearningModeCommand, RFIDScanEvent, RFIDModeResponse
    ├── schemas_system.py    # Pydantic System: HealthCheckResponse, ServiceStatus, SystemStatusResponse
    ├── schemas_config.py    # Pydantic Config: ButtonConfig, LEDConfig, RFIDConfig, AudioConfig für andere Services
    ├── schemas_audio.py     # Pydantic Audio: AudioPlayCommand, AudioVolumeCommand, AudioStatusResponse
    ├── schemas_content.py   # Pydantic Content: Tag, Playlist, Track, Stream, Podcast Base/Create/Update/Response
    └── schemas_enums.py     # Enums: ContentType, SourceType, AudioState, ServiceState, RFIDMode
```

---

## 3. Öffentliche Schnittstellen

### 3.1 REST-API

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
- `POST /api/v1/tracks` – Track anlegen (JSON, z.B. manuelle File-Einträge oder Remote-Tracks)
- `POST /api/v1/tracks/from-url` – Track asynchron von URL importieren → **HTTP 202**, Background-Download
- `GET /api/v1/tracks/{track_id}/download-status` – Download-Fortschritt eines via `from-url` importierten Tracks
- `PUT /api/v1/tracks/{track_id}` – Track-Metadaten bearbeiten
- `DELETE /api/v1/tracks/{track_id}` – Track löschen (inkl. Datei bei source_type="file")

**Streams (Webradio, eigene Ressource):**

- `GET /api/v1/streams` – Liste aller Streams
- `GET /api/v1/streams/{stream_id}` – Stream-Details
- `POST /api/v1/streams` – Neuen Stream anlegen (title, artist, source_uri)
- `PUT /api/v1/streams/{stream_id}` – Stream bearbeiten
- `DELETE /api/v1/streams/{stream_id}` – Stream löschen

**Podcasts:**

- `GET /api/v1/podcasts` – Liste aller Podcasts (inkl. neueste Episode)
- `GET /api/v1/podcasts/{podcast_id}` – Podcast-Details inkl. Episoden
- `POST /api/v1/podcasts` – Podcast anlegen (RSS-URL, Titel, optional Cover-Upload)
- `PUT /api/v1/podcasts/{podcast_id}` – Podcast bearbeiten
- `DELETE /api/v1/podcasts/{podcast_id}` – Podcast löschen
- Episoden werden per RSS-Fetch (podcast_fetcher) aktualisiert; Abspielen wie Tracks

**Audio-Control:**

- `POST /api/v1/audio/play` – Wiedergabe starten (optional mit track_id oder playlist_id)
- `POST /api/v1/audio/pause` – Wiedergabe pausieren
- `POST /api/v1/audio/stop` – Wiedergabe stoppen
- `POST /api/v1/audio/next` – Nächster Track
- `POST /api/v1/audio/prev` – Vorheriger Track
- `POST /api/v1/audio/volume` – Lautstärke setzen
- `GET /api/v1/audio/status` – Aktueller Wiedergabe-Status
- `GET /api/v1/audio/sleep-timer` – Sleep-Timer-Status abrufen
- `POST /api/v1/audio/sleep-timer` – Sleep-Timer starten (Payload: z.B. `minutes`)
- `DELETE /api/v1/audio/sleep-timer` – Sleep-Timer abbrechen
- `POST /api/v1/audio/seek` – Seek auf Position innerhalb des aktuellen Tracks (Payload: `position_ms`)
- `GET /api/v1/audio/session` – Aktuelle Queue/Session (repeat_mode, shuffle) für „What's next"
- `POST /api/v1/audio/repeat` – Repeat-Modus setzen (`none` | `all`)
- `POST /api/v1/audio/shuffle` – Shuffle für die aktuelle Session setzen (Payload: `shuffle: bool`)
- `GET /api/v1/audio/devices` – Erkannte PulseAudio/PipeWire-Sinks auflisten (Query: `enabled_only`)
- `POST /api/v1/audio/switch-device` – Audio-Output auf einen Sink wechseln (Body: `sink_name` oder `alsa_device`, optional `direction: "next"`)

**RFID-Control:**

- `POST /api/v1/rfid/learning-mode` – Lern-Modus aktivieren/deaktivieren

**Service-Config:**

- `GET /api/v1/config/buttons` – Button-Konfiguration abrufen
- `PUT /api/v1/config/buttons` – Button-Konfiguration aktualisieren
- `GET /api/v1/config/buttons/actions` – Liste aller unterstützten Button-Aktionen (für Admin-UI Auswahl)
- `GET /api/v1/config/leds` – LED-Konfiguration abrufen
- `PUT /api/v1/config/leds` – LED-Konfiguration aktualisieren
- `GET /api/v1/config/leds/states` – Liste aller unterstützten LED-„Logical States" (Binding IDs)
- `GET /api/v1/config/leds/patterns` – Liste aller unterstützten LED-Pattern-Typen
- `GET /api/v1/config/audio` – Audio-Konfiguration abrufen
- `PUT /api/v1/config/audio` – Audio-Konfiguration aktualisieren
- `GET /api/v1/config/rfid` – RFID-Konfiguration abrufen
- `PUT /api/v1/config/rfid` – RFID-Konfiguration aktualisieren
- `GET /api/v1/config/display` – Display-Konfiguration abrufen
- `PUT /api/v1/config/display` – Display-Konfiguration aktualisieren
- `GET /api/v1/config/display/element-types` – Verfügbare Display-Element-Typen (z.B. volume, sleep_timer, clock)
- `GET /api/v1/config/general` – Allgemeine Einstellungen (Sprache, Theme, Device-ID, MQTT, Sleep-Timer etc.)
- `PUT /api/v1/config/general` – Allgemeine Einstellungen aktualisieren
- `POST /api/v1/config/logo` – Logo-Bild hochladen (multipart)
- `DELETE /api/v1/config/logo` – Logo löschen

**Stats (Parent Dashboard / Nutzungsstatistik):**

- `GET /api/v1/stats/overview` – Übersicht: Hörminuten heute/gesamt, Daily-Limit, Anzahl Tags/Playlists/Tracks/Streams/Podcasts. `minutes_today` enthält abgeschlossene Events **und** den laufenden Zwischenstand (`listened_ms`) des aktiven Events (max. ~60 s veraltet).
- `GET /api/v1/stats/usage-today` – Heutige Hörminuten und Daily-Limit (daily_limit_enabled, daily_limit_minutes aus general_settings.json). Gleiche Live-Logik wie `/overview`. **Hinweis:** Das Daily-Limit-Enforcement in `usage_limits.py` verwendet weiterhin nur abgeschlossene Events, um laufende Wiedergabe nicht vorzeitig zu unterbrechen.
- `GET /api/v1/stats/listening-summary` – Detaillierte Statistik: minutes_per_day, top_tags, top_playlists, heatmap (für Parent Dashboard). Nur abgeschlossene Events.

**System & Health:**

- `GET /health` – Backend-Health (Root-Endpoint)
- `GET /api/v1/system/health` – Backend-Health (DB + MQTT-Connectivity)
- `GET /api/v1/system/status` – Gesamtsystem-Status (alle Services inkl. CPU/RAM wenn verfügbar)
- `GET /api/v1/system/logs?service=<id>&tail=200` – Logs eines Service-Containers (backend, mqtt, audio, rfid, button, led, display, webui). Quelle: Host-Helper `GET /container-logs` oder Docker-API/Fallback. Response: `{ "service", "lines", "tail" }`.
- `POST /api/v1/system/restart` – Alle Minabox-Container neustarten (Delegation an Host-Helper `/restart`)

**Host-Operationen (Delegation an Host-Helper):**

- `GET /api/v1/system/host-status` – Host-Status (Hostname, IP, RAM, CPU, Disk, Load, Temperatur)
- `GET /api/v1/system/temperature-history?hours=24` – Temperaturverlauf (Zeitreihe aus DB, letzte N Stunden)
- `GET /api/v1/system/current-alert` – Aktuell aktiver System-Alert (z.B. Überhitzung) für die WebUI-Bar
- `GET /api/v1/system/audio-path` – Aktueller Audio-Pfad (vom Host: AUDIO_FILES_PATH)
- `PUT /api/v1/system/audio-path` – Audio-Pfad setzen (Payload: `path`); Host-Helper schreibt `.env`
- `POST /api/v1/system/move-audio` – Medien-Ordner verschieben (source, destination)
- `GET /api/v1/system/move-status` – Status der Verschiebung (idle | running | done | error, Fortschritt)
- `POST /api/v1/system/reboot` – Host-Neustart
- `POST /api/v1/system/shutdown` – Host herunterfahren
- **WiFi:** `GET /api/v1/system/wifi/scan`, `POST /api/v1/system/wifi/connect`, `POST /api/v1/system/wifi/hotspot/start`, `POST /api/v1/system/wifi/hotspot/stop`, `GET /api/v1/system/wifi/hotspot/status`
- **USB:** `GET /api/v1/system/usb/devices`, `GET /api/v1/system/usb/{device_id}/files`, `POST /api/v1/system/usb/import`, `POST /api/v1/system/usb/eject`
- **Backup:** `GET /api/v1/system/backup/download` (ZIP), `POST /api/v1/system/backup/restore` (ZIP-Upload)
- **Zeit:** `GET /api/v1/system/time-status`, `PUT /api/v1/system/timezone`
- **Hostname:** `GET /api/v1/system/hostname`, `PUT /api/v1/system/hostname`
- **Board-LEDs (Stealth):** `GET /api/v1/system/board-leds`, `PUT /api/v1/system/board-leds` (stealth: true/false)
- **Netzwerk:** `GET /api/v1/system/network`, `PUT /api/v1/system/network` (DHCP/manual, address, gateway, dns)
- **Passwort:** `POST /api/v1/system/password` (System-User z.B. pi)
- **SSH:** `GET /api/v1/system/ssh-status`, `POST /api/v1/system/ssh-toggle`
- **Factory Reset:** `POST /api/v1/system/factory-reset` (optional delete_audio)
- **Update:** `POST /api/v1/system/update-minabox` (docker compose pull && up -d), `GET /api/v1/system/version` (Commit, update_available), `POST /api/v1/system/update-os`, `GET /api/v1/system/update-os/log`
- **Syslog:** `GET /api/v1/system/syslog?n=200&source=kernel|docker`
- **Docker:** `POST /api/v1/system/docker-prune`
- **Bluetooth:** `GET /api/v1/system/bluetooth/scan`, `POST /api/v1/system/bluetooth/pair`, `GET /api/v1/system/bluetooth/paired`, `POST /api/v1/system/bluetooth/connect`, `POST /api/v1/system/bluetooth/disconnect`, `POST /api/v1/system/bluetooth/remove`

### 3.2 WebSocket

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
    "track_title": "Optional: resolved track title",
    "track_artist": "Optional: resolved artist",
    "track_album": "Optional: resolved album",
    "track_cover_art_url": null,
    "playlist_position": 1,
    "playlist_total": 10
  }
  "timestamp": "2026-02-14T21:20:00Z"
}
```

RFID (Normal-Modus):

```json
{
  "type": "rfid_scanned",
  "data": {
    "tag_id": "04A224BC19",
    "content_type": "track|playlist|stream|podcast",
    "content_name": "Optional: resolved tag content name",
    "content_id": 5,
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
    "already_assigned": false,
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Tag nicht gefunden:

```json
{
  "type": "tag_not_found",
  "data": {
    "tag_id": "04A224BC19",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Blockierter Tag:

```json
{
  "type": "tag_blocked",
  "data": {
    "tag_id": "04A224BC19",
    "name": "Optional: tag name",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Usage-Denied (Parental/Daily-Limit außerhalb erlaubter Zeit):

```json
{
  "type": "usage_denied",
  "data": {
    "tag_id": "04A224BC19",
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
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Button-Raw-Event (wird für WebUI Hardware-Testmodus verwendet):

```json
{
  "type": "button_raw_event",
  "data": {
    "button_id": "btn_1",
    "name": "Optional: button name",
    "event_type": "short_press|long_press|double_press|rotate_cw|rotate_ccw|press",
    "timestamp": "2026-02-14T21:20:00Z"
  }
}
```

Repeat-Modus:

```json
{
  "type": "repeat_mode",
  "data": {
    "repeat_mode": "none|all"
  },
  "timestamp": "2026-02-14T21:20:00Z"
}
```

Shuffle-Modus:

```json
{
  "type": "shuffle_mode",
  "data": {
    "shuffle": false
  },
  "timestamp": "2026-02-14T21:20:00Z"
}
```

Sleep-Timer-Status:

```json
{
  "type": "sleep_timer_status",
  "data": { "active": true, "remaining_ms": 600000 },
  "timestamp": "2026-02-14T21:20:00Z"
}
```

System-Alert (z.B. Überhitzung; WebUI zeigt globale Alert-Bar):

```json
{
  "type": "system_alert",
  "level": "warning",
  "code": "temperature_high",
  "message": "alerts.temperature_high",
  "timestamp": "2026-02-14T21:20:00Z"
}
```

System-Alert gelöscht:

```json
{
  "type": "system_alert_cleared",
  "code": "temperature_high",
  "timestamp": "2026-02-14T21:20:00Z"
}
```

**Incoming Messages (WebUI → Backend):**

Aktuell verarbeitet das Backend keine Commands, sondern versucht lediglich, eingehenden Text als JSON zu parsen. Wenn das gelingt, sendet es einen `ack` zurück (Commands via WebSocket sind in dieser Implementierung nicht aktiv):

```json
{
  "type": "ack",
  "message": "Received",
  "timestamp": "2026-02-14T21:20:00Z"
}
```

### 3.3 MQTT – Subscribe Topics

Der Backend subscribed auf folgende MQTT-Topics:

**RFID:**

- `minabox/<device-id>/rfid/tag-scanned`
- `minabox/<device-id>/rfid/tag-scanned-learning`
- `minabox/<device-id>/rfid/tag-removed`
- `minabox/<device-id>/rfid/presence` (retained; liegt gerade eine Karte auf dem Leser?)
- `minabox/<device-id>/rfid/status`

**Audio:**

- `minabox/<device-id>/audio/status`
- `minabox/<device-id>/audio/position-report`

**Button:**

- `minabox/<device-id>/button/+` (alle Button-Actions)
- `minabox/<device-id>/button/raw-event`

**(keine weiteren Subscribe-Topics für LED/System in dieser Implementierung)**

### 3.4 MQTT – Publish Topics

**Audio-Commands:**

- `minabox/<device-id>/audio/play`
- `minabox/<device-id>/audio/pause`
- `minabox/<device-id>/audio/stop`
- `minabox/<device-id>/audio/next`
- `minabox/<device-id>/audio/prev`
- `minabox/<device-id>/audio/set-volume`
- `minabox/<device-id>/audio/volume-up`
- `minabox/<device-id>/audio/volume-down`
- `minabox/<device-id>/audio/mute-toggle`
- `minabox/<device-id>/audio/switch-device`

**RFID-Commands:**

- `minabox/<device-id>/rfid/cmd/set-mode`
- *(Reload-Konfiguration ist für RFID in der aktuellen Implementierung nicht über `cmd/reload-config` abgebildet.)*

**Config-Updates:**

- `minabox/<device-id>/button/config/reload` (Payload: `{}`)
- `minabox/<device-id>/led/config/reload` (Payload: `{}`)
- `minabox/<device-id>/audio/config/reload` (Payload: `{}`)
- `minabox/<device-id>/display/config/reload` (Payload: `{}`)
- `minabox/<device-id>/config/general` (retained; z.B. `log_level`)

**System/Usage Events:**

- `minabox/<device-id>/system/service-error` (z.B. Temperatur-Überhitzung)
- `minabox/<device-id>/system/service-started` (z.B. Temperatur normalisiert)
- `minabox/<device-id>/led/usage-denied` (Payload: `{ "event": "usage_denied", "timestamp": "..." }`)

### 3.5 System-/Host-Operationen

Aktionen, die direkt auf dem Host ausgeführt werden müssen (z.B. Dateien verschieben, später ggf. Netz- oder Mount-Konfiguration), werden **nicht** vom Backend selbst ausgeführt. Das Backend delegiert solche Anfragen an den **Host-Helper-Service**, der mit erweiterten Rechten läuft und nur intern erreichbar ist. Das Backend validiert die von der WebUI übergebenen Parameter und leitet sie an den Host-Helper weiter; Host-Details oder Fehler des Host-Helpers werden nicht ungefiltert an die WebUI durchgereicht. Details zu Rolle, Sicherheit und Schnittstelle des Host-Helpers: [docs/services/host-helper/Architecture.md](../host-helper/Architecture.md).

---

## 4. Datenbank-Schema

Der Backend verwendet SQLite mit SQLAlchemy und Alembic für Migrations.

### 4.1 Tags

```python
class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    tag_id = Column(String, unique=True, nullable=False, index=True)  # z.B. "04A224BC19"
    name = Column(String, nullable=True)  # z.B. "Benjamin Blümchen"
    content_type = Column(String, nullable=False)  # "playlist" | "track" | "stream"
    content_id = Column(Integer, nullable=False)  # Playlist-ID, Track-ID oder Stream-ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### 4.2 Playlists

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

### 4.3 Streams

```python
class Stream(Base):
    __tablename__ = "streams"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    source_uri = Column(String, nullable=False)
    cover_art_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_played_at = Column(DateTime, nullable=True)
```

Streams sind eigenständige Webradio-/Stream-Einträge (nicht in Playlists). Tags können auf Streams verweisen (content_type="stream", content_id=stream_id).

### 4.4 Tracks

```python
class Track(Base):
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    album = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    source_type = Column(String, nullable=False)  # "file" | "remote"
    source_uri = Column(String, nullable=False)  # Pfad oder URL
    cover_art_url = Column(String, nullable=True)  # /static/covers/track_{id}.jpg|.png
    created_at = Column(DateTime, default=datetime.utcnow)
    last_played_at = Column(DateTime, nullable=True)
```

### 4.5 Podcasts & Episoden

```python
class Podcast(Base):
    __tablename__ = "podcasts"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    feed_url = Column(String, nullable=False)
    cover_art_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_fetched_at = Column(DateTime, nullable=True)

class PodcastEpisode(Base):
    __tablename__ = "podcast_episodes"
    
    id = Column(Integer, primary_key=True)
    podcast_id = Column(Integer, ForeignKey("podcasts.id"), nullable=False)
    title = Column(String, nullable=False)
    source_uri = Column(String, nullable=False)  # Audio-URL
    published_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Podcast-Episoden werden per **podcast_fetcher** (RSS-Fetch-Loop, z.B. täglich) aktualisiert. Abspielen erfolgt wie bei Tracks (source_uri an Audio-Service).

### 4.6 PlaybackEvent (Statistik)

```python
class PlaybackEvent(Base):
    __tablename__ = "playback_events"
    
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=True)
    stream_id = Column(Integer, ForeignKey("streams.id"), nullable=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), nullable=True)
    podcast_id = Column(Integer, ForeignKey("podcasts.id"), nullable=True)
    content_type = Column(String(16), nullable=False)  # 'playlist' | 'track' | 'stream' | 'podcast'
```

Wird für **Stats API** (Parent Dashboard: Hörminuten, Top-Tags, Top-Playlists, Heatmap) und Daily-Limit (general_settings: daily_limit_enabled, daily_limit_minutes) genutzt.

**Hinweis Playback-Statistik:** `listened_ms` wird während der Wiedergabe ca. alle 60 Sekunden vom `AudioHandler._flush_loop` aktualisiert (offenes Event, `ended_at IS NULL`). Nach Stop wird das Event mit dem finalen `listened_ms`-Wert und `ended_at` abgeschlossen. `GET /api/v1/stats/overview` und `GET /api/v1/stats/usage-today` addieren beide Quellen (`get_today_listened_minutes` + `get_live_listened_minutes`), um die laufende Hörsession im Dashboard sichtbar zu machen. Das Daily-Limit-Enforcement verwendet ausschließlich abgeschlossene Events.

### 4.7 PlaylistTrack (M:N)

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

### 4.8 Playlist (Cover)

Playlist hat optional `cover_art_url`; Stream und Track haben optional `cover_art_url`. Cover-Bilder werden unter `STATIC_DIR/covers/` gespeichert.

### 4.9 TemperatureReadings (Systemtemperatur)

Die Systemtemperatur des Raspberry Pi wird periodisch (z.B. alle 5 Minuten) vom Backend aus dem Host-Status (Host-Helper) gelesen und in der Tabelle `temperature_readings` gespeichert. Überhitzungswarnungen nutzen das bestehende MQTT-Topic `system/service-error` (LED/Display); die WebUI zeigt einen globalen Alert-Balken (SystemAlertBar) über dem Header.

```python
class TemperatureReading(Base):
    __tablename__ = "temperature_readings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at = Column(DateTime, nullable=False)  # UTC, timezone-aware
    temperature_celsius = Column(Float, nullable=False)
```

- **Retention:** Einträge älter als z.B. 30 Tage werden vom Temperature-Log-Task gelöscht.
- **Überhitzung:** Schwellwert in `general_settings.json` (`temperature_warning_celsius`, Default 80). Bei Überschreitung: Backend publiziert MQTT `minabox/<device-id>/system/service-error` (Payload z.B. `code: "temperature_high"`); LED/Display reagieren wie bei anderen System-Fehlern. Bei Unterschreiten: Backend publiziert `system/service-started`. Zusätzlich sendet das Backend WebSocket `system_alert` / `system_alert_cleared` an die WebUI; `GET /api/v1/system/current-alert` liefert den aktuellen Alert für Reload/Tab-Wechsel.

### 4.10 Alembic Migrations

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
alembic revision --autogenerate -m "Add temperature_readings table"
```

**Migrations anwenden:**

```bash
alembic upgrade head
```

Beim Service-Start wird automatisch `alembic upgrade head` ausgeführt, um sicherzustellen, dass die DB aktuell ist.

---

## 5. Kern-Funktionen / Workflows

### 5.1 Tag-Scan → Wiedergabe (Normal-Modus)

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
6. Falls `content_type == "stream"`:
   - Lade Stream-Details (source_uri).
   - Erstelle Session mit einem „virtuellen" Track (Stream-URI).
7. Sende `minabox/<device-id>/audio/play` mit Track-/Stream-Daten (`source_type`, `source_uri`, `start_position_ms=0`) an Audio-Service.
8. Pushe Event via WebSocket an WebUI.

### 5.2 Tag anlernen (Lern-Modus)

Ablauf:

1. WebUI aktiviert Lern-Modus via `POST /api/v1/rfid/learning-mode` mit `{"enabled": true}`.
2. Backend sendet `minabox/<device-id>/rfid/cmd/set-mode` mit Payload `{"mode": "learning"}`.
3. RFID-Service wechselt in Lern-Modus.
4. Backend empfängt `minabox/<device-id>/rfid/tag-scanned-learning` mit `tag_id`.
5. Backend prüft, ob Tag bereits in DB existiert.
6. Backend pusht Event via WebSocket.
7. WebUI zeigt Dialog: "Welchem Content soll dieser Tag zugeordnet werden?"
8. User wählt Playlist oder Track aus.
9. WebUI sendet `POST /api/v1/tags` mit Tag-Daten.
10. Backend speichert Tag-Mapping in DB.
11. Backend deaktiviert Lern-Modus.

### 5.3 Button-Action → Audio-Control

Ablauf wie bisher (play/pause/next/prev via MQTT).

### 5.4 Next/Prev – Playlist-Navigation

Ablauf wie bisher (Playback-Session im Memory).

**Ende des Inhalts.** Läuft der letzte Titel aus, meldet der Audio-Service `stopped`;
`AudioHandler` ruft `ButtonHandler._handle_next()` – sofern der Stopp nicht bewusst ausgelöst
wurde. Das `deliberate_stop`-Flag wird bei *jedem* Stopp-Übergang einmal verbraucht: Jeder
bewusste Stopp löscht gleichzeitig `playback_intent_active`, und solange nur der
`deliberate_stop`-Zweig zurücksetzte, blieb das Flag stehen und verschluckte das nächste
natürliche Titelende. Ist kein nächster Titel da, entscheidet
`_loop_decision()` anhand von `playback_end_behavior` aus `general_settings.json`:

| Wert | Verhalten |
|---|---|
| `stop` (Default) | `stop` an den Audio-Service, wie bisher |
| `repeat` | Session zurück auf Titel 1 und erneut abspielen |
| `repeat_while_tag` | wie `repeat`, aber nur solange `rfid/presence` eine aufliegende Karte meldet |

Mit der ersten Wiederholung startet `TimerHandler.start_loop_guard()` einen Timer über
`playback_loop_guard_minutes` (0 = aus). Läuft er ab, blendet `fade_out_and_stop()` die
Lautstärke aus und stoppt – damit eine liegengebliebene Karte die Box nicht stundenlang
spielen lässt. Der Timer wird von `mark_deliberate_stop()` abgeräumt und prüft beim Auslösen,
ob noch dieselbe Session läuft und ob überhaupt noch wiederholt wird. `_loop_decision()` prüft
dieselbe Grenze zusätzlich am Titelübergang, als Rückfallebene.

`fade_out_and_stop()` ist der gemeinsame Weg für alle Fälle, in denen die Box von sich aus
aufhört (Sleep-Timer, Tageslimit, Schleifen-Sperre). Zwei Eigenheiten dabei:

- Der Ausblend-Lauf bricht ab, sobald `playback_intent_active` weg ist – der Inhalt kann
  mitten im Ausblenden auslaufen, und ohne diesen Abbruch würde weiter an der Lautstärke
  gedreht, obwohl längst nichts mehr läuft.
- Nach dem Stopp wird die Ausgangslautstärke wiederhergestellt (`volume_before_fade`).
  Sonst bliebe die Box nach jedem Ausblenden stumm und wirkt beim nächsten Einschalten defekt.

### 5.5 Config-Management

Ablauf wie bisher (Pydantic-Validierung, JSON-Datei, MQTT-Reload).

### 5.6 Audio-Upload

Ablauf wie bisher (multipart upload, mutagen-Metadaten, Track-Verzeichnis).

### 5.7 Asynchroner URL-Import (`POST /tracks/from-url`)

**Endpoint:** `POST /api/v1/tracks/from-url?url=<url>`

**Ablauf:**

1. Domain-Whitelist-Check (`_check_allowed_domain`).
2. Playlist-Parameter aus URL entfernen (`_strip_playlist_params`).
3. Duplikat-Check: Existiert bereits ein Track mit gleicher `source_uri`? → HTTP 200 mit `{"track_id": ..., "status": "done"}`.
4. Placeholder-Track in DB anlegen (`title="..."`, `source_type="file"`, `source_uri=clean_url`).
5. Track-Verzeichnis anlegen: `AUDIO_STORAGE_PATH/{track_id}/`.
6. Status-Eintrag im In-Memory-Dict: `_download_status[track_id] = {"status": "pending", "error": None}`.
7. `asyncio.create_task(_run_download_task(...))` – Background-Task mit eigener DB-Session.
8. Sofort HTTP 202 zurückgeben: `{"track_id": track_id, "status": "pending"}`.

**Background-Task `_run_download_task`:**

1. Status auf `"downloading"` setzen.
2. `MediaDownloaderClient.download_video()` aufrufen (mit Retry-Logik).
3. Track in DB aktualisieren: `title`, `artist`, `album`, `duration_ms`, `source_uri` (MP3-Pfad).
4. Cover Art ermitteln:
   - Primär: `_extract_cover_art()` – eingebettetes APIC/pictures aus MP3 via mutagen
   - Fallback: `_download_thumbnail()` – `thumbnail`-URL aus yt-dlp-Ergebnis via httpx
   - Speicherort: `STATIC_DIR/covers/track_{id}.jpg|.png`
5. `cover_art_url` in DB schreiben.
6. Status auf `"done"` setzen.
7. Bei Fehler: Status auf `"error"` setzen, Placeholder-Track und Verzeichnis löschen.

**In-Memory Status-Dict:**

```python
# Modul-Level:
_download_status: dict[int, dict] = {}
# Eintrag: { "status": "pending" | "downloading" | "done" | "error", "error": str | None }
```

> **Hinweis:** Das Dict lebt nur im Prozess-Memory. Nach einem Service-Neustart sind laufende Status-Einträge verloren. Der `/download-status`-Endpoint gibt dann `"unknown"` zurück.

### 5.8 Download-Status-Endpoint (`GET /tracks/{id}/download-status`)

**Endpoint:** `GET /api/v1/tracks/{track_id}/download-status`

**Response:**

```json
{
  "track_id": 42,
  "status": "downloading",
  "error": null
}
```

**Status-Werte:**

| Wert | Bedeutung |
|---|---|
| `pending` | Task eingereiht, noch nicht gestartet |
| `downloading` | Import läuft |
| `done` | Download abgeschlossen; Track vollständig in DB |
| `error` | Download fehlgeschlagen; `error`-Feld enthält den Grund |
| `unknown` | Kein Status-Eintrag (Track nicht via `from-url` importiert oder Service-Neustart) |

- Bei unbekannter `track_id` → HTTP 404.
- Der Endpoint liegt **vor** dem generischen `GET /{track_id}`-Handler, da FastAPI Routen in Reihenfolge matched.

---

## 6. Abhängigkeiten

**Services:**

- RFID-Service (Tag-Events)
- Audio-Service (Wiedergabe-Commands & Status)
- Button-Service (Action-Events, Config-Responses)
- LED-Service (Config-Responses, optional)
- WebUI-Service (REST/WebSocket Client)
- Media-Downloader-Service (URL-Import, via `MediaDownloaderClient`)

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
- `mutagen` – Audio-Metadaten-Extraktion & Cover-Art-Extraktion
- `httpx` – Async HTTP-Client (Media-Downloader + Thumbnail-Download)
- `structlog` – Logging

**Konfiguration:**

- Globale `.env` (Root):
  - `MINABOX_DEVICE_ID` – Box-ID für MQTT-Topics
  - `MQTT_BROKER`, `MQTT_PORT` – MQTT-Broker-Verbindung
  - `DATABASE_PATH` – z.B. `/data/minabox.db`
  - `AUDIO_STORAGE_PATH` – z.B. `/mnt/audio/tracks`
  - `STATIC_DIR` – z.B. `/data/static` (Cover Art unter `STATIC_DIR/covers/`)
  - `MEDIA_DOWNLOADER_URL` – z.B. `http://media-downloader:8007`
  - `LOG_LEVEL` – `DEBUG` | `INFO` | `WARNING` | `ERROR`

- Service-spezifisch `config/backend.json`:
  - `api_port` – z.B. `8080`
  - `ws_enabled` – `true` | `false`
  - `session_timeout_min` – Session-Timeout (z.B. `60`)

---

## 7. Fehler & Status

### 7.1 Typische Fehlerfälle

- `tag_not_found` – Tag-ID nicht in Datenbank
- `content_not_found` – Zugeordneter Content (Playlist/Track) existiert nicht mehr
- `database_error` – DB-Verbindung/Schreibfehler
- `service_unreachable` – Audio/RFID-Service antwortet nicht
- `invalid_config` – Config-Validierung fehlgeschlagen
- `file_upload_failed` – Fehler beim Speichern der Upload-Datei
- `metadata_extraction_failed` – Metadaten konnten nicht extrahiert werden (nicht kritisch)
- `domain_not_allowed` – URL-Domain nicht in `_ALLOWED_DOMAINS` (HTTP 400)
- `download_failed` – Media-Downloader-Fehler nach Retries (Background-Task setzt Status auf `error`)

### 7.2 REST Error-Format

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
- `202 Accepted` – Asynchroner Download gestartet (`POST /tracks/from-url`)
- `400 Bad Request` – Ungültige Anfrage (z.B. ungültige Config, Domain nicht erlaubt)
- `404 Not Found` – Ressource nicht gefunden (z.B. Tag, Playlist, Track)
- `500 Internal Server Error` – Server-/DB-Fehler

### 7.3 Logging

Der Backend loggt strukturiert (structlog, JSON) u.a.:

- `tag_scanned_received` mit `tag_id`, Mapping-Result, `content_type`, `content_id`
- `audio_command_sent` mit Command (`play`, `pause`, etc.) und Payload
- `button_action_received` mit Action (`play_pause`, `next`, etc.)
- `config_update_requested` / `config_update_success` / `config_update_failed` mit Service und Fehlerdetails
- `websocket_connected` / `websocket_disconnected` mit Client-Info
- `database_query` / `database_error` mit Query-Details
- `track_upload_started` / `track_upload_success` / `track_upload_failed` mit Track-ID und Dateiname
- `session_created` / `session_updated` mit Playlist/Track-Info
- `api_create_track_from_url_accepted` mit `track_id` und `url`
- `download_task_completed` / `download_task_failed` / `download_task_unexpected_error` mit `track_id`
- `track_thumbnail_downloaded` / `track_thumbnail_download_failed` mit `track_id` und `url`
- `track_cover_extract_failed` mit `track_id`
- `media_downloader_download_5xx_retry` / `media_downloader_download_transient_retry` mit `attempt`
- `playback_stats_flushed` mit `event_id` und `ms` (live flush alle 60 s)

---

## 8. Nicht-Ziele / Abgrenzung

- Keine direkte Hardware-Anbindung (GPIO, I2C, SPI etc.)
- Keine Audio-Dekodierung oder Wiedergabe (Audio-Service)
- Keine Button-Debouncing oder LED-Pattern-Steuerung
- Keine User-Authentication (kann später ergänzt werden für Multi-User-Zugriff)
- Keine Multi-Tenancy (eine Box = eine Backend-Instanz)
- Kein Streaming-Server (Audio-Files werden lokal gespeichert und via Pfad referenziert)
- Keine erweiterten Playlist-Modi (Shuffle, Repeat) in Phase 1 (kann später ergänzt werden)

---

## 9. Refactoring-Checkliste

- [ ] **core/mqtt_handlers.py aufteilen:** Die Datei bündelt RFID (Tag-Scan, Learning, Tag-Removed), Button-Actions, Audio-Status, Sleep-Timer, Bedtime-Fade, Playback-Events und Stream-Reconnect. Empfehlung: thematische Handler-Module (z. B. `rfid_handlers.py`, `button_handlers.py`, `sleep_timer.py`, `playback_events.py`) mit gemeinsamer Basis; MQTT-Dispatcher ruft die jeweiligen Handler auf.
- [ ] **Sleep-Timer-Logik bündeln:** Aktuell verteilt auf `core/mqtt_handlers.py`, `core/sleep_settings.py` und REST in `api/routes_audio.py`. Optional: eigenes Feature-Modul (z. B. `core/sleep_timer.py`) mit API-Anbindung in `routes_audio.py`.
- [ ] **`_download_status`-Dict persistieren:** Aktuell In-Memory; nach Service-Neustart gehen laufende Status-Einträge verloren. Optional: Status in DB-Tabelle speichern.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei" in diesem Dokument aktualisieren.
