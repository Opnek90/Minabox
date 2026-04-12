# LED-Service – Architecture

## 1. Zweck & Verantwortung

Der LED-Service ist der zentrale Ausgabeservice für einfache, einfarbige LEDs.
Er reagiert auf Zustände und Ereignisse (z.B. Systemstatus, Audio-Status, RFID-Events, Button-Events) und steuert damit LEDs an, um den aktuellen Zustand der Box visuell anzuzeigen.

Ziele:

- Abstrakte Anbindung einfarbiger LEDs über GPIO.
- Konfigurierbares Mapping "logischer Zustand/Ereignis → LED-Pattern".
- Flexibel in Anzahl und Belegung der LEDs pro Box.

Nicht-Ziele:

- Keine Business-Logik (keine Entscheidungen über Playlists, Fehlerbehandlung etc.).
- Kein Schreiben in die Datenbank (Konfigurationsverwaltung erfolgt im Backend).
- Keine WebUI-Logik (nur Anzeige-Output und Config-Updates).

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/led-service/src/led_service/`

```text
led_service/
├── __init__.py              # Package-Init
├── main.py                  # Einstiegspunkt: Config, LEDController, MQTT, State-Management, API-Server, Graceful Shutdown
├── config.py                # Lädt Env + leds.json
├── config_schema.py         # Pydantic-Schema für LED-Config (leds[], id, name, gpio, bindings)
├── config_manager.py        # JSON-Config (config/leds.json), Hot-Reload
├── exceptions.py            # Service-spezifische Exceptions
├── core/
│   ├── __init__.py
│   ├── led_controller.py    # Steuerung der LEDs: Zustand aus MQTT ableiten, Pattern aus bindings anwenden
│   ├── led_patterns.py      # Pattern-Ausführung (solid, blink, pulse, off) pro LED
│   └── state_manager.py     # Aktueller logischer Zustand (aus MQTT-Events), FIFO-Verarbeitung
├── infrastructure/
│   ├── __init__.py
│   └── mqtt_client.py       # MQTT: Subscriptions (audio/status, rfid/tag-scanned, system/service-error, button/raw-event, led/config), Publish config/response
└── api/
    ├── __init__.py
    └── routes.py            # FastAPI: GET /health (LEDs, MQTT-Status)
