# Display-Service – Architecture

## 1. Zweck & Verantwortung

Der Display-Service steuert ein Hardware-Display (z.B. I2C-OLED, SSD1306) und zeigt den aktuellen System- und Wiedergabe-Zustand an. Er bezieht Zustände aus MQTT (Audio-Status, Fehler) und optional aus dem Backend (Sleep-Timer) und rendert sie in konfigurierbaren Bereichen (Areas) und Elementen.

Ziele:

- Anzeige von Audio-Status (Volume, Mute, Play/Pause/Stop), Uhrzeit, Sleep-Timer und Fehlerzustand
- Konfigurierbare Anordnung (Bereiche: Header, linke/rechte Spalte) und Element-Typen
- Keine Business-Logik; nur Anzeige von Daten aus MQTT und Backend

Nicht-Ziele:

- Keine Datenbank oder Config-Verwaltung (Config wird vom Backend bereitgestellt; Display liest lokale `config/display.json` und reagiert auf Config-Reload)
- Keine direkte WebUI-Interaktion (Konfiguration über Admin-UI → Backend → Config-Datei)

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/display-service/src/display_service/`

```text
display_service/
├── __init__.py                  # Package-Init
├── main.py                      # DisplayService: Config, State, MQTT, Render-Loop, Sleep-Timer-Poll, Session-Poll, Area-Build, API-Server, Shutdown
├── config.py                    # Lädt App-Config: Env + display.json
├── config_schema.py             # Pydantic: DisplayElement (type, area, order), DisplayServiceConfig, AppConfig; Element-Typen (volume, sleep_timer, clock, …)
├── config_manager.py            # Thin Wrapper um shared_lib JsonConfigManager für Display-Config, Hot-Reload
├── exceptions.py                # MinaboxDisplayError, DisplayHardwareError
├── core/
│   ├── __init__.py
│   └── state_manager.py         # In-Memory-State: Audio (state, volume, muted), Sleep-Timer, Session (repeat/shuffle), Error-Flag; Updates aus MQTT und Backend-Polls
├── infrastructure/
│   ├── __init__.py
│   ├── display_controller.py    # OLED (SSD1306) über I2C: Theme/Layout, init/clear/is_available, show_areas/show_lines (Header + zwei Spalten)
│   └── mqtt_client.py            # MQTT: Subscriptions audio/status, audio/error, system/service-error, display config/reload; Message- und Config-Reload-Callbacks
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI create_app: GET /health (display_enabled, display_available, mqtt_connected, device_id)
└── models/
    ├── __init__.py
    └── schemas.py               # Pydantic HealthResponse für /health
