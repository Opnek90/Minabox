# Minabox - Framework Guidelines

**Version:** 1.7.0  
**Letzte Änderung:** 2026-02-15

Dieses Dokument definiert die technischen Standards und Best Practices für das gesamte Minabox-Projekt. Alle Services müssen diesen Richtlinien folgen, um Konsistenz, Wartbarkeit und Qualität sicherzustellen.

---

## 1. Technologie-Stack

### Core

- **Sprache:** Python 3.13+  
- **Package Management:** Poetry oder pip-tools  
- **Container:** Docker & Docker Compose  
- **Orchestrierung:** Zentrales `docker-compose.yml` im Root-Repository  

### Development

- **IDE:** Frei wählbar (VSCode empfohlen)  
- **Git:** Konventionelle Commit-Messages  
- **Branching:** Feature-Branches, `main` = stabiler Stand  

---

## 2. Projekt-Struktur (Root-Repository)

Das Root-Repository ist wie folgt strukturiert:

```text
docker-compose.yml       # ZENTRALES Compose-File für alle Services

docs/
  Framework.md           # Dieses Dokument
  services/              # Fachliche Doku & Checklisten pro Bereich
    rfid/
      Architecture.md    # RFID-Service Architektur (vorhanden)
    audio/
      Architecture.md    # Audio-Service Architektur (vorhanden)
    backend/
      Architecture.md    # Backend-Service Architektur (vorhanden, deckt API & DB ab)
    webui/
      Architecture.md    # WebUI-Service Architektur (vorhanden)
    led/
      Architecture.md    # LED-Service Architektur (vorhanden)
    button/
      Architecture.md    # Button-Service Architektur (vorhanden)
    host-helper/
      Architecture.md    # Host-Helper-Service Architektur (systemnahe Aktionen)
    api/                 # Optionale zusätzliche API-Dokumentation (geplant)

services/                # Technische Services (Implementierungen)
  rfid-service/
  audio-service/
  backend-service/
  webui-service/
  led-service/
  button-service/
  host-helper-service/   # Optional: systemnahe Aktionen, nur vom Backend angesprochen
  shared-lib/            # Gemeinsame Config/Exceptions/MQTT-Basis (Paket: minabox-shared, Import: shared_lib)
infrastructure/          # Infrastruktur-Konfigurationen (Mosquitto-Config, Monitoring, CI/CD)
scripts/                 # Hilfsskripte (dev-tools.sh, setup-folders.sh, test_display.py)
```

**Hinweise:**

- **`docker-compose.yml` liegt direkt im Root** und orchestriert alle Services (MQTT-Broker, Backend, Audio, RFID, LED, Button, WebUI, optional Host-Helper).
- `infrastructure/` enthält nur Konfigurationsdateien für Infrastruktur-Komponenten (z.B. `mosquitto.conf`, Prometheus-Config, Grafana-Dashboards), aber **kein** eigenes Compose-File.
- Jeder Service-Ordner unter `services/` verwendet die Standardstruktur aus Kapitel **4. Projekt-Struktur pro Service**.
- Für jeden fachlichen Bereich existiert eine `Architecture.md` unter `docs/services/<bereich>/`.
- `docs/services/backend/Architecture.md` deckt sowohl die REST-API als auch die Datenbankschicht ab, da der Backend-Service beide Verantwortlichkeiten innehat.
- Alle Architecture.md-Dateien für die Hauptservices (RFID, Audio, Backend, WebUI, LED, Button) sind bereits vorhanden und beschreiben Aufgaben, Schnittstellen und Konfigurationsmodelle.
- Der **Host-Helper-Service** (optional) kapselt systemnahe Aktionen auf dem Host (z.B. Dateien verschieben); er wird nur intern vom Backend angesprochen und ist nicht nach außen exponiert. Siehe `docs/services/host-helper/Architecture.md`.
- **Gemeinsame Python-Bausteine** (Config, Exceptions, MQTT-Basis) liegen in `services/shared-lib` (Paket **minabox-shared**, Import **shared_lib**). Siehe `services/shared-lib/README.md`.

---

## 3. Code-Qualität Standards

### 3.1 Tools

**Linting & Formatting:**

