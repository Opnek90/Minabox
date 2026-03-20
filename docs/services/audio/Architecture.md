# Audio-Service – Architecture

**Version**: 1.1.0  
**Status**: Production Ready ✅  
**Last Updated**: 2026-03-20

## 1. Zweck & Verantwortung

Der Audio-Service ist der zentrale Player-Service der Minabox.
Er erhält Steuerbefehle (z.B. `play`, `pause`, `stop`, `next`, `prev`, `set_volume`) vom Backend über MQTT und führt diese lokal auf dem Raspberry Pi aus.

### Ziele

- **Robuste Audio-Wiedergabe**: Abspielen von Audioinhalten (Dateien und Streams) über VLC (libVLC)
- **Automatische Hardware-Erkennung**: Erkennung und Priorisierung verfügbarer Audio-Hardware (HATs, USB, onboard)
- **Flexible Ausgabe**: Konfigurierbare Ausgabegeräte (PulseAudio empfohlen, ALSA deprecated; optional „auto“)
- **Pulse-Geräteauswahl**: Mehrere Ausgabegeräte (enabled_output_devices) mit Anzeigenamen (device_display_names) für WebUI/Admin
- **Wiedergabestatus-Verwaltung**: Verwaltung von Wiedergabestatus (playing/paused/stopped) und Lautstärke
- **Kinderschutz**: Maximale Lautstärkebegrenzung (max_volume)
- **Status-Interface**: Klares Status-Interface für Backend, WebUI, LED und andere Services
- **State-Persistenz**: Resume-Funktionalität nach Service-Neustart

### Nicht-Ziele

- Keine Playlist- oder Tag-Logik (Zuordnung Tag → Playlist/Track liegt ausschließlich im Backend)
- Keine Persistenz in einer Datenbank (nur optional lokale State-JSON-Datei für Resume)
- Keine direkte Interaktion mit der WebUI (nur über MQTT/REST via Backend)

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/audio-service/src/audio_service/`

```text
audio_service/
├── __init__.py              # Package-Init
├── main.py                  # Einstiegspunkt: Config, Logging, AudioService-Instanz, Signal-Handler, Graceful Shutdown
├── config.py                # Lädt Service-Config: Env + audio.json
├── config_schema.py         # Pydantic AudioConfig (output_device_type/name, enabled_output_devices, device_display_names, max_volume, default_volume)
├── config_manager.py        # JSON-Config (config/audio.json), Hot-Reload, Validierung, atomare Schreibvorgänge
├── exceptions.py            # MinaboxAudioError, AudioError, PlaybackError, VLCError, MQTTError, ConfigUpdateError, StateError, etc.
├── core/
│   ├── __init__.py
│   ├── service.py           # Haupt-Orchestrierung: MQTT-Command-Routing, periodisches Status-Publish, State-Persistenz, Resume, Config-Reload, Graceful Shutdown
│   ├── state_manager.py     # Playback-State-Persistenz (state/audio_state.json), Save/Restore, Resume
│   └── mqtt_handler.py      # MQTT-Command-Verarbeitung (play, pause, stop, next, prev, set-volume, volume-up/down, config/update, config/reload, config/get)
├── infrastructure/
│   ├── __init__.py
│   ├── vlc_backend.py       # VLC-Playback-Engine (libVLC): Play/Pause/Stop, Volume, Events, Position/Duration, Pulse/ALSA-Output
│   ├── audio_backend.py     # Abstrakte AudioBackend-Schnittstelle (ABC) für erweiterbare Backends
│   ├── audio_detector.py    # ALSA-Geräteerkennung (aplay -L), Prioritäts-Ranking (HATs, USB, onboard)
│   ├── pulse_detector.py   # PulseAudio-Sink-Erkennung (pactl list sinks) für Geräteauswahl
│   └── mqtt_client.py       # Async MQTT (aiomqtt), Subscriptions/Publish, Auto-Reconnect, Retained Status
├── api/
│   ├── __init__.py
│   └── routes.py            # REST: GET /health, GET /api/v1/status, GET /api/v1/devices, POST /api/v1/switch-device
└── models/
    ├── __init__.py
    └── schemas.py           # Pydantic-Schemas für API/MQTT (Health, Status, Commands)
