# Minabox – Optimierungen & Qualitäts-Findings

**Erstellt:** 2026-02-17  
**Status:** Offene Punkte zur schrittweisen Abarbeitung

Dieses Dokument enthält Findings aus dem Code-Review aller Services (RFID, Audio, Backend, Button, LED) vor der Erstellung des WebUI-Service. Die Einträge sind nach Priorität sortiert.

---

## Legende

- [ ] Offen
- [x] Erledigt

Prioritäten: **P0** = Bug/Blocker, **P1** = Hohe Priorität, **P2** = Mittlere Priorität, **P3** = Niedrige Priorität / Housekeeping

---

## P0 – Bugs & Blocker

### 1. LED Healthcheck-Bug in docker-compose.yml
- [x] **Datei:** `docker-compose.yml` (Zeile 245)
- **Problem:** Der Healthcheck-Befehl ist fehlerhaft:
  ```yaml
  test: ["CMD", "curl", "-f", "http://localhost:8000/health || exit 0"]
  ```
  Der String `"http://localhost:8000/health || exit 0"` wird als **ein einzelnes Argument** (die URL) an curl übergeben. Das `|| exit 0` ist kein Shell-Befehl, sondern Teil der URL.
- **Fix:** Entweder `CMD-SHELL` verwenden oder den Befehl korrigieren:
  ```yaml
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  ```

### 2. LED-Service LOG_LEVEL hat Default statt Required
- [x] **Datei:** `docker-compose.yml` (Zeile 221)
- **Problem:** `LOG_LEVEL=${LOG_LEVEL:-INFO}` verwendet einen Default-Wert, während alle anderen Services `LOG_LEVEL=${LOG_LEVEL:?LOG_LEVEL must be set in .env}` verwenden (Required, kein Default).
- **Framework:** Abschnitt 13.2 sagt explizit: *"Keine Defaults vorhanden! Services schlagen beim Start mit klarer Fehlermeldung fehl."*
- **Fix:** `LOG_LEVEL=${LOG_LEVEL:?LOG_LEVEL must be set in .env}`

### 3. Audio-Service Dockerfile CMD-Pfad falsch
- [x] **Datei:** `services/audio-service/Dockerfile` (Zeile 63)
- **Problem:** `CMD ["python", "-m", "src.audio_service.main"]` – das `src.`-Prefix ist falsch. Es sollte entweder `PYTHONPATH=/app/src` gesetzt und `CMD ["python", "-m", "audio_service.main"]` verwendet werden, oder `WORKDIR /app/src` gesetzt werden.
- **Vergleich:** Alle anderen Services verwenden `python -m <service_name>.main` ohne `src.`-Prefix.

---

## P1 – Hohe Priorität (Konsistenz & Standards)

### 4. Dependency-Versionen stark unterschiedlich
- [x] **Betroffene Dateien:** Alle `requirements.txt` und `pyproject.toml`
- **Problem:** Die Services verwenden sehr unterschiedliche Versionen derselben Libraries:

  | Library | RFID | Audio | Backend | Button | LED |
  |---------|------|-------|---------|--------|-----|
  | fastapi | 0.115 | 0.126 | 0.126 | 0.129 | 0.126 |
  | pydantic | 2.9 | 2.12.5 | 2.12.5 | 2.12 | 2.12 |
  | structlog | 24.4 | 25.4 | 25.4 | 25.5 | 25.4 |
  | aiomqtt | 2.4 | 2.4 | 2.5 | 2.5 | 2.3 |
  | tenacity | 8.4 | 9.0 | 9.1 | 9.1.4 | 9.0 |

- **Risiko:** Inkompatibilitäten, unterschiedliches API-Verhalten, erschwerte Wartung.
- **Fix:** Alle Services auf dieselben Versionen bringen. RFID-Service hat die ältesten Versionen und sollte aktualisiert werden.

### 5. Vier verschiedene Config-Management-Patterns
- [x] **Problem:** Jeder Service verwendet einen anderen Ansatz:
  - **RFID:** Manuelles `os.getenv()` + JSON-Loading in `ConfigManager`, `python-dotenv`
  - **Audio:** `pydantic_settings.BaseSettings` in ConfigManager, verschachteltes `GlobalConfig` + `AudioConfig`
  - **Backend:** `pydantic_settings.BaseSettings` mit `env_prefix` und `model_validator`
  - **Button/LED:** Manuelles `os.getenv()` in `config.py`, `EnvConfig` + Service-spezifische Config → `AppConfig`
- **Framework:** Abschnitt 13.3 definiert ein einheitliches Schema-basiertes Pattern.
- **Fix:** Einheitliches Pattern definieren. Button/LED haben den saubersten Ansatz (getrennte `EnvConfig` + Service-Config → `AppConfig`). Diesen als Standard für alle Services übernehmen.