- **Ruff v0.15.0+** – Linting, Import-Sortierung, Code-Modernisierung **und Formatting**  
- ~~**Black 25.11.0** – Code-Formatting (88 Zeichen, einheitlicher Stil)~~ **DEPRECATED: Use `ruff format` instead**
- **mypy 1.20.0** – Type-Checking (moderate Strenge)

> **⚠️ Important:** Black has been replaced by `ruff format` as of 2026-02-15. Ruff provides faster formatting with the same opinionated style while maintaining full compatibility. The pre-commit configuration has been updated to use `ruff-format` exclusively.

**Konfiguration in `pyproject.toml`:**

```toml
# Black-Konfiguration wird für Kompatibilität beibehalten, aber nicht mehr verwendet
[tool.black]
line-length = 88
target-version = ['py313']

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]

[tool.ruff.format]
# Ruff Format verwendet Black-kompatible Defaults
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.13"
warn_unused_configs = true
disallow_untyped_defs = true
warn_return_any = true
```

### 3.2 Pre-commit Hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.1
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Black wurde durch ruff-format ersetzt (2026-02-15)
  # - repo: https://github.com/psf/black
  #   rev: 26.1.0
  #   hooks:
  #     - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.1
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
        additional_dependencies:
          - types-requests
          - types-PyYAML
          - pydantic
```

Setup:

```bash
pip install pre-commit
pre-commit install
```

Optional: `./scripts/dev-tools.sh install` installiert die Hooks; `./scripts/dev-tools.sh format` formatiert den Code, `./scripts/dev-tools.sh check` führt Linting und Type-Check aus.

### 3.3 Type-Hints

Alle Funktionen müssen Type-Hints haben:

```python
from typing import Optional

def process_tag(tag_id: str, timeout: int = 5) -> Optional[str]:
    """Process RFID tag."""
    ...
```

---

## 4. Projekt-Struktur pro Service

### 4.1 Standard-Struktur

```text
service-name/                   # z.B. rfid-service/, audio-service/
├── src/
│   └── service_name/          # z.B. rfid_service/
│       ├── __init__.py
│       ├── main.py            # Einstiegspunkt
│       ├── api/               # REST-Endpoints (FastAPI)
│       │   ├── __init__.py
│       │   └── routes.py
│       ├── core/              # Business-Logic
│       │   ├── __init__.py
│       │   └── logic.py
│       ├── models/            # Data-Models (Pydantic)
│       │   ├── __init__.py
│       │   └── schemas.py
│       ├── config_schema.py   # Service Config Schema
│       ├── config_manager.py  # Config Manager
│       └── config.py          # Config Loading
├── tests/
│   ├── unit/
│   └── integration/
├── config/
│   └── service.json           # Service-spezifische Config
├── Dockerfile
├── docker-compose.yml         # Optional: lokales Compose für Einzelservice-Tests
├── pyproject.toml
├── requirements.txt           # Für Docker-Build
└── README.md
```

**Hinweise:** Die Architektur-Dokumentation liegt zentral unter `docs/services/<bereich>/Architecture.md`. Einzelne Services können ein lokales `docker-compose.yml` für isolierte Entwicklung/Tests haben; optional ein `scripts/`-Ordner für Build- oder Hilfsskripte (z. B. Icon-Generierung, Locale-Merge). Für den produktiven Betrieb wird aber **nur** das zentrale `docker-compose.yml` im Root verwendet.

**MQTT-Client-Platzierung:** Die MQTT-Client-Implementierung gehört in der Regel unter **`infrastructure/`** (z. B. `infrastructure/mqtt_client.py`), da es sich um Transport-/Kommunikationsschicht handelt. Beim Backend-Service darf MQTT ausnahmsweise unter **`core/`** liegen, wenn er stark in die Business-Logik (Handlers, Session) eingebunden ist; neue Services sollten `infrastructure/` bevorzugen.

**Abweichungen von der Standard-Struktur:** Der **Backend-Service** baut die FastAPI-App in einer eigenen **`app_factory.py`** und setzt den API-Router aus mehreren `routes_*.py` in `api/__init__.py` zusammen (kein einzelnes `create_app` in `api/routes.py`). Der **Host-Helper-Service** hält bewusst eine schlanke Config (nur `config.py`, env-basiert, optional ohne `config_schema`/`config_manager`) und nutzt **shared-lib** für Exceptions und ggf. Env-Loading.

### 4.2 Namenskonventionen

- **Services (Ordner):** `lower-kebab-case` – z.B. `rfid-service`, `audio-service`  
- **Python-Packages:** `lower_snake_case` – z.B. `rfid_service`, `audio_service`  
- **Funktionen:** `snake_case` – z.B. `read_tag()`, `play_audio()`  
- **Klassen:** `PascalCase` – z.B. `RFIDReader`, `AudioPlayer`  
- **Konstanten:** `UPPER_CASE` – z.B. `MAX_VOLUME`, `DEFAULT_TIMEOUT`  

---

## 5. Service-Kommunikation

### 5.1 Architektur: Hybrid MQTT + REST

**MQTT (asynchron, Event-Driven):**

- Hardware-Events (Buttons, RFID-Scan)  
- Status-Änderungen (Playback, Volume)  
- System-Events (Service-Start, Fehler, Health-Status)  

**REST (synchron):**

- Status-Abfragen: `GET /api/v1/audio/status`  
- Commands: `POST /api/v1/audio/play`  
- Konfiguration & Admin: z.B. `GET /api/v1/rfid/tags`  

### 5.2 MQTT Broker

- **Technologie:** Eclipse Mosquitto 2.1+  
- **Port:** 1883 (Standard)  
- **Docker Service Name:** `mqtt` (nicht `mosquitto`)  
- Broker läuft als Container, konfiguriert im zentralen `docker-compose.yml` im Root.
- Konfigurationsdateien liegen unter `infrastructure/mosquitto/` (z.B. `mosquitto.conf`).

### 5.3 MQTT Topic-Schema

Globales Schema:

```text
minabox/<device-id>/<domain>/<action>
```

- `<device-id>`: Eindeutige ID der Box (z.B. `box1`, `livingroom`, `kidsroom`)
- `<domain>`: Fachbereich, z.B. `rfid`, `button`, `audio`, `system`, `led`.
- `<action>`: Konkretes Event oder Kommando, z.B. `tag-scanned`, `play`, `status`.

Beispiele:

```text
# RFID
minabox/box1/rfid/tag-scanned
minabox/box1/rfid/tag-removed