```

---

## 3. Komponenten-Übersicht

### 3.1 Kern-Komponenten

#### VLC Backend (`vlc_backend.py`) - 455 LOC

**Verantwortung**: Audio-Playback-Engine basierend auf libVLC

**Features**:
- Vollständige VLC Media Player Kontrolle über python-vlc Bindings
- Event-Handling für Playback-State-Changes (Playing, Paused, Stopped, EndReached, Error)
- PulseAudio- oder ALSA-Output-Konfiguration (PulseAudio bevorzugt)
- Volume-Control mit Child-Protection Limits (max_volume)
- Positionsabfrage für Status-Updates
- Playlist-Navigation (next/prev mit interner Queue)
- Unterstützung für lokale Dateien und HTTP/HTTPS-Streams

**Technische Details**:
- Nutzt `vlc.Instance()` und `vlc.MediaPlayer()`
- PulseAudio: `--aout=pulse` (Standard); ALSA (deprecated): `--aout=alsa --alsa-audio-device=<device>`
- Event-Callbacks via VLC Event Manager
- Asynchrone Event-Verarbeitung

#### Backend-Abstraktion (`audio_backend.py`) - 163 LOC

**Verantwortung**: Abstrakte Schnittstelle für Audio-Backends

**Zweck**:
- Erweiterbare Architektur für zukünftige Backend-Implementierungen (z.B. MPD, GStreamer)
- Standardisierte Playback-Control-Interface
- Event-Callback-System
- Type-safe API mit Pydantic Models

**Interface-Methoden**:
```python
class AudioBackend(ABC):
    async def initialize() -> None
    async def play(source_uri: str, start_position_ms: int) -> None
    async def pause() -> None
    async def resume() -> None
    async def stop() -> None
    async def set_volume(volume: int) -> None
    async def get_position() -> int
    async def get_duration() -> int | None
    async def is_playing() -> bool
    async def cleanup() -> None
