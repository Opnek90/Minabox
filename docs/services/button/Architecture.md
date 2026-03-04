# Button-Service – Architecture

## 1. Zweck & Verantwortung

Der Button-Service ist der zentrale Eingabe-Service für physische Buttons und Rotary-Encoder.
Er liest Hardware-Inputs (Push-Buttons, Rotary-Encoder) aus, wandelt sie in normierte Ereignisse um und wendet eine konfigurierbare Mapping-Logik an, um daraus logische Aktionen abzuleiten.

Ziele:

- Abstrakte Anbindung verschiedener Eingabetypen (Push-Button, Rotary-Encoder).
- Konfigurierbares Mapping "Hardware-Input → logische Aktion" pro Box.
- Flexibel in der Anzahl und Art der Buttons (2, 4, 6 Buttons etc.).

Nicht-Ziele:

- Keine direkte Wiedergabelogik (kein Wissen über Playlists/Songs).
- Kein Schreiben in die Datenbank (Mapping-Verwaltung erfolgt im Backend).
- Keine WebUI-Logik (nur Eingabe-Events und Config-Updates).

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/button-service/src/button_service/`

```text
button_service/
├── __init__.py              # Package-Init
├── main.py                  # Einstiegspunkt: Config, EventProcessor, MQTT, API-Server, Graceful Shutdown
├── config.py                # Lädt Env + buttons.json
├── config_schema.py         # Pydantic-Schema für Button-Config (buttons[], id, name, mode, type, gpio, actions)
├── config_manager.py        # JSON-Config (config/buttons.json), Hot-Reload
├── exceptions.py            # Service-spezifische Exceptions
├── core/
│   ├── __init__.py
│   ├── event_processor.py   # Verarbeitung Raw-Events: Mapping (basic/advanced), Action-Dispatch, MQTT-Publish
│   ├── events.py            # Event-Definitionen / Datentypen für Button-Events
│   ├── state_machine.py    # State-Machine pro Button (short_press, long_press, double_press, rotate_cw/ccw)
│   └── gpio_input_manager.py # GPIO-/Encoder-Einlesen, Roh-Events erzeugen
├── infrastructure/
│   ├── __init__.py
│   └── mqtt_client.py       # MQTT: Verbindung, Subscriptions (config/get, config/update, config/reload), Publish (Actions, config/response)
└── api/
    ├── __init__.py
    └── routes.py            # FastAPI: GET /health (Buttons, MQTT-Status)