# Buttons
minabox/box1/button/play-pause
minabox/box1/button/next
minabox/box1/button/prev
minabox/box1/button/volume-up

# Audio
minabox/box1/audio/play
minabox/box1/audio/pause
minabox/box1/audio/stop
minabox/box1/audio/status

# System
minabox/box1/system/service-started
minabox/box1/system/service-error
minabox/box1/system/online

# LED
minabox/box1/led/config/update
```

**Namenskonvention:**

- Nur Kleinbuchstaben, Ziffern, Bindestrich oder Unterstrich  
- Keine Leerzeichen, keine doppelten `/`  
- `<device-id>` ist Pflicht, damit mehrere Boxen parallel betrieben werden können  

### 5.4 MQTT QoS, Wildcards & Retain

**QoS:**

- Standard: **QoS 1** (`at least once`) für Steuer- und Event-Topics (RFID, Button, Audio-Kommandos)  
- Optional: **QoS 0** für häufige, nicht-kritische Telemetrie (z.B. Fortschritt/Debug)  

**Wildcards:**

- `+` für genau eine Ebene, z.B.:

  ```text
  minabox/+/rfid/tag-scanned        # Alle Geräte
  ```

- `#` nur in Debug-/Analyse-Tools, **nicht** im produktiven Service-Code, z.B.:

  ```text
  minabox/box1/#                    # Debug-Client für eine Box
  ```

- Wildcards nur als komplette Topic-Ebene verwenden, nicht innerhalb eines Wortes.  

**Retained Messages:**

- Retain **AN** für Zustände:

  ```text
  minabox/<device-id>/audio/status
  minabox/<device-id>/system/online
  ```

- Retain **AUS** für einmalige Events:

  ```text
  minabox/<device-id>/rfid/tag-scanned
  minabox/<device-id>/button/pressed
  ```