```

#### Audio Device Detector (`audio_detector.py`) - 162 LOC

**Verantwortung**: Automatische Erkennung und Priorisierung von Audio-Hardware (ALSA)

**Features**:
- Erkennung aller verfügbaren ALSA-Audio-Geräte via `aplay -L`
- Prioritätsbasiertes Ranking nach Hardware-Typ
- Unterstützung für gängige Raspberry Pi Audio HATs
- Fallback auf manuelle Konfiguration

**Hinweis**: Bei `output_device_type = pulseaudio` wird optional der **PulseSinkDetector** genutzt (siehe unten).

#### PulseSinkDetector (`pulse_detector.py`)

**Verantwortung**: Erkennung verfügbarer PulseAudio-/PipeWire-Sinks für Geräteauswahl

**Features**:
- Läuft nur, wenn `PULSE_SERVER` gesetzt ist (z.B. Host-Pulse-Socket im Container)
- Führt `pactl list sinks` aus und parst Sink-Namen/Description
- Liefert Liste von Sinks für Config `enabled_output_devices` und Admin-UI (Geräteauswahl)
- Priorität/Anzeigename optional aus Properties (node.nick, alsa.card_name)

**Hardware-Priorisierung** (niedrigere Zahl = höhere Priorität):
1. **WM8960 Audio HAT** (Waveshare/Seeed) - Priorität 1
2. **HiFiBerry DAC/AMP** - Priorität 2
3. **IQaudio DAC/AMP** - Priorität 3
4. **Blokas Pisound** - Priorität 4
5. **Audio Injector HATs** - Priorität 5
6. **USB Soundcards** - Priorität 6
7. **Raspberry Pi 3.5mm jack (Headphones)** - Priorität 7
8. **HDMI Audio (vc4hdmi)** - Priorität 8
9. **Unbekannte Geräte** - Priorität 99

**Auto-Detection Prozess**:
1. `aplay -L` ausführen und Ausgabe parsen
2. `plughw:CARD=...` Devices identifizieren (beste VLC-Kompatibilität)
3. Card-Namen mit Prioritäts-Keywords matchen
4. Devices nach Priorität sortieren
5. Bestes verfügbares Device zurückgeben

### 3.2 Service-Layer

#### Service (`service.py`) - 415 LOC

**Verantwortung**: Haupt-Orchestrierung des Audio-Service

**Features**:
- MQTT-Command-Routing zu allen Handlern
- Periodisches Status-Publishing (2s Intervall, retained)
- Error-Publishing bei Fehlern
- Config Hot-Reload via MQTT
- State-Persistenz bei Pause/Stop
- Resume-Funktionalität
- Graceful Shutdown (SIGTERM/SIGINT)
- Concurrent FastAPI + MQTT Service
- Uptime-Tracking
- Health-Check-Logik

**Lifecycle**:
1. **Initialization**:
   - VLC Backend initialisieren
   - Audio-Hardware erkennen (falls `auto`)
   - MQTT-Verbindung aufbauen
   - State aus Persistenz laden
   - FastAPI-Server starten

2. **Runtime**:
   - MQTT-Commands verarbeiten
   - Status alle 2s publishen
   - Config-Updates verarbeiten
   - Errors publishen

3. **Shutdown**:
   - Signal-Handler (SIGTERM/SIGINT)
   - State persistieren
   - VLC Backend cleanup
   - MQTT-Disconnect
   - FastAPI-Server stoppen

#### MQTT Client (`mqtt_client.py`) - 234 LOC

**Verantwortung**: Asynchrone MQTT-Kommunikation

**Features**:
- Async MQTT-Connection-Management via aiomqtt
- Topic-Subscription/Publishing
- Auto-Reconnection mit Exponential Backoff
- Retained Messages für Status
- QoS-Level-Konfiguration
- Graceful Disconnect

#### MQTT Handler (`mqtt_handler.py`) - 267 LOC

**Verantwortung**: MQTT-Command-Verarbeitung

**Unterstützte Commands**:
- `play` - Start/Resume Playback
- `pause` - Pause Playback
- `stop` - Stop Playback
- `next` - Next Track (Backend-controlled)
- `prev` - Previous Track (Backend-controlled)
- `set-volume` - Set Volume (0-100, clamped to max_volume)
- `volume-up` - Increase Volume (default step: 5)
- `volume-down` - Decrease Volume (default step: 5)
- `mute-toggle` - Toggle mute/unmute (no payload)
- `switch-device` - Switch output sink/device (payload: `sink_name` or `alsa_device`, optional `direction: "next"`)
- `config/update` - Update Configuration
- `config/reload` - Reload Configuration
- `config/get` - Get Current Configuration
- `config/general` - Apply runtime log level (`log_level` payload), topic: `minabox/<device-id>/config/general`

**Validation**:
- Payload-Validation via Pydantic
- Volume-Clamping (0-100, max_volume)
- Source-URI-Validation (file/stream)
- Error-Handling mit strukturiertem Logging

### 3.3 Support-Komponenten

#### State Manager (`state_manager.py`) - 172 LOC

**Verantwortung**: Playback-State-Persistenz

**Features**:
- Save/Restore Playback-State
- JSON-basierte Persistenz (`state/audio_state.json`)
- Resume-Funktionalität nach Restart
- Atomic File-Writes (write to temp, then rename)

**Persistierte Daten**:
```json
{
  "last_track_id": "track_123",
  "last_source_type": "file",
  "last_source_uri": "/mnt/audio/album1/01-track.mp3",
  "last_position_ms": 12345,
  "last_state": "paused",
  "last_volume": 55,
  "timestamp": "2026-02-16T20:45:00Z"
}
```

#### Config Manager (`config_manager.py`) - 235 LOC

**Verantwortung**: Konfigurationsverwaltung

**Features**:
- JSON-basierte Konfiguration (`config/audio.json`)
- Hot-Reload-Support via MQTT
- Validation mit Pydantic-Schemas
- Atomic File-Writes
- Default-Values

**Config-Schema** (`config_schema.py`):
```python
class AudioConfig(BaseModel):
    output_device_type: Literal["auto", "alsa", "pulseaudio", "default"]  # ALSA deprecated → PULSEAUDIO
    output_device_name: str  # Pulse-Sink-Name oder "auto" / ALSA-Device
    enabled_output_devices: list[str] = []  # Erlaubte Sinks für Geräteauswahl (leer = alle)
    device_display_names: dict[str, str] = {}  # Sink-Name → Anzeigename (z.B. "Lautsprecher", "Headset")
    min_volume: int = Field(ge=0, le=100)  # Child protection (minimum volume)
    max_volume: int = Field(ge=0, le=100)  # Child protection
    default_volume: int = Field(ge=0, le=100)