```

---

## 3. Öffentliche Schnittstellen

### 3.1 MQTT – Actions

Der Button-Service publiziert **fertige Aktionen**, nachdem das Mapping angewendet wurde.

Topic-Schema (analog Framework):

```text
minabox/<device-id>/button/<action>
```

Typische Aktionen (Beispiele):

- `minabox/<device-id>/button/play-pause`
- `minabox/<device-id>/button/next`
- `minabox/<device-id>/button/prev`
- `minabox/<device-id>/button/volume-up`
- `minabox/<device-id>/button/volume-down`
- `minabox/<device-id>/button/mute`
- `minabox/<device-id>/button/power-off`

Payload (JSON, minimal):

```json
{
  "source": "btn_1",
  "event_type": "short_press",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

- `source`: interne Button-ID (z.B. `btn_1`, `enc_1`).
- `event_type`: z.B. `short_press`, `long_press`, `double_press`, `rotate_cw`, `rotate_ccw`.

### 3.2 MQTT – Raw-Events (optional, Debug)

Zusätzlich kann der Button-Service **Raw-Events** (vor Mapping) für Debug/Analyse publizieren:

```text
minabox/<device-id>/button/raw-event
```

Payload (JSON):

```json
{
  "button_id": "btn_1",
  "name": "Play/Pause",
  "type": "push",
  "event_type": "short_press",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

Diese Raw-Events sind optional und primär für Logging/Debugging gedacht.

### 3.3 MQTT – Config-API

Der Button-Service unterstützt eine Config-API über MQTT, um das Mapping zu verwalten.

**Topics:**

- `minabox/<device-id>/button/config/get`  
  Anfrage vom Backend, um aktuelle Config anzufordern.

- `minabox/<device-id>/button/config/update`  
  Backend sendet neue vollständige Konfiguration.

- `minabox/<device-id>/button/config/reload`  
  Service liest lokale JSON-Konfigurationsdatei neu ein.

- `minabox/<device-id>/button/config/response`  
  Service bestätigt Erfolg/Fehler einer Config-Operation.

**Update-Request (Beispiel-Payload für `config/update`):**

```json
{
  "buttons": [
    {
      "id": "btn_1",
      "name": "Play/Pause",
      "mode": "basic",
      "type": "push",
      "gpio": 17,
      "action": "play_pause"
    },
    {
      "id": "enc_1",
      "name": "Lautstärke",
      "mode": "advanced",
      "type": "rotary",
      "clk": 22,
      "dt": 23,
      "sw": 24,
      "actions": {
        "rotate_cw": "volume_up",
        "rotate_ccw": "volume_down",
        "press": "mute"
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
  "error": "invalid_button_type",
  "timestamp": "2026-02-14T13:30:05Z"
}
```

### 3.4 REST (optional)

Optional kann der Service einen HTTP-Endpoint anbieten (z.B. FastAPI):

- `GET /health` – Gesundheitszustand, erkannte Buttons/Encoder, MQTT-Status.

---

## 4. Konfigurationsmodell

Die Button-Konfiguration wird lokal in einer JSON-Datei gespeichert, z.B. `config/buttons.json`.
Der Inhalt wird vom Backend/WebUI verwaltet und per MQTT (`config/update`) in den Service gespielt. Der Service schreibt die Datei und lädt das Mapping per Hot-Reload neu.

### 4.1 Struktur `buttons.json`

```json
{
  "buttons": [
    {
      "id": "btn_1",
      "name": "Play/Pause",
      "mode": "basic",
      "type": "push",
      "gpio": 17,
      "action": "play_pause"
    },
    {
      "id": "enc_1",
      "name": "Lautstärke",
      "mode": "advanced",
      "type": "rotary",
      "clk": 22,
      "dt": 23,
      "sw": 24,
      "actions": {
        "rotate_cw": "volume_up",
        "rotate_ccw": "volume_down",
        "press": "mute"
      }
    }
  ]
}
```

Felder:

- `id`: interne Button-/Encoder-ID (z.B. `btn_1`, `enc_1`), vom Backend vergeben; muss für Nutzer nicht sichtbar sein.
- `name`: Klarname für WebUI/Logs (z.B. "Play/Pause").
- `mode`: `"basic"` oder `"advanced"`.
  - **basic**: es gibt ein Feld `action`, alle Eventtypen führen zur selben Aktion.
  - **advanced**: es gibt ein Feld `actions`, das je Eventtyp eine getrennte Aktion definiert.
- `type`: `"push"` oder `"rotary"`.
- `gpio`: (nur `push`) – GPIO-Pin für den Button.
- `clk`, `dt`, `sw`: (nur `rotary`) – exakte Pin-Bezeichnungen des Encoders.
- `action`: (nur `mode = basic`) – Name der logischen Aktion (z.B. `"play_pause"`).
- `actions`: (nur `mode = advanced`) – Map von `event_type` auf logische Aktion (z.B. `"short_press"`: `"play_pause"`).

### 4.2 Verhalten bei fehlenden Mappings

- Wenn einem Button für ein bestimmtes `event_type` **keine** Aktion zugeordnet ist, passiert einfach nichts.
- Mehrere Buttons dürfen dieselbe Aktion haben (z.B. zwei "Play/Pause"-Buttons); der Service erzwingt keine Eindeutigkeit.

---

## 5. Kern-Funktionen / Use-Cases

### 5.1 Eventtypen & State-Machine

Der Button-Service erkennt intern verschiedene Eventtypen pro Button:

- `short_press`
- `long_press`
- `double_press` (optional später)
- `rotate_cw` (Encoder clockwise)
- `rotate_ccw` (Encoder counter-clockwise)
- `press` (Encoder-Taster `sw`)

Zur Erkennung dieser Eventtypen verwendet er pro Button eine einfache **State-Machine**, die z.B. Klickdauer und Zeitabstände zwischen Klicks auswertet.

### 5.2 Basic-Modus

Im Basic-Modus (`mode = "basic"`):

- Für den Button ist nur eine Aktion (`action`) definiert.
- Egal, ob `short_press`, `long_press` oder `double_press` erkannt wird – alle führen zur **gleichen** Aktion.

Beispiel:

```json
{
  "id": "btn_1",
  "name": "Play/Pause",
  "mode": "basic",
  "type": "push",
  "gpio": 17,
  "action": "play_pause"
}
```

Internes Verhalten:

- Roh-Event (z.B. `short_press`) → Mapping → Aktion `play_pause` → MQTT-Event
  - Topic: `minabox/<device-id>/button/play-pause`

### 5.3 Advanced-Modus

Im Advanced-Modus (`mode = "advanced"`):

- Der Button hat eine `actions`-Map mit spezifischen Aktionen pro Eventtyp.

Beispiel:

```json
{
  "id": "btn_1",
  "name": "Play & Power",
  "mode": "advanced",
  "type": "push",
  "gpio": 17,
  "actions": {
    "short_press": "play_pause",
    "long_press": "power_off",
    "double_press": "next"
  }
}
```

Internes Verhalten:

- Roh-Event `short_press` → Aktion `play_pause` → `button/play-pause`.
- Roh-Event `long_press` → Aktion `power_off` → `button/power-off`.
- Roh-Event `double_press` → Aktion `next` → `button/next`.

Wenn es für einen Eventtyp keine Aktion in `actions` gibt, passiert nichts.

### 5.4 Raw-Event-Erfassung & FIFO-Verarbeitung

Ablauf intern:

1. Hardware-Ereignis wird erkannt (GPIO/Encoder).
2. Der Service erzeugt einen Raw-Event (`button_id`, `event_type`, `timestamp`).
3. Raw-Event wird in eine interne FIFO-Queue gestellt.
4. Ein Worker verarbeitet Events nacheinander (FIFO):
   - optional: Publish auf `.../button/raw-event` (Debug). 
   - Anwendung des Mappings (Basic oder Advanced).
   - ggf. Publish eines Action-Events.

So bleibt das Verhalten bei schnellen/gleichzeitigen Eingaben deterministisch.

---

## 6. Abhängigkeiten

- **Hardware:**
  - GPIO-Pins für Push-Buttons.
  - GPIO-Pins für Rotary-Encoder (`clk`, `dt`, `sw`).

- **MQTT-Broker:**
  - Verbindung zu Mosquitto (Host/Port aus globaler `.env`).

- **Backend-Service:**
  - Verwalten der Button-Konfiguration (Erstellen/Bearbeiten/Löschen von Buttons).
  - Senden von `config/update`-Messages.

- **WebUI:**
  - UI zum Anlegen/Ändern/Löschen von Buttons.
  - Anzeige von Raw-Events (optional) zur Fehlersuche.

- **Konfiguration:**
  - Globale `.env` (Root):
    - `MINABOX_DEVICE_ID`, `MQTT_BROKER`, `MQTT_PORT` etc.
  - Service-spezifische JSON: `config/buttons.json`.

---

## 7. Fehler & Status

### 7.1 Typische Fehlerfälle

- `gpio_init_failed` – GPIO-Pin konnte nicht initialisiert werden.
- `invalid_config` – Config-Datei syntaktisch ungültig oder unvollständig.
- `unsupported_type` – Button-/Encoder-Typ wird nicht unterstützt.

### 7.2 Verhalten bei Config-Fehlern

- Bei ungültiger neuer Config (`config/update`):
  - Service verwirft die neue Config, behält die alte bei.
  - Antwort über `.../button/config/response` mit `success=false` und Fehlergrund.

- Bei Start mit ungültiger Config-Datei:
  - Service geht in einen Fehlerzustand (analog RFID: `state = "error"`).
  - Es werden keine Action-Events publiziert, bis eine gültige Config vorliegt.

### 7.3 Logging

- Wichtige Ereignisse und Fehler werden strukturiert geloggt:
  - `button_event` mit `button_id`, `event_type`.
  - `action_triggered` mit `action`, `source`.
  - `config_update_received` / `config_update_applied` / `config_update_failed`.
- Die Log-Konfiguration folgt den globalen Logging-Regeln aus dem Framework (structlog, JSON-Logging, Level-Definitionen).
---

## 8. Nicht-Ziele / Abgrenzung

- Kein direktes Triggern von Audio oder anderen Services über interne Aufrufe – Kommunikation läuft ausschließlich über MQTT-Action-Events.
- Keine Persistenz von Button-Konfigurationen in einer Datenbank (Backend ist dafür zuständig).
- Keine Interpretation der Aktionen – z.B. `play_pause` ist ein reiner Aktionsname; was konkret passiert, entscheidet Backend/Audio-Service.

---

## 9. Refactoring-Checkliste

- [ ] **Keine groben Inkonsistenzen:** Event-Verarbeitung (core), Config und MQTT sind getrennt; GPIO/Encoder in core, MQTT in infrastructure.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei“ in diesem Dokument aktualisieren.