Ziel: Neue Subscriber bekommen den aktuellen Status, aber keine alten Events.

### 5.5 Backend als MQTT–WebSocket-Bridge

**Backend-Service:**

- Subscribed auf relevante MQTT-Topics (RFID, Buttons, Audio-Status, System)  
- Aggregiert Events und Status  
- Schiebt Events/Status via WebSocket an die WebUI  
- Exponiert REST-API für Queries/Commands  

**WebUI:**

- Verbindung zum Backend via WebSocket (Real-Time Updates)  
- REST-Calls für Commands (Play, Pause, Config)  
- Kein direkter MQTT-Zugriff (Security & Vereinfachung)  

**Warum kein direktes MQTT im WebUI:**

- Einfachere Frontend-Implementierung (nur HTTP/WebSocket)  
- Backend kann filtern, aggregieren, validieren  
- Services bleiben im internen Netz, nicht direkt exponiert  

### 5.6 MQTT Message Format

JSON mit Timestamps:

```json
{
  "event": "tag_scanned",
  "data": {
    "tag_id": "ABC123",
    "reader_id": "pn532_01"
  },
  "timestamp": "2026-02-14T13:30:00Z"
}
```

---

## 6. Generisches Config-Update-Pattern über MQTT

Mehrere Services (z.B. Button-, LED-, RFID-Service) verwenden ein einheitliches Muster für Konfigurationsupdates über MQTT.

### 6.1 Prinzip

- Service-spezifische Konfiguration wird in einer JSON-Datei im Service-Ordner gehalten (z.B. `config/buttons.json`, `config/leds.json`, `config/service.json`).
- Das Backend/WebUI verwaltet diese Konfigurationen zentral (CRUD-UI) und sendet Änderungen via MQTT an den jeweiligen Service.
- Der Service validiert die neue Config, schreibt sie in die lokale JSON-Datei und wendet sie per Hot-Reload an.

### 6.2 Standard-Topics für Config-API

Für jeden Service, der konfigurierbar ist, gelten folgende Muster (Domain = Service-Name):

- `minabox/<device-id>/<domain>/config/get`  
  - Anfrage vom Backend, um die aktuelle Config zu erhalten.

- `minabox/<device-id>/<domain>/config/update`  
  - Backend sendet eine **vollständige** neue Konfiguration.

- `minabox/<device-id>/<domain>/config/reload`  
  - Service liest die lokale JSON-Datei neu ein (z.B. nach manueller Änderung).

- `minabox/<device-id>/<domain>/config/response`  
  - Service bestätigt das Ergebnis einer Config-Operation.

**Beispiele:**

- Button-Service: `domain = button` → `minabox/box1/button/config/update`  
- LED-Service: `domain = led` → `minabox/box1/led/config/update`  
- RFID-Service (optional): `domain = rfid` → `minabox/box1/rfid/config/update`

### 6.3 Payload-Konventionen

**Update-Request (`config/update`):**

- Enthält die vollständige, service-spezifische Konfiguration als JSON.
- Beispiel: siehe `buttons.json` bzw. `leds.json` in den jeweiligen Architecture-Dokumenten.

**Response (`config/response`):**

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
  "error": "invalid_config",
  "timestamp": "2026-02-14T13:30:05Z"
}
```

### 6.4 Verhalten bei Config-Fehlern

- Services validieren eingehende Konfigurationen **vor** dem Schreiben:
  - Bei ungültiger Config: keine Änderungen an der lokalen Datei, `success=false` + Fehlercode in `config/response`.
  - Bei gültiger Config: Datei wird überschrieben, Hot-Reload wird durchgeführt, `success=true`.
- Startet ein Service mit ungültiger Konfigurationsdatei, geht er in einen Fehlerzustand (z.B. `state = "error"`) und wartet auf eine gültige Config vom Backend.

Dieses Muster soll für alle konfigurierbaren Services konsistent umgesetzt werden (Button, LED, ggf. RFID, Audio, Backend).

---

## 7. Logging & Monitoring

### 7.1 Logging-Framework

- **Library:** `structlog` (strukturiertes Logging)
- **Format:** Abhängig vom `LOG_LEVEL` (siehe 7.2)

Konfiguration in jedem Service (`main.py`):

```python
import os
import logging
import structlog