```

#### FastAPI Routes (`api/routes.py`) - 101 LOC

**Verantwortung**: REST-API-Endpoints

**Endpoints**:
- `GET /health` - Service Health Check
- `GET /api/v1/status` - Current Audio Status
- `GET /api/v1/devices` - List detected Pulse/PipeWire sinks
- `POST /api/v1/switch-device` - Switch output sink/device

**Health Response**:
```json
{
  "status": "healthy",
  "service": "audio",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "timestamp": "2026-02-16T20:45:00Z"
}
```

#### Exceptions (`exceptions.py`) - 77 LOC

**Verantwortung**: Strukturierte Error-Hierarchie

**Exception-Typen**:
- `MinaboxAudioError` (Base für alle Audio-Service-Fehler)
- `AudioError` (Base für Playback/Backend-Fehler)
- `PlaybackError`, `VLCError`, `FileNotFoundError`, `StreamUnreachableError`, `OutputDeviceError`
- `MQTTError`, `MQTTConnectionError`, `MQTTPublishError`
- `ConfigUpdateError`, `StateError`

---

## 4. Datenfluss

### 4.1 Play-Command-Flow

```
MQTT Command (play)
  ↓
MQTT Handler (mqtt_handler.py)
  ↓ validate & parse payload
Service (service.py)
  ↓ check device auto-detection
Audio Detector (audio_detector.py)  [if device_name == "auto"]
  ↓ get best available device
VLC Backend (vlc_backend.py)
  ↓ configure output device
  ↓ load media, set position, play
ALSA/PulseAudio
  ↓
Audio Output (Speaker/HAT)
  ↓
VLC Events (Playing, EndReached, Error)
  ↓
Service (service.py)
  ↓ update internal state
State Manager (state_manager.py)
  ↓ persist state to JSON
MQTT Status Publishing
  ↓
minabox/{device_id}/audio/status (retained, every 2s)
```

### 4.2 Config-Update-Flow

```
MQTT (config/update)
  ↓
MQTT Handler (mqtt_handler.py)
  ↓
Config Manager (config_manager.py)
  ↓ validate with Pydantic
  ↓ write to config/audio.json (atomic)
  ↓
Service (service.py)
  ↓ reload config
  ↓ re-initialize VLC Backend (if device changed)
  ↓