```

---

## 3. Logische Zustände (Beispiele)

Der LED-Service arbeitet mit logischen Zuständen/Ereignissen, die aus MQTT-Nachrichten anderer Services abgeleitet werden. Mögliche Zustände sind u.a.:

**System:**

- `system_booting` – Box startet.
- `system_online` – System betriebsbereit.
- `system_error` – generischer Fehlerzustand.
- `system_updating` – Update/Deployment läuft.

**Audio:**

- `audio_playing` – Wiedergabe läuft.
- `audio_paused` – Wiedergabe pausiert.
- `audio_stopped` – keine Wiedergabe.
- `audio_buffering` / `audio_loading` – Audio wird geladen.

**RFID:**

- `rfid_scanned` – Tag erfolgreich gelesen.
- `rfid_unknown_tag` – Tag nicht in der Datenbank.

**User-Interaktion:**

- `button_pressed` – irgendein Button wurde gedrückt.
- `config_change` – Konfiguration wurde erfolgreich übernommen.

**Netzwerk/Backend:**

- `backend_unreachable` – Backend nicht erreichbar.
- `mqtt_disconnected` – MQTT-Broker nicht erreichbar.

Diese Liste dient als Vorschlagskatalog. Welche Zustände tatsächlich verwendet werden, wird über das Mapping konfiguriert.

---

## 4. Öffentliche Schnittstellen

### 4.1 MQTT – Eingehende Events

Der LED-Service subscribed auf relevante MQTT-Themen anderer Services (z.B. Audio, RFID, System, Backend) und leitet daraus die oben genannten logischen Zustände ab.

Beispiele (konkret im Architecture-Dokument der jeweiligen Services definiert):

- `minabox/<device-id>/audio/status` → abgeleitet: `audio_playing`, `audio_paused`, `audio_stopped`.
- `minabox/<device-id>/rfid/tag-scanned` → abgeleitet: `rfid_scanned`.
- `minabox/<device-id>/system/service-error` → abgeleitet: `system_error`.
- `minabox/<device-id>/button/raw-event` → abgeleitet: `button_pressed`.

### 4.2 MQTT – Config-API

Analog zum Button-Service besitzt der LED-Service eine Config-API über MQTT.

**Topics:**

- `minabox/<device-id>/led/config/get`  
  Anfrage vom Backend, um aktuelle LED-Config anzufordern.

- `minabox/<device-id>/led/config/update`  
  Backend sendet neue vollständige LED-Konfiguration.

- `minabox/<device-id>/led/config/reload`  
  Service liest lokale JSON-Konfigurationsdatei neu ein.

- `minabox/<device-id>/led/config/response`  
  Service bestätigt Erfolg/Fehler einer Config-Operation.

**Update-Request (Beispiel-Payload für `config/update`):**

```json
{
  "leds": [
    {
      "id": "led_5",
      "name": "Power-LED",
      "gpio": 5,
      "enabled": true,
      "bindings": {
        "system_online": {
          "pattern_type": "solid"
        },
        "system_error": {
          "pattern_type": "blink",
          "interval_ms": 200,
          "repeat": 0
        }
      }
    },
    {
      "id": "led_6",
      "name": "Status-LED",
      "gpio": 6,
      "bindings": {
        "audio_playing": {
          "pattern_type": "blink",
          "interval_ms": 800,
          "repeat": 0
        },
        "audio_paused": {
          "pattern_type": "off"
        },
        "audio_stopped": {
          "pattern_type": "off"
        },
        "rfid_scanned": {
          "pattern_type": "pulse",
          "duration_ms": 500,
          "repeat": 1
        }
      }
    }
  ]
}
```

**Response (für `config/response`):**

```json
{
  "success": true,
  "error": null,
  "timestamp": "2026-02-14T13:30:05Z"
}
```

Im Fehlerfall:

```json
{
  "success": false,
  "error": "invalid_led_config",
  "timestamp": "2026-02-14T13:30:05Z"
}
```

### 4.3 REST (optional)

Optional kann der Service einen HTTP-Endpoint anbieten (z.B. FastAPI):

- `GET /health` – Gesundheitszustand, bekannte LEDs, MQTT-Status.

---

## 5. Konfigurationsmodell

Die LED-Konfiguration wird lokal in einer JSON-Datei gespeichert, z.B. `config/leds.json`.
Der Inhalt wird vom Backend/WebUI verwaltet und per MQTT (`config/update`) in den Service gespielt. Der Service schreibt die Datei und lädt das Mapping per Hot-Reload neu.

### 5.1 Struktur `leds.json`

```json
{
  "leds": [
    {
      "id": "led_5",
      "name": "Power-LED",
      "gpio": 5,
      "bindings": {
        "system_online": {
          "pattern_type": "solid"
        },
        "system_error": {
          "pattern_type": "blink",
          "interval_ms": 200,
          "repeat": 0
        }
      }
    }
  ]
}
```

Felder:

- `id`: interne LED-ID (z.B. `led_5`, `led_6` oder eine zufällige ID), vom Backend vergeben; muss für Nutzer nicht sichtbar sein.
- `name`: Klarname für WebUI/Logs (z.B. "Power-LED", "Status-LED").
- `gpio`: GPIO-Pin, an dem die LED angeschlossen ist.
- `enabled`: Ob diese LED vom Service berücksichtigt wird (wenn `false`, wird sie nicht angesteuert).
- `bindings`: Map von `logical_state` (z.B. `audio_playing`, `system_error`) auf ein Pattern-Objekt.

### 5.2 Pattern-Objekt

Ein Pattern beschreibt, **wie** die LED auf einen logischen Zustand reagieren soll:

Felder im Pattern:

- `pattern_type`: `"solid"` | `"blink"` | `"pulse"` | `"off"`.
  - `solid`: LED dauerhaft einschalten. Bleibt aktiv, bis ein anderes Pattern diese LED überschreibt. **`duration_ms` hat bei `solid` keine Wirkung** und wird beim Einlesen der Konfiguration automatisch ignoriert (mit Warning-Log). Das Feld sollte in neuen Konfigurationen weggelassen werden.
  - `blink`: an/aus im angegebenen Intervall.
  - `pulse`: kurz aufleuchten, dann wieder aus.
  - `off`: LED sofort ausschalten, ohne sichtbaren Puls (z.B. für häufig eintreffende Zustände wie `audio_stopped`/`audio_paused`).

- `duration_ms` (optional): Dauer des Patterns in Millisekunden.
  - **Nicht anwendbar bei `solid`** – wird ignoriert (siehe oben).
  - Bei `pulse`: wie lange die LED pro Puls eingeschaltet bleibt.

- `interval_ms` (optional, nur für `blink`): Intervall zwischen an/aus in Millisekunden (z.B. 1000 = langsam, 200 = schnell).

- `repeat` (optional): Anzahl der Wiederholungen.
  - `1`: einmal ausführen.
  - `0` oder nicht gesetzt: unendlich, bis ein anderer Zustand die LED überschreibt.

Beispiele:

- `solid` dauerhaft an (kein `duration_ms` nötig):

```json
{
  "pattern_type": "solid"
}
```

- schnelles Blinken bei Fehler:

```json
{
  "pattern_type": "blink",
  "interval_ms": 200,
  "repeat": 0
}
```

- einmaliger Puls bei RFID-Scan:

```json
{
  "pattern_type": "pulse",
  "duration_ms": 500,
  "repeat": 1
}
```

### 5.3 Verhalten bei fehlenden Bindings

- Wenn für einen logischen Zustand (`logical_state`) in `bindings` **kein** Pattern definiert ist, verändert dieser Zustand die LED nicht.
- Mehrere LEDs dürfen denselben logischen Zustand binden (z.B. mehrere LEDs für `system_error`).

---

## 6. Kern-Funktionen / Use-Cases

### 6.1 Zustandsableitung aus MQTT

Der LED-Service leitet logische Zustände aus MQTT-Nachrichten ab, z.B.:

- `audio/status` mit `state="playing"` → `audio_playing`.
- `audio/status` mit `state="paused"` → `audio_paused`.
- `audio/status` mit `state="stopped"` → `audio_stopped`.
- `rfid/tag-scanned` → `rfid_scanned`.
- `rfid/tag-removed` → `rfid_removed`.
- `rfid/unknown-tag` → `rfid_unknown_tag`.
- `rfid/tag-blocked` → `rfid_tag_blocked`.
- `system/service-started` → `system_online`.
- `system/service-error` → `system_error`.
- `system/booting` → `system_booting`.
- `button/raw-event` → `button_pressed`.
- `backend/unreachable` → `backend_unreachable`.
- `led/usage-denied` → `usage_denied`.

Diese Zuordnung (welches Topic → welcher `logical_state`) wird im LED-Service-Code oder in einer separaten Mapping-Konfiguration festgelegt.

### 6.2 Pattern-Ausführung

Ablauf pro LED:

1. Ein logischer Zustand wird erkannt (z.B. `audio_playing`).
2. Der Service sucht das Pattern aus `bindings[audio_playing]` für diese LED.
3. Das Pattern wird angewendet:
   - `solid`: LED dauerhaft an – kein Timeout, kein sleep.
   - `blink`: LED toggelt im angegebenen Intervall, ggf. `repeat`-mal oder unendlich.
   - `pulse`: LED wird für `duration_ms` eingeschaltet, dann wieder ausgeschaltet, ggf. mehrfach.
4. Bei einem neuen Zustand mit Binding für dieselbe LED wird das vorherige Pattern abgebrochen/überschrieben.

### 6.3 FIFO-Verarbeitung

- Eingehende Zustandsereignisse (abgeleitet aus MQTT) werden in einer FIFO-Queue verarbeitet.
- So werden Zustandänderungen in der Reihenfolge ihres Auftretens abgearbeitet und das Verhalten bleibt deterministisch.

---

## 7. Abhängigkeiten

- **Hardware:**
  - GPIO-Pins für einfarbige LEDs.

- **MQTT-Broker:**
  - Verbindung zu Mosquitto (Host/Port aus globaler `.env`).

- **Andere Services:**
  - Audio-Service (`audio/status`).
  - RFID-Service (`rfid/tag-scanned`, ggf. Fehlerstatus).
  - Backend/System-Service (`system/service-started`, `system/service-error`).
  - Button-Service (`button/raw-event`).

- **Backend-Service:**
  - Verwalten der LED-Konfiguration (Erstellen/Bearbeiten/Löschen von LEDs).
  - Senden von `led/config/update`-Messages.

- **WebUI:**
  - UI zur Zuweisung von logischen Zuständen zu LEDs und Patterns.

- **Konfiguration:**
  - Globale `.env` (Root): `MINABOX_DEVICE_ID`, `MQTT_BROKER`, `MQTT_PORT` etc.
  - Service-spezifische JSON: `config/leds.json`.

---

## 8. Fehler & Status

### 8.1 Typische Fehlerfälle

- `gpio_init_failed` – GPIO-Pin konnte nicht initialisiert werden.
- `invalid_led_config` – Config-Datei syntaktisch ungültig oder unvollständig.
- `unsupported_pattern` – Pattern-Typ nicht unterstützt.

### 8.2 Verhalten bei Config-Fehlern

- Bei ungültiger neuer Config (`led/config/update`):
  - Service verwirft die neue Config, behält die alte bei.
  - Antwort über `led/config/response` mit `success=false` und Fehlergrund.

- Bei Start mit ungültiger Config-Datei:
  - Service geht in einen Fehlerzustand.
  - LEDs bleiben in einem definierten Fallback-Zustand (z.B. alle aus oder Fehlerblinken für eine spezielle LED).

### 8.3 Logging

- Wichtige Ereignisse und Fehler werden strukturiert geloggt:
  - `led_state_change` mit `led_id`, `logical_state`, `pattern_type`.
  - `config_update_received` / `config_update_applied` / `config_update_failed`.
  - `gpio_error` mit Pin-Nummer und Fehlerursache.
  - `solid_pattern_duration_ignored` – Warning, wenn eine `solid`-Konfiguration ein nicht-null `duration_ms` enthält.
- Die Log-Konfiguration folgt den globalen Logging-Regeln aus dem Framework (structlog, JSON-Logging, Level-Definitionen).

---

## 9. Nicht-Ziele / Abgrenzung

- Keine komplexen Animations-Frameworks oder Farbverläufe (nur einfache Patterns für einfarbige LEDs).
- Keine Interpretation von Business-Logik – der Service reagiert nur auf abgeleitete logische Zustände.
- Kein direktes Triggern anderer Services – Kommunikation verläuft nur passiv über MQTT-Subscriptions.

---

## 10. Refactoring-Checkliste

- [ ] **Keine groben Inkonsistenzen:** LED-Controller, Patterns und State-Management in core; MQTT in infrastructure.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei" in diesem Dokument aktualisieren.