# Get log level from environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level_int = getattr(logging, LOG_LEVEL, logging.INFO)

# Choose renderer based on log level
if LOG_LEVEL == "DEBUG":
    # Development: Human-readable console format
    renderer = structlog.dev.ConsoleRenderer()
else:
    # Production: Structured JSON format
    renderer = structlog.processors.JSONRenderer()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        renderer,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)
```

Verwendung:

```python
logger.info("tag_scanned", tag_id="ABC123", reader_id="pn532_01")
logger.error("mqtt_connection_failed", broker="mqtt", port=1883)
```

### 7.2 Log-Levels & Output-Format

**LOG_LEVEL ist eine REQUIRED Environment-Variable ohne Default!**  
Wenn nicht gesetzt, schlägt der Service mit klarer Fehlermeldung fehl.

| Level    | Verwendung                | Format              | Use Case              |
|----------|---------------------------|---------------------|------------------------|
| DEBUG    | Entwickler-Details        | Console (lesbar)    | Development            |
| INFO     | Normale Operation         | JSON (strukturiert) | Production             |
| WARNING  | Wiederholbare Fehler      | JSON (strukturiert) | Production             |
| ERROR    | Aktion fehlgeschlagen     | JSON (strukturiert) | Production             |
| CRITICAL | Service-/System-Ausfall   | JSON (strukturiert) | Production             |

**Formatierung:**

- **DEBUG-Level:** Nutzt `ConsoleRenderer()` für schöne, lesbare Logs:
  ```text
  2026-02-15 19:43:19 [info     ] tag_scanned    tag_id=ABC123 reader_id=pn532_01
  ```

- **INFO+ Levels:** Nutzt `JSONRenderer()` für strukturiertes Logging:
  ```json
  {"event": "tag_scanned", "tag_id": "ABC123", "reader_id": "pn532_01", "level": "info", "timestamp": "2026-02-15T19:43:19.123456Z"}
  ```

**Wann welches Format?**

- **Development (LOG_LEVEL=DEBUG):** Console-Format – besser lesbar für Menschen
- **Production (LOG_LEVEL=INFO):** JSON-Format – optimal für Log-Aggregation (ELK, Grafana Loki, etc.)

**In `.env` setzen:**

```bash
# Development
LOG_LEVEL=DEBUG

# Production
LOG_LEVEL=INFO
```

### 7.3 Log-Output

Standard: `stdout` (durch Docker aufgenommen). Es werden **keine Log-Dateien** im Projekt oder unter `/data/logs/` geschrieben; alle Ausgaben landen in Docks Log-Verwaltung (z.B. `json-file`-Driver).

Im Admin-UI (System-Status) zeigt der **Log-Button** pro Service die Container-Logs an. Dafür fragt das Backend die Docker-API ab (`container.logs()`). Der Docker-Socket muss in den Backend-Container gemountet sein (z.B. `/var/run/docker.sock`) und der Container muss Zugriff darauf haben (z.B. `group_add` mit der Docker-Gruppe des Hosts).

```bash
docker compose logs -f                # Alle Services
docker compose logs -f rfid           # Nur RFID-Service
docker compose logs --tail=100 rfid   # Letzte 100 Zeilen
```

Optionale Log-Rotation über Docker-Logging-Driver:

```yaml
services:
  rfid:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 7.4 Health-Checks

Jeder Service exponiert `/health` (am Root, nicht unter `/api/v1`).

**Health-Status-Semantik:**

- **`healthy`** – Service läuft, alle relevanten Abhängigkeiten (z. B. MQTT, DB) sind verbunden.
- **`degraded`** – Service läuft, aber eine Abhängigkeit fehlt oder ist eingeschränkt (z. B. MQTT verbunden, VLC nicht initialisiert).
- **`unhealthy`** – Service oder kritische Abhängigkeit ist nicht nutzbar (z. B. DB oder MQTT down).

Services sollen einen dieser Werte zurückgeben; einheitliche Felder (z. B. `status`, `service`, `device_id`, `mqtt_connected`) sind in der shared-lib als `BaseHealthResponse` / `build_health_body` vorgegeben. Für Health-Handler nur öffentliche APIs nutzen (z. B. `mqtt_client.is_connected`), keine privaten Attribute (`_client`, `_running`).