MQTT (config/response)
  ↓
{"success": true, "timestamp": "..."}
```

---

## 5. Öffentliche Schnittstellen

### 5.1 MQTT – Steuerbefehle

Topic-Schema:
```
minabox/<device-id>/audio/<command>
```

**Unterstützte Kommandos**:

#### `play`
```json
{
  "track_id": "track_123",
  "source_type": "file",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "start_position_ms": 0
}
```

- `track_id`: Backend-vergebene ID (zur Referenz)
- `source_type`: `"file"` oder `"stream"`
- `source_uri`: Pfad oder URL zur Audioquelle
- `start_position_ms`: Startposition in Millisekunden (optional, default: 0)

**Verhalten**:
- Falls `track_id`/`source_uri` angegeben: neuen Track laden und abspielen
- Falls nicht angegeben und pausierter Track existiert: Resume an letzter Position

#### `pause`
Keine Payload erforderlich.

**Verhalten**:
- Playback pausieren
- Position speichern
- State auf `"paused"` setzen

#### `stop`
Keine Payload erforderlich.

**Verhalten**:
- Playback stoppen
- Position auf 0 zurücksetzen
- State auf `"stopped"` setzen

#### `set-volume`
```json
{
  "volume": 55
}
```

- `volume`: gewünschter Lautstärkewert (0–100)
- Wird automatisch auf `max_volume` geclamped

#### `volume-up` / `volume-down`
```json
{
  "step": 5
}
```

- `step`: Schrittwert (optional, default: 5)
- Resultat wird auf `max_volume` begrenzt

### 5.2 MQTT – Status & Fehler

#### Status-Topic (retained)
```
minabox/<device-id>/audio/status
```

**Payload**:
```json
{
  "state": "playing",
  "track_id": "track_123",
  "source_type": "file",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "position_ms": 12345,
  "duration_ms": 240000,
  "volume": 55,
  "timestamp": "2026-02-16T21:20:00Z"
}
```

- `state`: `"playing"` | `"paused"` | `"stopped"` | `"error"`
- `position_ms`: aktuelle Wiedergabeposition
- `duration_ms`: Gesamtdauer (falls bekannt, sonst `null`)
- `volume`: aktueller Volume (0-100, bereits geclamped)

**Publishing**:
- **Intervall**: Alle 2 Sekunden
- **Retained**: Ja (letzter Status bleibt erhalten)
- **QoS**: 1 (at least once)

#### Fehler-Topic
```
minabox/<device-id>/audio/error
```

**Payload**:
```json
{
  "error_code": "file_not_found",
  "message": "Source file not found",
  "track_id": "track_123",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "timestamp": "2026-02-16T21:21:00Z"
}
```

**Error-Codes**:
- `file_not_found` - Quell-Datei existiert nicht
- `decode_error` - VLC kann Datei nicht dekodieren
- `stream_unreachable` - Netzwerk-Stream nicht erreichbar
- `output_device_error` - ALSA-Device nicht verfügbar
- `vlc_initialization_error` - VLC Backend-Initialisierung fehlgeschlagen
- `device_detection_error` - Auto-Detection fehlgeschlagen

### 5.3 REST API

#### `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "service": "audio",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "timestamp": "2026-02-16T20:45:00Z"
}
```

**Status values**:
- `"healthy"` - All systems functional
- `"degraded"` - MQTT or VLC problem
- `"unhealthy"` - Critical error

#### `GET /api/v1/status`

**Response**: Mirrors the `audio/status` MQTT topic.

#### `GET /api/v1/devices`

Lists detected PulseAudio/PipeWire audio sinks (supports optional `enabled_only` query parameter).

#### `POST /api/v1/switch-device`

Switches the audio output to the specified sink/device (request body: `sink_name` or `alsa_device`; optional `direction: "next"`).

---

## 6. Konfigurationsmodell

### 6.1 Struktur `config/audio.json`

```json
{
  "output_device_type": "pulseaudio",
  "output_device_name": "alsa_output.platform-soc_sound.stereo-fallback",
  "enabled_output_devices": ["alsa_output.platform-soc_sound.stereo-fallback", "alsa_output.usb-..."],
  "device_display_names": {
    "alsa_output.usb-...": "Headset",
    "alsa_output.platform-soc_sound.stereo-fallback": "Lautsprecher"
  },
  "min_volume": 5,
  "max_volume": 70,
  "default_volume": 40
}
```

**Felder**:

- `output_device_type`: Audio-Output-Typ
  - `"pulseaudio"` - PulseAudio (empfohlen)
  - `"alsa"` - ALSA (deprecated; wird beim Laden ggf. auf pulseaudio migriert)
  - `"auto"` - Automatische Erkennung (ALSA-basiert)
  - `"default"` - System-Default

- `output_device_name`: Device-Identifier
  - Bei PulseAudio: Pulse-Sink-Name (z.B. `alsa_output.platform-soc_sound.stereo-fallback`)
  - `"auto"` - Automatische Erkennung (ALSA)
  - `"default"` - System-Default-Device

- `enabled_output_devices`: Liste von Pulse-Sink-Namen, die in der Geräteauswahl (WebUI/Admin) angeboten werden. Leer = alle verfügbaren Sinks.

- `device_display_names`: Map von Sink-Name → Anzeigename (z.B. „Lautsprecher“, „Headset“) für die WebUI.

- `min_volume`: Minimale Lautstärke (0-100) zum Schutz vor unbeabsichtigtem „Stumm“-Niveau.

- `max_volume`: Maximale Lautstärke (0-100) für Kinderschutz

- `default_volume`: Lautstärke beim Service-Start

### 6.2 Auto-Detection

**Wenn `output_device_name` = `"auto"`**:

1. Service startet Audio-Detector (`audio_detector.py`)
2. Detector scannt ALSA-Devices via `aplay -L`
3. Devices werden nach Priorität sortiert
4. Bestes verfügbares Device wird ausgewählt
5. VLC Backend wird mit diesem Device konfiguriert

**Fallback**:
- Falls keine Devices gefunden: Fehler loggen, Service im degraded state
- User kann manuelles Device in Config setzen

### 6.3 MQTT-Config-API

#### Commands
- `minabox/<device-id>/audio/config/get` - Config abrufen
- `minabox/<device-id>/audio/config/update` - Config aktualisieren
- `minabox/<device-id>/audio/config/reload` - Config neu laden

#### Response
- `minabox/<device-id>/audio/config/response` - Erfolg/Fehler

**Update-Request**:
```json
{
  "output_device_type": "alsa",
  "output_device_name": "auto",
  "max_volume": 70,
  "default_volume": 40
}
```

**Response**:
```json
{
  "success": true,
  "error": null,
  "timestamp": "2026-02-16T21:22:00Z"
}
```

**Validation**:
- Pydantic-Schema-Validation
- Bei ungültiger Config: alte Config bleibt aktiv
- Response mit `success: false` und `error`-Message

---

## 7. VLC Backend – Technische Details

### 7.1 libVLC Integration

**Library**: [python-vlc](https://github.com/oaubert/python-vlc) 3.0.21216

**Initialisierung**:
```python
args = []
if output_device_type == "alsa":
    args.extend(["--aout=alsa", f"--alsa-audio-device={device_name}"])