### 6. Health-Endpoint-Pfad inkonsistent
- [x] **Problem:**
  - Audio, Backend: `/api/v1/health`
  - Button, LED: `/health`
  - RFID: **Kein Health-Endpoint!**
- **Framework:** Abschnitt 7.4 sagt: *"Jeder Service exponiert `/health`"*
- **Fix:**
  1. RFID-Service braucht einen Health-Endpoint.
  2. Pfad vereinheitlichen: `/health` (wie im Framework-Template) oder `/api/v1/health`.

### 7. MQTT-Client-Interface inkonsistent
- [x] **Problem:** Fünf verschiedene MQTT-Client-Implementierungen mit unterschiedlichen APIs:
  - **Payload-Typ:** RFID/Audio nehmen `str`, Backend/Button/LED nehmen `dict` (auto-serialize)
  - **Topic-Handling:** RFID prepended automatisch `minabox/{device_id}/`, andere verwenden den vollen Topic
  - **`is_connected`:** RFID hat `@property`, Audio/Backend haben `def is_connected()` als Methode, Button/LED haben keine Methode
  - **Message-Loop:** RFID hat `messages()` Generator, Audio hat `listen()` mit Callback, Backend hat `start_listening()` mit Handler-Registry, Button/LED haben `run()` Loop
- **Fix:** Gemeinsames Interface definieren. Idealerweise eine Basisklasse in `shared/` mit einheitlichem `publish(topic, payload_dict)`, `subscribe()`, `is_connected`, und `run()` Pattern.

### 8. main.py-Struktur inkonsistent
- [x] **Problem:** Drei verschiedene Muster:
  - **RFID:** Funktionaler Stil, kein Service-Klasse, `setup_logging()` liest ENV direkt
  - **Audio:** Kein Service-Klasse auf Top-Level, globale `_service`/`_shutdown_event`, separate `run_service()` und `start_fastapi_server()` Funktionen
  - **Backend:** Module-Level structlog-Konfiguration, `signal.signal()` statt `loop.add_signal_handler()`, FastAPI-Lifespan-Pattern
  - **Button/LED:** Saubere `Service`-Klasse, `setup_logging(log_level)` als Funktion mit Parameter, Signal-Handler via `loop.add_signal_handler()`
- **Fix:** Button/LED-Pattern als Standard übernehmen (Service-Klasse mit `start()`, `run()`, `stop()`, `request_shutdown()`).

### 9. Exception-Base-Class-Naming inkonsistent
- [x] **Problem:** Verschiedene Namenskonventionen:
  - RFID: `MinaboxRFIDError`
  - Audio: `MinaboxError` (generisch!)
  - Backend: `MinaboxError` (gleicher Name wie Audio!)
  - Button: `MinaboxButtonError`
  - LED: `MinaboxLEDError`
- **Risiko:** Audio und Backend verwenden **denselben** Klassennamen `MinaboxError`. Bei einer zukünftigen Shared-Library würde das kollidieren.
- **Framework:** Abschnitt 8.1 definiert `MinaboxError` als globale Basis, aber jeder Service sollte eine eigene Sub-Klasse haben.
- **Fix:** Einheitliches Naming: `MinaboxError` (global, in `shared/`) → `MinaboxAudioError`, `MinaboxBackendError` etc. als service-spezifische Basis.

---

## P2 – Mittlere Priorität (Code-Qualität)

### 11. Dockerfile-Patterns uneinheitlich
- [x] **Problem:** Drei verschiedene pip-Install-Strategien:
  - **RFID/Button/LED:** `pip install --no-cache-dir -r requirements.txt`, kopiert `site-packages` direkt
  - **Audio:** `pip install --no-cache-dir --user -r requirements.txt`, kopiert `/root/.local` → `/usr/local`
  - **Backend:** Erstellt ein venv (`/opt/venv`), kopiert Venv
- **Weitere Unterschiede:**
  - RFID: Kein `HEALTHCHECK` im Dockerfile, kein `EXPOSE`
  - Button/LED: `WORKDIR /app/src` (Doppelt-WORKDIR)
  - Audio: Hat `EXPOSE 8003`, Backend hat `EXPOSE 8080`
- **Fix:** Eine einheitliche Dockerfile-Vorlage verwenden. Framework Abschnitt 10.1 gibt ein Template vor – dieses konsequent anwenden.

