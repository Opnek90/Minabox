# Audio-Service – Architecture

## 1. Zweck & Verantwortung

Der Audio-Service ist der zentrale Player-Service der Minabox.
Er erhält Steuerbefehle (z.B. `play`, `pause`, `stop`, `next`, `prev`, `set_volume`) vom Backend über MQTT und führt diese lokal auf dem Raspberry Pi aus.

Ziele:

- Abspielen von Audioinhalten (Dateien und Streams) über ein konfigurierbares Ausgabegerät.
- Verwaltung von Wiedergabestatus (playing/paused/stopped) und Lautstärke inkl. Kinderschutz (maximale Lautstärke).
- Bereitstellung eines klaren Status-Interfaces für Backend, WebUI, LED- und andere Services.

Nicht-Ziele:

- Keine Playlist- oder Tag-Logik (Zuordnung Tag → Playlist/Track liegt ausschließlich im Backend).
- Keine Persistenz in einer Datenbank (nur optional lokale State-JSON-Datei für Resume).
- Keine direkte Interaktion mit der WebUI (nur über MQTT/REST via Backend).

---

## 2. Öffentliche Schnittstellen

### 2.1 MQTT – Steuerbefehle

Topic-Schema (analog Framework):

```text
minabox/<device-id>/audio/<command>
```

Unterstützte Kommandos:

- `minabox/<device-id>/audio/play`
- `minabox/<device-id>/audio/pause`
- `minabox/<device-id>/audio/stop`
- `minabox/<device-id>/audio/next`       # Backend entscheidet, welcher Track als nächstes gespielt wird
- `minabox/<device-id>/audio/prev`       # Backend entscheidet, welcher Track vorher war
- `minabox/<device-id>/audio/set-volume`
- `minabox/<device-id>/audio/volume-up`
- `minabox/<device-id>/audio/volume-down`

**Payload-Beispiele:**

`play`:

```json
{
  "track_id": "track_123",        
  "source_type": "file",          
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "start_position_ms": 0
}
```

- `track_id`: vom Backend vergebene ID (zur Anzeige/Referenz in WebUI).
- `source_type`: `"file"` oder `"stream"`.
- `source_uri`: Pfad oder URL zur Audioquelle (z.B. lokale Datei oder HTTP-Stream).
- `start_position_ms`: Startposition in Millisekunden (0 = von Anfang).

`set-volume`:

```json
{
  "volume": 55
}
```

- `volume`: gewünschter Lautstärkewert (0–100). Der Audio-Service clamped diesen Wert auf `max_volume` (Kinderschutz).

`volume-up` / `volume-down`:

```json
{
  "step": 5
}
```

- `step`: optionaler Schrittwert (Standard: 5), Resultat wird ebenfalls auf `max_volume` begrenzt.

### 2.2 MQTT – Status & Fehler

**Status-Topic (retained):**

```text
minabox/<device-id>/audio/status
```

Payload (Beispiel):

```json
{
  "state": "playing",
  "track_id": "track_123",
  "source_type": "file",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "position_ms": 12345,
  "duration_ms": 240000,
  "volume": 55,
  "timestamp": "2026-02-14T21:20:00Z"
}
```

- `state`: `"playing"` | `"paused"` | `"stopped"` | `"error"`.
- `position_ms`: aktuelle Wiedergabeposition in Millisekunden.
- `duration_ms`: Gesamtdauer des Tracks (falls bekannt, sonst `null`).
- `volume`: aktueller Volume-Wert (0–100, bereits auf `max_volume` gecappt).

**Fehler-Topic:**

```text
minabox/<device-id>/audio/error
```

Payload (Beispiel):

```json
{
  "error_code": "file_not_found",
  "message": "Source file not found",
  "track_id": "track_123",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "timestamp": "2026-02-14T21:21:00Z"
}
```

Mögliche `error_code`-Werte (Beispiele):

- `file_not_found`
- `decode_error`
- `stream_unreachable`
- `output_device_error`