elif output_device_type == "pulseaudio":
    args.append("--aout=pulse")

instance = vlc.Instance(args)
player = instance.media_player_new()
```

### 7.2 Event-Handling

**Registrierte Events**:
- `vlc.EventType.MediaPlayerPlaying` → `state = "playing"`
- `vlc.EventType.MediaPlayerPaused` → `state = "paused"`
- `vlc.EventType.MediaPlayerStopped` → `state = "stopped"`
- `vlc.EventType.MediaPlayerEndReached` → Next track (if playlist)
- `vlc.EventType.MediaPlayerEncounteredError` → Error publishing

**Callback-Flow**:
```
VLC Event
  ↓
Event Manager Callback (sync)
  ↓
Async Event Queue
  ↓
Service Event Handler (async)
  ↓
State Update + MQTT Publish
```

### 7.3 Position & Duration Tracking

**Position**:
- Via `player.get_time()` (Millisekunden)
- Abgefragt für Status-Updates (alle 2s)

**Duration**:
- Via `player.get_length()` (Millisekunden)
- Kann `None` sein (z.B. bei Streams)

### 7.4 Volume Control

**Range**: 0-100 (VLC-intern: 0-200, wird umgerechnet)

**Child Protection**:
```python
def set_volume(self, volume: int) -> None:
    clamped = min(volume, self.max_volume)
    vlc_volume = int(clamped * 2)  # VLC: 0-200
    self.player.audio_set_volume(vlc_volume)