### 12. RFID-Service fehlt `pydantic-settings` und `uvicorn`
- [x] **Problem:** RFID-Service hat keine REST-API (kein FastAPI-Router, kein Health-Endpoint). Er hat `fastapi` in den Requirements, nutzt es aber nicht produktiv.
- **Fix:** Entweder FastAPI/uvicorn entfernen (wenn kein Health-Endpoint gewünscht ist) oder einen Health-Endpoint implementieren (Framework-Vorgabe).

### 13. LED MQTT-Client hat Inline-Import
- [x] **Datei:** `services/led-service/src/led_service/mqtt_client.py` (Zeile 286)
- **Problem:** `from datetime import datetime, timezone` wird innerhalb der Methode `_send_config_response()` importiert statt am Dateianfang.
- **Fix:** Import an den Dateianfang verschieben.

### 14. Backend verwendet `signal.signal()` statt asyncio Signal-Handler
- [x] **Datei:** `services/backend-service/src/backend_service/main.py` (Zeile 195)
- **Problem:** `signal.signal(signal.SIGTERM, handle_shutdown)` ist nicht async-safe. Alle anderen Services verwenden `loop.add_signal_handler()`.
- **Fix:** Auf `loop.add_signal_handler()` umstellen (wie Button/LED).

### 15. Fehlende `from __future__ import annotations`
- [x] **Problem:** Inkonsistente Nutzung:
  - Verwendet: RFID `main.py`, `config_manager.py`; Button `main.py`, `config_schema.py`; LED `config_schema.py`
  - Fehlt: Audio `main.py`; Backend `main.py`; LED `main.py`
- **Fix:** Konsistent in allen Modulen verwenden oder weglassen. Empfehlung: Überall hinzufügen für zukunftssicheren Code (PEP 563).

### 16. Kein `models/schemas.py` im RFID-Service
- [x] **Problem:** RFID hat `models/events.py` statt `models/schemas.py`, was vom Framework-Standard abweicht (Framework Abschnitt 4.1 definiert `models/schemas.py`).
- **Fix:** Entweder umbenennen oder in der Dokumentation begründen.

---

## P3 – Niedrige Priorität / Housekeeping

### 17. Config-Dateinamen nicht einheitlich
- [x] **Problem:**
  - RFID: `config/service.json`
  - Audio: `config/audio.json`
  - Button: `config/buttons.json`
  - LED: `config/leds.json`
  - Backend: `config/backend.json` (in Doku referenziert)
- **Fix:** RFID `config/service.json` → `config/rfid.json` umbenannt. Alle Services nutzen jetzt `config/<domain>.json`.
- **Empfehlung:** Entweder alle `config/service.json` oder alle `config/<domain>.json`. Die aktuelle Benennung ist funktional nicht problematisch, aber uneinheitlich.

### 18. RFID ConfigManager erstellt globale Singleton-Instanz
- [x] **Datei:** `services/rfid-service/src/rfid_service/config_manager.py` (Zeile 147)
- **Problem:** `config_manager = ConfigManager()` auf Modul-Ebene. Kein anderer Service macht das.
- **Fix:** Entfernen und stattdessen in `main.py` oder `config.py` instanziieren.

### 19. Backend ConfigManager fehlt `config_manager.py`
- [x] **Problem:** Backend hat eine `config_manager.py`, aber diese delegiert nur an `BackendConfig` (pydantic-settings). Die Datei `config.py` enthält die eigentliche `get_config()`-Funktion. Die Aufteilung `config.py` + `config_manager.py` + `config_schema.py` ist im Backend anders als bei anderen Services.
- **Fix:** Vereinfachen und an das Button/LED-Pattern angleichen.

### 20. `typing.Optional` statt `X | None` in einigen Services
- [x] **Problem:** Mischung aus `Optional[X]` (altes Pattern) und `X | None` (Python 3.10+ Pattern) in Button und LED Services.
- **Fix:** `Optional[X]` → `X | None` in allen 5 Services ersetzt (22 Dateien). `Optional` aus `from typing import`-Zeilen entfernt.

### 21. Docker-Compose: Audio-Volume-Mount mit Kommentar `← GEÄNDERT`
- [x] **Datei:** `docker-compose.yml` (Zeile 65, 141)
- **Problem:** Kommentare `# ← GEÄNDERT` sollten entfernt werden – sie sind Entwickler-Notizen, keine Dokumentation.
- **Fix:** Kommentare entfernt. Zusätzlich: Startreihenfolge explizit definiert (mqtt → backend → audio → rfid/button/led → webui), Backend-Healthcheck in `docker-compose.yml` ergänzt, Services in der gewünschten Reihenfolge sortiert.

---

## Dokumentations-Findings

