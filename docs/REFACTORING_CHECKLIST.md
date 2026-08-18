# Refactoring-Checkliste Minabox

Dieses Dokument bündelt potentielle Verbesserungen und identifizierte Inkonsistenzen im Code, um ein gezieltes Refactoring zu ermöglichen. Die Details pro Service stehen in den jeweiligen Architecture-Dokumenten; hier der Überblick und übergreifende Punkte.

---

## 1. Allgemeine Punkte

- [ ] Code-Qualität: Framework-Vorgaben (Ruff, mypy, structlog) einhalten; Pre-commit prüfen.
- [ ] Tests: Fehlende Unit-/Integrationstests für kritische Pfade ergänzen.
- [ ] Dokumentation: Nach Refactoring die betroffenen Architecture.md-Abschnitte (Dateistruktur, Funktion pro Datei) aktualisieren.

---

## 2. Pro Service (Verweise)

| Service | Architecture-Dokument | Refactoring-Checkliste (im Dokument) |
|--------|----------------------|-------------------------------------|
| shared-lib | [services/shared-lib/Architecture.md](services/shared-lib/Architecture.md) | Abschnitt 6 |
| Backend | [services/backend/Architecture.md](services/backend/Architecture.md) | Abschnitt 9 |
| Audio | [services/audio/Architecture.md](services/audio/Architecture.md) | Abschnitt 14 |
| Display | [services/display/Architecture.md](services/display/Architecture.md) | Abschnitt 8 |
| Host-Helper | [services/host-helper/Architecture.md](services/host-helper/Architecture.md) | Abschnitt 8 |
| Button | [services/button/Architecture.md](services/button/Architecture.md) | Abschnitt 9 |
| LED | [services/led/Architecture.md](services/led/Architecture.md) | Abschnitt 10 |
| RFID | [services/rfid/Architecture.md](services/rfid/Architecture.md) | Abschnitt 8 |
| WebUI | [services/webui/Architecture.md](services/webui/Architecture.md) | Abschnitt 12 (siehe auch [services/webui/Redesign.md](services/webui/Redesign.md)) |

### 2.1 Kurzfassung der Service-Checklisten

- **shared-lib:** Keine groben Inkonsistenzen; optional gemeinsame Topic-Helfer/Konstanten zentralisieren.
- **Backend:** `core/mqtt_handlers.py` in thematische Handler-Module aufteilen; Sleep-Timer-Logik optional in eigenes Feature-Modul bündeln.
- **Audio:** Keine groben Inkonsistenzen; State/Config/MQTT klar getrennt.
- **Display:** `main.py` optional entlasten (Poll-Loops, Area-Build in eigene Module).
- **Host-Helper:** `api/routes.py` nach Domänen in mehrere Route-Module aufteilen.
- **Button, LED, RFID:** Keine groben Inkonsistenzen; nach Refactoring Doku aktualisieren.
- **WebUI:** Struktur-Doku an Code angepasst; Konsistenz Komponenten-/API-Namen in Doku prüfen. Redesign-Review mit priorisierter Umsetzungsreihenfolge (Nginx-Upstream-Fix, Mobile-Navigation, Datenschicht-Vereinheitlichung, neue Features) in [services/webui/Redesign.md](services/webui/Redesign.md).

---

## 3. Übergreifende Inkonsistenzen

### 3.1 Backend: `core/mqtt_handlers.py`

- **Problem:** Eine sehr große Datei bündelt viele Verantwortlichkeiten: RFID (Tag-Scan, Learning, Tag-Removed), Button-Actions, Audio-Status, Sleep-Timer, Bedtime-Fade, Playback-Events, Stream-Reconnect.
- **Empfehlung:** Aufteilung in thematische Handler-Module (z. B. `rfid_handlers.py`, `button_handlers.py`, `sleep_timer.py`, `playback_events.py`) mit gemeinsamer Basis; MQTT-Dispatcher ruft die jeweiligen Handler auf.
- **Siehe:** [services/backend/Architecture.md](services/backend/Architecture.md) – Dateistruktur und Refactoring-Checkliste.

### 3.2 Backend: Sleep-Timer-Logik

- **Problem:** Sleep-Timer-Logik verteilt auf `core/mqtt_handlers.py`, `core/sleep_settings.py` und REST in `api/routes_audio.py`.
- **Empfehlung:** Dokumentieren und optional als eigenes Feature-Modul bündeln (z. B. `core/sleep_timer.py` + API-Anbindung in `routes_audio.py`).

### 3.3 Display: `main.py`

- **Problem:** `DisplayService` in `main.py` vereint Orchestrierung, Render-Loop, Sleep-Timer-Poll, Session-Poll, MQTT-Handling, Area-Building und API-Server.
- **Empfehlung:** Optional: Poll-Loops und Area-Build-Logik in eigene Module auslagern (z. B. `core/display_runner.py`, `core/area_builder.py`), `main.py` nur Orchestrierung.

### 3.4 Host-Helper: `api/routes.py`

- **Problem:** Eine sehr große `routes.py` mit vielen Endpoints (Audio-Pfad, Move, Reboot, WiFi, USB, Backup, System, Bluetooth, Zeit, Hostname, Factory Reset, Update, etc.).
- **Empfehlung:** Aufteilung nach Domänen in mehrere Route-Module (z. B. `routes_system.py`, `routes_wifi.py`, `routes_usb.py`, `routes_backup.py`, `routes_bluetooth.py`) und in der FastAPI-App zusammenführen.

### 3.5 WebUI: Dokumentation vs. Code

- **Problem:** Die Architecture.md beschrieb teilweise andere Komponenten- und API-Namen als der aktuelle Code.
- **Status:** Datei- und Ordnerstruktur in Abschnitt 3 wurde an die tatsächliche Codebasis angeglichen (auth.ts, system.ts, ConfigForm/ mit Untermodulen, AuthSection, SecurityPanel, etc.). Refactoring-Checkliste in [services/webui/Architecture.md](services/webui/Architecture.md) Abschnitt 12 nennt weitere Abgleichpunkte.

---

## 4. Nach dem Refactoring

- Architecture.md der betroffenen Services aktualisieren (Dateistruktur, Funktion pro Datei).
- Diese Checkliste abhaken bzw. erledigte Punkte entfernen oder als „erledigt“ markieren.