```

---

## 8. State-Management & Resume

### 8.1 Interner State

**State-Manager** hält:
```python
{
    "last_track_id": str | None,
    "last_source_type": "file" | "stream" | None,
    "last_source_uri": str | None,
    "last_position_ms": int,
    "last_state": "playing" | "paused" | "stopped",
    "last_volume": int,
    "timestamp": str
}
```

### 8.2 Persistenz

**Datei**: `state/audio_state.json`

**Wann wird gespeichert**:
- Bei `pause` - Position speichern
- Bei `stop` - State speichern
- Bei Shutdown - Aktuellen State speichern

**Atomic Write**:
1. Write to `audio_state.json.tmp`
2. `fsync()`
3. `rename()` to `audio_state.json`

### 8.3 Resume-Logik

**Service-Start**:
1. State-Manager lädt `audio_state.json`
2. State wird in Service geladen
3. **Kein automatischer Resume** (User/Backend muss `play` senden)

**Resume bei `play`-Command ohne Track**:
1. Prüfe: existiert `last_track_id`?
2. Falls ja: lade `last_source_uri` mit `last_position_ms`
3. Setze `state = "playing"`

---

## 9. Fehlerbehandlung & Logging

### 9.1 Fehlertypen

**Playback-Fehler**:
- `file_not_found` → Error-Event + `state = "error"`
- `decode_error` → Error-Event + `state = "error"`
- `stream_unreachable` → Error-Event + retry (3x)

**Init-Fehler**:
- `vlc_initialization_error` → Service startet im degraded state
- `device_detection_error` → Fallback auf manual config
- `output_device_error` → Service degraded, Health unhealthy

**Config-Fehler**:
- Ungültige Config → alte Config bleibt, Response `success: false`
- Missing config file → Default-Config wird erstellt

### 9.2 Logging

**Framework**: structlog mit JSON-Logging (LOG_LEVEL=INFO) oder Console (LOG_LEVEL=DEBUG)

**Log-Events**:
- `audio_service_started` - Service lifecycle
- `audio_device_detected` - Auto-detection Ergebnis
- `vlc_backend_initialized` - VLC init success
- `audio_command_received` - Jeder MQTT-Command
- `play_started`, `play_paused`, `play_stopped` - Playback events
- `volume_changed` - Volume updates
- `audio_error` - Alle Fehler mit Details
- `config_update_received`, `config_update_applied` - Config changes
- `state_persisted` - State save events

### 9.3 Health Status

**Healthy**:
- MQTT connected: `true`
- VLC initialized: `true`
- No critical errors

**Degraded**:
- MQTT connection lost (reconnecting)
- VLC init failed but retrying
- Output device warning

**Unhealthy**:
- MQTT connection failed (no retry)
- VLC init permanently failed
- Critical output device error

---

## 10. Abhängigkeiten

### 10.1 Hardware / OS

- **Raspberry Pi** (3/4/5) mit ALSA-konfiguriertem Audio-Device
- **Unterstützte Audio-Hardware**:
  - WM8960 Audio HAT (Waveshare/Seeed)
  - HiFiBerry DAC/AMP
  - IQaudio DAC/AMP
  - USB-Soundkarten
  - 3.5mm Klinke (onboard)
  - HDMI Audio

### 10.2 Software

**System-Packages**:
- `vlc` - VLC Media Player
- `libvlc5` - VLC library
- `vlc-plugin-base` - VLC plugins
- `libasound2` - ALSA library

**Python 3.13+**: Siehe `services/audio-service/requirements.txt` für die aktuellen, versionierten Abhängigkeiten. Kurzüberblick:
- `python-vlc` - libVLC bindings
- `fastapi`, `uvicorn[standard]` - REST API & ASGI server
- `aiomqtt` - Async MQTT client
- `structlog` - Structured logging
- `pydantic` - Config validation
- `tenacity` - Retry & error handling
- `httpx` - HTTP client (z.B. für Health-Checks)

### 10.3 Services

- **MQTT Broker** (Mosquitto): `mqtt:1883`
- **Backend Service**: Sendet Play/Pause/Stop-Commands

### 10.4 Konfiguration

- **Global** (`.env`): `MINABOX_DEVICE_ID`, `MQTT_BROKER`, `MQTT_PORT`, `LOG_LEVEL`
- **Service-spezifisch**: `config/audio.json`
- **State-Persistenz**: `state/audio_state.json`

---

## 11. Implementierungs-Status

### 11.1 Komponenten-Übersicht

| Modul | LOC | Status |
|-------|-----|--------|
| `vlc_backend.py` | 455 | ✅ Production Ready |
| `service.py` | 415 | ✅ Production Ready |
| `mqtt_handler.py` | 267 | ✅ Production Ready |
| `config_manager.py` | 235 | ✅ Production Ready |
| `mqtt_client.py` | 234 | ✅ Production Ready |
| `main.py` | 179 | ✅ Production Ready |
| `state_manager.py` | 172 | ✅ Production Ready |
| `audio_backend.py` | 163 | ✅ Production Ready |
| `audio_detector.py` | 162 | ✅ Production Ready |
| `config_schema.py` | 122 | ✅ Production Ready |
| `api/routes.py` | 101 | ✅ Production Ready |
| `exceptions.py` | 77 | ✅ Production Ready |
| `__init__.py` | 32 | ✅ Production Ready |
| **Gesamt** | **~2800** | **✅ Production Ready** |

### 11.2 Features

- ✅ VLC-basierte Wiedergabe
- ✅ Automatische Hardware-Erkennung
- ✅ MQTT-Steuerung (alle Commands)
- ✅ State-Persistenz & Resume
- ✅ Volume-Management mit Kinderschutz
- ✅ Config Hot-Reload
- ✅ REST API (Health & Status)
- ✅ Error-Handling & Logging
- ✅ Graceful Shutdown
- ✅ Docker-Integration

### 11.3 Tests

- ✅ VLC Backend-Initialisierung
- ✅ Audio Device Detection
- ✅ MQTT Integration
- ✅ REST API Endpoints
- ✅ State Persistence
- ✅ Docker Container

---

## 12. Nicht-Ziele / Abgrenzung

- ❌ **Keine Playlist-Verwaltung** (Reihenfolge/Shuffle/Repeat) – liegt im Backend
- ❌ **Keine Benutzerprofile** – kann später im Backend ergänzt werden
- ❌ **Keine direkten Service-Trigger** – nur über MQTT-Events
- ❌ **Keine Equalizer/DSP** – kann später als VLC-Plugin ergänzt werden
- ❌ **Keine Multi-Room-Sync** – könnte später mit Snapcast integriert werden

---

## 13. Roadmap / Erweiterungen

### Phase 1 (Current) ✅
- VLC Backend
- Auto-Detection
- Basic Playback Control
- MQTT Integration

### Phase 2 (Next)
- Integration mit Backend-Service (Playlist-Management)
- Integration mit RFID-Service (Tag-triggered Playback)
- WebUI für Audio-Control

### Phase 3 (Future)
- Equalizer-Support (VLC-Plugin)
- Gapless Playback
- Crossfade zwischen Tracks
- Multi-Room-Sync (Snapcast)
- Spotify Connect Integration

---

## 14. Refactoring-Checkliste

- [ ] **Keine groben Inkonsistenzen:** State-Persistenz (state_manager), Config (config_manager) und MQTT-Handler sind klar getrennt; VLC und Backend-Abstraktion in infrastructure.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei“ in diesem Dokument aktualisieren.

---

**Version**: 1.1.0  
**Status**: ✅ Production Ready  
**Last Updated**: 2026-03-20