Bei schwerwiegenden Fehlern setzt der Audio-Service zusätzlich `state = "error"` im `audio/status`-Topic.

### 2.3 REST (optional)

Optional kann der Audio-Service zusätzlich eine kleine REST-API anbieten (z.B. via FastAPI), primär für Debug/Health:

- `GET /health` – Service-Health, aktueller Status, GStreamer/ALSA-Verbindung.
- `GET /status` – aktueller Audio-Status (Spiegelung von `audio/status`).

---

## 3. Konfigurationsmodell

Die Audio-Konfiguration wird lokal in einer JSON-Datei gespeichert, z.B. `config/audio.json`.
Sie wird vom Backend/WebUI verwaltet und via MQTT-Config-API in den Service geladen.

### 3.1 Struktur `audio.json`

```json
{
  "output_device_type": "alsa",
  "output_device_name": "hw:1,0",
  "max_volume": 70,
  "default_volume": 40
}
```

Felder:

- `output_device_type`: aktuell `"alsa"` (direkte ALSA-Ausgabe; Erweiterungen möglich).
- `output_device_name`: Konkretes ALSA-Device, z.B. `"hw:1,0"`, `"default"` etc.
- `max_volume`: maximale Lautstärke (0–100). Alle Volume-Änderungen werden auf diesen Wert begrenzt (Kinderschutz).
- `default_volume`: Lautstärke beim Service-Start (wird ebenfalls auf `max_volume` gecappt).

### 3.2 MQTT-Config-API für Audio

Analog zum generischen Muster aus dem Framework:

- `minabox/<device-id>/audio/config/get`
- `minabox/<device-id>/audio/config/update`
- `minabox/<device-id>/audio/config/reload`
- `minabox/<device-id>/audio/config/response`

**Update-Request (Beispiel-Payload für `audio/config/update`):

```json
{
  "output_device_type": "alsa",
  "output_device_name": "hw:1,0",
  "max_volume": 70,
  "default_volume": 40
}
```

**Response (`audio/config/response`):**

```json
{
  "success": true,
  "error": null,
  "timestamp": "2026-02-14T21:22:00Z"
}
```

Im Fehlerfall:

```json
{
  "success": false,
  "error": "invalid_audio_config",
  "timestamp": "2026-02-14T21:22:00Z"
}
```

Der Audio-Service validiert jede eingehende Config vor dem Schreiben; bei ungültiger Config bleibt die alte Konfiguration aktiv.

---

## 4. Kern-Funktionen / Use-Cases

### 4.1 Audio-Wiedergabe (Play/Pause/Stop)

Ablauf bei `play`:

1. Audio-Service erhält ein `play`-Kommando über MQTT.
2. Falls `track_id` / `source_uri` im Payload enthalten sind:
   - aktueller Track wird abgebrochen (falls vorhanden),
   - neuer Track wird geladen und mit `start_position_ms` gestartet.
3. Falls **kein** neuer Track angegeben ist und ein pausierter Track existiert:
   - Service setzt die Wiedergabe an der letzten Position (`last_position_ms`) fort.
4. Service setzt `state = "playing"` und aktualisiert `audio/status`.

`pause`:

- Wiedergabe wird pausiert.
- Aktuelle `position_ms` wird im internen State gespeichert.
- `state = "paused"`, `audio/status` aktualisiert.

`stop`:

- Wiedergabe wird gestoppt.
- Position kann auf 0 zurückgesetzt werden.
- `state = "stopped"`, `audio/status` aktualisiert.

### 4.2 State-Management & Resume

Der Audio-Service verwaltet einen internen State-Manager mit u.a.:

- `last_track_id`
- `last_source_type`
- `last_source_uri`
- `last_position_ms`
- `last_state`

Optionale Persistenz:

- Dieser State kann zusätzlich in einer kleinen JSON-Datei (`state/audio_state.json`) gespeichert werden.
- Nach einem Neustart kann der Service diesen State laden, um z.B. bei einem `play`-Kommando ohne neuen Track wieder an der letzten Stelle weiterzuspielen.