### D1. Framework.md Projekt-Struktur-Pfad falsch
- [x] **Problem:** Framework.md Abschnitt 2 listet `docs/Framework.md` als Pfad – die Datei lag im Root als `Framework.md`.
- **Fix:** `Framework.md` nach `docs/Framework.md` verschoben. Verweise in `services/backend-service/README.md` und `services/rfid-service/README.md` auf `docs/Framework.md` angepasst.

### D2. Audio Architecture.md – Dependency-Versionen veraltet
- [x] **Datei:** `docs/services/audio/Architecture.md` (Abschnitt 9.2)
- **Problem:** Listet alte Versionen: `aiomqtt==2.3.0`, `structlog==24.4.0`, `pydantic==2.10.5`, `fastapi==0.115.6`. Die tatsächlichen Requirements sind neuer.
- **Fix:** Abschnitt 9.2 verweist jetzt auf `services/audio-service/requirements.txt` und enthält nur noch eine Kurzüberblick-Liste ohne feste Versionen.

### D3. Audio Architecture.md – Exception-Klassen stimmen nicht überein
- [x] **Datei:** `docs/services/audio/Architecture.md` (Abschnitt 2.3)
- **Problem:** Dokumentation nannte `AudioServiceError`, `AudioBackendError`, `VLCInitializationError`, `AudioDeviceNotFoundError`. Der Code verwendet `MinaboxAudioError`, `AudioError`, `VLCError`, `OutputDeviceError` etc.
- **Fix:** Exception-Liste in der Doku an die tatsächliche Hierarchie in `exceptions.py` angeglichen.

### D4. Backend Architecture.md – MQTT-Library
- [x] **Datei:** `docs/services/backend/Architecture.md` (Abschnitt 5)
- **Problem:** Listet `paho-mqtt oder aiomqtt`. Es wird ausschließlich `aiomqtt` verwendet.
- **Fix:** Nur noch `aiomqtt` – asynchroner MQTT-Client – dokumentiert.

### D5. WebUI Architecture.md – Docker-Compose Broker-Name
- [x] **Datei:** `docs/services/webui/Architecture.md` (Abschnitt 7.3)
- **Problem:** Beispiel-Compose verwendete `mosquitto` als Service-Name und `MQTT_BROKER=mosquitto`. Das tatsächliche Compose verwendet `mqtt`.
- **Fix:** Service-Name und Umgebungsvariable im Beispiel auf `mqtt` angepasst.

### D6. RFID Architecture.md – Fehlende MQTT-Config-API-Dokumentation
- [x] **Problem:** Der RFID-Service hat keine dokumentierte Config-API über MQTT (wie Button und LED). Es war unklar, ob das generische Config-Update-Pattern unterstützt wird.
- **Fix:** In Abschnitt 2.1 ausdrücklich dokumentiert, dass der RFID-Service **kein** generisches Config-API-Pattern (config/get, config/update, config/response) unterstützt; Konfiguration über `config/rfid.json`, Laufzeit-Steuerung nur via `cmd/set-mode` und `cmd/reload-config`. Zusätzlich alle Verweise auf `config/service.json` in `config/rfid.json` geändert (RFID Architecture + config_schema.py).

---

## Vorschläge für zukünftige Verbesserungen

### V1. Shared Library (`shared/`)
- [ ] **Beschreibung:** Gemeinsamen Code in eine `shared/`-Library extrahieren:
  - `shared/logging.py` – Einheitliche `setup_logging(log_level: str)` Funktion
  - `shared/mqtt_client.py` – Basis-MQTT-Client mit einheitlichem Interface
  - `shared/config.py` – Einheitliches `EnvConfig`-Pattern
  - `shared/exceptions.py` – `MinaboxError` Base-Klasse
- **Vorteil:** DRY, einfachere Wartung, garantierte Konsistenz.
- **Hinweis:** Framework Abschnitt 2 sieht `shared/` bereits vor, es wird aber noch nicht genutzt.

### V2. Pre-commit Hooks aktivieren
- [ ] **Beschreibung:** `.pre-commit-config.yaml` ist im Framework dokumentiert, aber es ist unklar ob `pre-commit install` auf dem Entwicklungsrechner ausgeführt wurde.
- **Fix:** Sicherstellen, dass Pre-commit Hooks installiert und aktiv sind. Optional: CI/CD-Pipeline, die Ruff/Mypy bei jedem Commit prüft.

### V3. Tests
- [ ] **Beschreibung:** Aktuell existieren keine Tests für die Services (keine Dateien unter `tests/`). Framework Abschnitt 9 definiert die Test-Philosophie.
- **Fix:** Mindestens Unit-Tests für Business-Logic und API-Endpoints pro Service erstellen.

---

**Letzte Aktualisierung:** 2026-02-17