```

---

## 3. Schnittstellen

### 3.1 REST

- **`GET /health`** – Health-Check. Response: `status`, `service`, `device_id`, `display_enabled`, `display_available`, `mqtt_connected`, `mqtt_broker`, `mqtt_port`.

Es gibt keine weiteren REST-Endpoints; Konfiguration erfolgt über die Config-Datei und MQTT Reload.

### 3.2 MQTT – Subscriptions

Der Display-Service subscribed auf:

- **`minabox/<device-id>/audio/status`** – Aktueller Audio-Status (state, volume, muted). Wird im StateManager gecacht und für Volume-, Mute- und Play-State-Elemente genutzt.
- **`minabox/<device-id>/audio/error`** – Fehler-Event; setzt internen Fehlerzustand (Anzeige z.B. über `error_state`-Element).
- **`minabox/<device-id>/system/service-error`** – System-Fehler; setzt ebenfalls Fehlerzustand.
- **`minabox/<device-id>/display/config/reload`** – Signal zum Neuladen der lokalen Config (`config/display.json`).

### 3.3 Backend-Abfrage (Sleep-Timer)

Der Service pollt periodisch (z.B. alle 5 Sekunden) **`GET <BACKEND_URL>/api/v1/audio/sleep-timer`**, um den Sleep-Timer-Status (active, remaining_ms) zu erhalten. Diese Daten werden im StateManager gecacht und für Elemente vom Typ `sleep_timer` verwendet. Kein MQTT-Topic für Sleep-Timer.

---

## 4. Konfiguration

**Datei:** `config/display.json`

**Struktur (Beispiel):**

```json
{
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60,
  "font_size": "large",
  "font": "sans",
  "elements": [
    { "id": "vol", "type": "volume", "enabled": true, "order": 0, "area": 2 },
    { "id": "mute", "type": "mute", "enabled": true, "order": 0, "area": 2 },
    { "id": "time", "type": "clock", "enabled": true, "order": 0, "area": 0 },
    { "id": "sleep", "type": "sleep_timer", "enabled": true, "order": 1, "area": 1 },
    { "id": "state", "type": "play_state", "enabled": true, "order": 1, "area": 1 },
    { "id": "error", "type": "error_state", "enabled": true, "order": 1, "area": 0 }
  ]
}
```

**Felder:**

- **enabled** – Display global ein/aus.
- **i2c_bus** – I2C-Bus-Nummer (z.B. 1 für `/dev/i2c-1`).
- **i2c_address** – I2C-Adresse (z.B. 60 für 0x3C, SSD1306).
- **font_size** – `small` | `medium` | `large`.
- **font** – `default` | `sans` | `mono`.
- **elements** – Liste von Anzeige-Elementen.

**Element:**

- **id** – Eindeutige ID (z.B. `vol`, `time`).
- **type** – Element-Typ: `volume`, `sleep_timer`, `mute`, `play_state`, `clock`, `error_state`.
- **enabled** – Ob das Element angezeigt wird.
- **order** – Reihenfolge innerhalb der Area (niedriger = weiter oben).
- **area** – Bereich: `0` = Header (volle Breite), `1` = linke Spalte, `2` = rechte Spalte.

Die Backend-API stellt **`GET /api/v1/config/display/element-types`** bereit, um die verfügbaren Typen für die Admin-UI zu liefern.

---

## 5. Kernkomponenten

- **DisplayService (main.py)** – Orchestrierung: Config laden, MQTT verbinden, Render-Loop und Sleep-Timer-Poll starten, FastAPI-Server.
- **DisplayController (display_controller.py)** – Low-Level-Zugriff auf das I2C-Display (init, clear, show_areas); prüft `is_available()`.
- **ConfigManager (config_manager.py)** – Lädt und validiert `config/display.json` (Pydantic-Schema); Hot-Reload bei MQTT-Signal.
- **StateManager (state_manager.py)** – Cacht Audio-Status (aus MQTT) und Sleep-Timer (aus Backend-Poll); liefert Daten für die Anzeige; verwaltet Fehlerzustand.
- **MQTTClient (mqtt_client.py)** – Verbindung zum Broker, Subscriptions auf audio/status, audio/error, system/service-error, display/config/reload; ruft Callbacks für State-Update und Config-Reload auf.
- **Render-Loop** – Periodisch (z.B. 1 s): State + Config → Areas aufbauen → `show_areas()` aufrufen.
- **Sleep-Timer-Poll-Loop** – Periodisch (z.B. 5 s): Backend `GET /api/v1/audio/sleep-timer` aufrufen und StateManager aktualisieren.

---

## 6. Abhängigkeiten

- **MQTT-Broker** (Mosquitto) – für audio/status, audio/error, system/service-error, display/config/reload.
- **Backend** – für Sleep-Timer-Abfrage (`GET /api/v1/audio/sleep-timer`) und optional für Config-Bereitstellung (Backend schreibt `config/display.json`; Display liest sie).
- **Hardware** – I2C-OLED (z.B. SSD1306); Zugriff über `/dev/i2c-*`. Im Container müssen I2C-Devices gemountet werden.

---

## 7. Integration im Stack

- Der Display-Service wird in der zentralen **docker-compose.yml** als Service (z.B. `display`) eingetragen und gehört zum gleichen Docker-Netzwerk wie Backend und MQTT.
- Config wird vom Backend über Volume-Mount oder Config-Sync in `config/display.json` bereitgestellt; die Admin-UI konfiguriert über `GET/PUT /api/v1/config/display`.
- Nach Config-Änderung kann das Backend (oder ein anderer Dienst) `minabox/<device-id>/display/config/reload` publishen, damit der Display-Service die Config neu lädt.

---

## 8. Refactoring-Checkliste

- [ ] **main.py vereint viele Verantwortungen:** DisplayService in `main.py` enthält Orchestrierung, Render-Loop, Sleep-Timer-Poll, Session-Poll, MQTT-Handling, Area-Building und API-Server. Optional: Poll-Loops und Area-Build-Logik in eigene Module auslagern (z. B. `core/display_runner.py`, `core/area_builder.py`); `main.py` nur Orchestrierung.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei“ in diesem Dokument aktualisieren.