Beispiel:

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "rfid",
        "device_id": config.env.minabox_device_id,
        "mqtt_connected": mqtt_client.is_connected,
    }
```

Docker Health-Check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1
```

---

## 8. Error Handling & Retry-Strategien

### 8.1 Exception-Hierarchie

Template (pro Service kopieren und anpassen):

```python
# service_name/exceptions.py

class MinaboxError(Exception):
    """Base Exception für alle Minabox-Fehler."""
    pass

class HardwareError(MinaboxError):
    """Hardware-Kommunikation fehlgeschlagen."""
    pass

class RFIDReadError(HardwareError):
    """RFID-Tag konnte nicht gelesen werden."""
    pass

class ServiceCommunicationError(MinaboxError):
    """Service nicht erreichbar."""
    pass

class MQTTConnectionError(ServiceCommunicationError):
    """MQTT-Broker nicht erreichbar."""
    pass

class DataError(MinaboxError):
    """Daten-bezogene Fehler."""
    pass

class TagNotFoundError(DataError):
    """RFID-Tag nicht in Datenbank."""
    pass
```

### 8.2 Retry-Strategien

**Library:** `tenacity`

Hardware-Retries (schnell):

```python
from tenacity import retry, stop_after_attempt, wait_fixed

@retry(stop=stop_after_attempt(3), wait=wait_fixed(0.5))
def read_rfid_tag() -> str:
    try:
        return rfid_reader.read()
    except Exception as e:
        logger.warning("rfid_read_failed", error=str(e))
        raise RFIDReadError(f"Read failed: {e}")
```

Netzwerk-Retries (exponentielles Backoff):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
)
def connect_mqtt():
    ...
```

### 8.3 Graceful Degradation

Services sollen bei Teil-Ausfällen weiterlaufen:

```python
try:
    await mqtt_client.publish("minabox/box1/rfid/tag-scanned", payload)
except MQTTConnectionError:
    logger.warning("mqtt_unavailable_caching")
    local_cache.append(payload)
```

### 8.4 Einheitliches REST Error-Format

```json
{
  "error": {
    "code": "TAG_NOT_FOUND",
    "message": "Tag ABC123 not found",
    "details": {"tag_id": "ABC123"}
  }
}
```

---

## 9. Testing

### 9.1 Philosophie

- Fokus auf Business-Logic und API-Tests  
- Hardware-Tests primär manuell auf dem Gerät  
- Logs als primäres Debugging-Tool  
- Kein harter Coverage-Zwang; lieber sinnvolle Tests als Zahlenoptimierung  

### 9.2 Test-Framework

- **pytest** für Unit- und Integrationstests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

### 9.3 Manuelle Test-Checklisten

Pro Service Checkliste in `docs/TESTING.md`:

```text
# RFID-Service - Manuelle Tests

## Hardware-Tests
- [ ] Tag auflegen → Tag-ID in Logs
- [ ] Tag entfernen → Event getriggert
- [ ] Unbekannter Tag → Error-Handling
- [ ] Reader disconnect → Service recovered

## Integration-Tests
- [ ] Tag-Scan → MQTT-Event published
- [ ] Audio-Service empfängt Event
- [ ] LED zeigt Status
```

---

## 10. Docker & Deployment

### 10.1 Dockerfile-Standards

- **Base-Image:** `python:3.13-slim`  
- **Multi-Stage-Build** empfohlen:

```dockerfile
# Stage 1: Build
FROM python:3.13-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY src/ ./src/
COPY config/ ./config/

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1

RUN useradd -m -u 1000 minabox && chown -R minabox:minabox /app
USER minabox