### 4.3 Lautstärke & Kinderschutz

- Alle Volume-Kommandos (`set-volume`, `volume-up`, `volume-down`) werden intern auf einen Bereich `0–max_volume` begrenzt.
- `max_volume` und `default_volume` werden aus `audio.json` geladen.
- Beim Service-Start:
  - Volume wird auf `default_volume` gesetzt (geclamped auf `max_volume`).
- Volume-Änderungen führen zu einem Update von `audio/status.volume`.

### 4.4 GStreamer + ALSA Backend

Der Audio-Service verwendet einen GStreamer-basierten Backend:

- `GStreamerAudioBackend` implementiert ein internes `AudioBackend`-Interface mit Methoden wie
  - `play(source_uri, start_position_ms)`
  - `pause()`
  - `stop()`
  - `set_volume(volume)`
  - `get_position()`
- Die Audio-Ausgabe erfolgt über ALSA (basierend auf `output_device_type` und `output_device_name` aus der Config).
- GStreamer-Events (z.B. End-of-Stream, Fehler) werden in MQTT-Status-/Fehler-Events übersetzt.

---

## 5. Abhängigkeiten

- **Hardware / OS:**
  - Raspberry Pi mit konfiguriertem ALSA-Audio-Device (z.B. WM8960 HAT, USB-Lautsprecher, Klinke).

- **MQTT-Broker:**
  - Verbindung zu Mosquitto (Host/Port aus globaler `.env`).

- **Backend-Service:**
  - Hält Playlists und Tag→Track/Playlist-Mapping.
  - Sendet `audio`-Kommandos (play/pause/stop/next/prev/volume) sowie `audio/config`-Updates.

- **WebUI:**
  - Steuert Audio indirekt über Backend (REST/WebSocket → Backend → MQTT → Audio-Service).

- **Konfiguration:**
  - Globale `.env` (Root): `MINABOX_DEVICE_ID`, `MQTT_BROKER`, `MQTT_PORT` etc.
  - Service-spezifische JSON: `config/audio.json`.
  - Optional: `state/audio_state.json` für Resume.

---

## 6. Fehler & Status

### 6.1 Typische Fehlerfälle

- `file_not_found` – Quell-Datei existiert nicht.
- `decode_error` – GStreamer kann Datei/Stream nicht dekodieren.
- `stream_unreachable` – Netzwerkstream nicht erreichbar.
- `output_device_error` – ALSA-Device nicht verfügbar oder fehlerhaft.

### 6.2 Verhalten bei Fehlern

- Bei Abspiel-Fehlern:
  - Service publiziert einen Eintrag auf `audio/error` mit `error_code` und Details.
  - `audio/status.state` wird auf `"error"` gesetzt.

- Bei Config-Fehlern:
  - Ungültige Config: alte Config bleibt aktiv, `audio/config/response.success = false`.
  - Service kann optional `state = "error"` setzen, wenn z.B. das Device nicht initialisiert werden kann.

### 6.3 Logging

Der Service loggt u.a.:

- `audio_command_received` mit `command`, Payload.
- `play_started`, `play_paused`, `play_stopped` mit `track_id`, `source_uri`.
- `volume_changed` mit altem und neuem Wert.
- `audio_error` mit `error_code`, `details`.
- `config_update_received` / `config_update_applied` / `config_update_failed`.

Die Log-Konfiguration folgt den globalen Logging-Regeln aus dem Framework (structlog, JSON-Logging, Level-Definitionen).

---

## 7. Nicht-Ziele / Abgrenzung

- Keine Playlist-Verwaltung (Reihenfolge/Shuffle/Repeat) – das liegt im Backend.
- Keine Benutzerprofile oder individuelle Lautstärkeprofile – kann später im Backend ergänzt werden.
- Kein direktes Triggern anderer Services – Kommunikation erfolgt ausschließlich über MQTT-Events und -Status.