CMD ["python", "-m", "service_name.main"]
```

### 10.2 Zentrales `docker-compose.yml`

Das zentrale `docker-compose.yml` im Root orchestriert alle Services:

- `mqtt` – MQTT-Broker (Eclipse Mosquitto 2.1+)  
- `backend` – Backend-Service (API, DB, Orchestrierung)  
- `rfid` – RFID-Service  
- `audio` – Audio-Service  
- `button` – Button-Service  
- `led` – LED-Service  
- `webui` – WebUI-Service  
- Gemeinsames Netzwerk `minabox-network`  

**Starten aller Services:**

```bash
docker compose up -d
```

**Logs anzeigen:**

```bash
docker compose logs -f
```

**Services neustarten:**

```bash
docker compose restart backend audio
```

---

## 11. Graceful Shutdown

Wichtige Punkte (kurz):

- Services müssen `SIGTERM` und `SIGINT` abfangen  
- Shutdown-Reihenfolge:
  1. Neue Requests stoppen  
  2. Laufende Operationen (mit Timeout) beenden  
  3. MQTT sauber disconnecten  
  4. DB-Verbindungen schließen  
  5. Hardware freigeben  
- Jeder Schritt wird geloggt  
- Timeouts sind Pflicht, keine unendlichen Waits  

(Detaillierte Templates für Signal-Handling und Shutdown-Sequenz können pro Service übernommen werden.)

---

## 12. Datenbank & Persistence

- **Backend** als einziger direkter DB-Nutzer (z.B. SQLite + SQLAlchemy + Alembic)  
- Andere Services greifen nur via REST-API auf Daten zu  
- Typische Tabellen:
  - `tags` (Tag → Content-Mapping)
  - `content` (Audio-Inhalte, Metadaten)

---

## 13. Configuration Management

### 13.1 Zwei Ebenen

1. **Zentrale `.env`** im Root (gemeinsame Settings: MQTT-Broker, Ports, Logging, Device-ID)  
2. **Service-spezifische JSON-Configs** unter `config/*.json` pro Service  

### 13.2 Required Environment Variables

**Folgende Variablen sind REQUIRED und müssen in `.env` gesetzt sein:**

- `MQTT_BROKER`: MQTT broker hostname (z.B. `mqtt`)
- `MQTT_PORT`: MQTT broker port (z.B. `1883`)
- `MINABOX_DEVICE_ID`: Device ID for MQTT topics (z.B. `box1`)
- `LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)

**Keine Defaults vorhanden!** Services schlagen beim Start mit klarer Fehlermeldung fehl, wenn diese Variablen fehlen.

Beispiel `.env`:

```bash
# Device Configuration
MINABOX_DEVICE_ID=box1

# MQTT Broker
MQTT_BROKER=mqtt
MQTT_PORT=1883

# Logging (DEBUG for development, INFO for production)
LOG_LEVEL=INFO
```

### 13.3 Schema-basierte Config

Jeder Service definiert ein eigenes Schema (`config_schema.py`) und einen `ConfigManager`, der:

- `.env` + JSON lädt  
- Werte validiert (Pydantic)
- Globale Env-Vars (MQTT_BROKER, etc.) **ohne** Service-Prefix lädt
- Service-spezifische Env-Vars mit Prefix lädt (z.B. `MINABOX_BACKEND_*`)
- Hot-Reload ermöglicht (z.B. via MQTT-Config-Update)  

---

## 14. Best Practices

- **DRY (Don't Repeat Yourself)** – Gemeinsam genutzte Funktionalität (Config, Exceptions, MQTT-Basis) in `services/shared-lib` (minabox-shared)  
- **SOLID-Prinzipien** – insbesondere Single Responsibility & Dependency Inversion  
- **12-Factor-App** – für Konfiguration, Logs, Disposability, etc.  
- **Semantic Versioning** – für APIs und Service-Releases  
- **KISS (Keep It Simple)** – einfache Lösung > überkomplexe "perfekte" Lösung  
- **Fail-Fast** – Keine Silent-Defaults für kritische Konfiguration  

---

## 15. Referenzen

- Phoniebox (RPi-Jukebox-RFID) – Feature-Inspiration  
- TonUINO – Arduino-basierte Alternative  
- 12-Factor-App: https://12factor.net/  
- Python Best Practices: https://docs.python-guide.org/  
- MQTT Topics & Best Practices:  
  - https://www.hivemq.com/blog/mqtt-essentials-part-5-mqtt-topics-best-practices/  
  - https://www.emqx.com/en/blog/advanced-features-of-mqtt-topics  

---

**Letzte Aktualisierung:** 2026-02-15  
**Version:** 1.7.0
