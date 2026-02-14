# Minabox - Framework Guidelines

**Version:** 1.3  
**Letzte Änderung:** 2026-02-14

Dieses Dokument definiert die technischen Standards und Best Practices für das gesamte Minabox-Projekt. Alle Services müssen diesen Richtlinien folgen, um Konsistenz, Wartbarkeit und Qualität sicherzustellen.

---

## 1. Technologie-Stack

### Core

- **Sprache:** Python 3.11+  
- **Package Management:** Poetry oder pip-tools  
- **Container:** Docker & Docker Compose  
- **Orchestrierung:** zentrales `docker-compose.yml` im Root-Repo  

### Development

- **IDE:** Frei wählbar (VSCode empfohlen)  
- **Git:** Konventionelle Commit-Messages  
- **Branching:** Feature-Branches, `main` = stabiler Stand  

---

## 2. Projekt-Struktur (Root-Repository)

Das Root-Repository ist wie folgt strukturiert:

```text
docs/
  Framework.md           # Dieses Dokument
  Architecture.md        # Gesamtarchitektur & Service-Kommunikation
  services/              # Fachliche Doku & Checklisten pro Bereich
    rfid/RFID.md
    audio/Audio.md
    webui/WebUI.md
    api/API.md
    database/Database.md
    hardware/Hardware.md

services/                # Technische Services (Implementierungen)
  rfid-service/
  audio-service/
  backend-service/
  webui-service/
  ...                    # weitere Services nach Bedarf

shared/                  # Gemeinsame Libraries/Module (DRY)
infrastructure/          # Infrastruktur (docker-compose, MQTT-Broker, Monitoring, CI/CD)
Jeder Service-Ordner unter services/ verwendet die Standardstruktur aus Kapitel 3. Projekt-Struktur pro Service.

3. Code-Qualität Standards
3.1 Tools
Linting & Formatting:

Ruff – Linting, Import-Sortierung, Code-Modernisierung

Black – Code-Formatting (88 Zeichen, einheitlicher Stil)

mypy – Type-Checking (moderate Strenge)

Konfiguration in pyproject.toml:

text
[tool.black]
line-length = 88
target-version = ['py311']

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]

[tool.mypy]
python_version = "3.11"
warn_unused_configs = true
disallow_untyped_defs = true
warn_return_any = true
3.2 Pre-commit Hooks
.pre-commit-config.yaml:

text
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/psf/black
    rev: 24.10.0
    hooks:
      - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
        additional_dependencies:
          - types-requests
          - types-PyYAML
          - pydantic
Setup:

bash
pip install pre-commit
pre-commit install
3.3 Type-Hints
Alle Funktionen müssen Type-Hints haben:

python
from typing import Optional

def process_tag(tag_id: str, timeout: int = 5) -> Optional[str]:
    """Process RFID tag."""
    ...
4. Projekt-Struktur pro Service
4.1 Standard-Struktur
text
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
├── docs/
│   └── README.md
├── config/
│   └── service.json           # Service-spezifische Config
├── Dockerfile
├── docker-compose.yml         # Optional: lokales Compose für Einzelservice
├── pyproject.toml
├── requirements.txt           # Für Docker-Build
└── README.md
4.2 Namenskonventionen
Services (Ordner): lower-kebab-case

z.B. rfid-service, audio-service

Python-Packages: lower_snake_case

z.B. rfid_service, audio_service

Funktionen: snake_case

z.B. read_tag(), play_audio()

Klassen: PascalCase

z.B. RFIDReader, AudioPlayer

Konstanten: UPPER_CASE

z.B. MAX_VOLUME, DEFAULT_TIMEOUT

5. Service-Kommunikation
5.1 Architektur: Hybrid MQTT + REST
MQTT (asynchron, Event-Driven):

Hardware-Events (Buttons, RFID-Scan)

Status-Änderungen (Playback, Volume)

System-Events (Service-Start, Fehler, Health-Status)

REST (synchron):

Status-Abfragen: GET /api/v1/audio/status

Commands: POST /api/v1/audio/play

Konfiguration & Admin: z.B. GET /api/v1/rfid/tags

5.2 MQTT Broker
Technologie: Eclipse Mosquitto

Port: 1883 (Standard)

Broker läuft als Container unter infrastructure/ und wird über das zentrale docker-compose.yml gestartet.

5.3 MQTT Topic-Schema
Globales Schema:

text
minabox/<device-id>/<domain>/<action>
<device-id>: Eindeutige ID der Box (z.B. box1, livingroom, kidsroom)

<domain>: Fachbereich, z.B. rfid, button, audio, system

<action>: Konkretes Event oder Kommando, z.B. tag-scanned, play, status

Beispiele:

text
# RFID
minabox/box1/rfid/tag-scanned
minabox/box1/rfid/tag-removed

# Buttons
minabox/box1/button/play
minabox/box1/button/next
minabox/box1/button/prev
minabox/box1/button/volume

# Audio
minabox/box1/audio/play
minabox/box1/audio/pause
minabox/box1/audio/stop
minabox/box1/audio/status

# System
minabox/box1/system/service-started
minabox/box1/system/service-error
minabox/box1/system/online
Namenskonvention:

Nur Kleinbuchstaben, Ziffern, Bindestrich oder Unterstrich

Keine Leerzeichen, keine doppelten /

<device-id> ist Pflicht, damit mehrere Boxen parallel betrieben werden können [web:20][web:32].

5.4 MQTT QoS, Wildcards & Retain
QoS:

Standard: QoS 1 (at least once) für Steuer- und Event-Topics (RFID, Button, Audio-Kommandos) [web:16].

Optional: QoS 0 für häufige, nicht-kritische Telemetrie (z.B. Fortschritt/Debug) [web:16].

Wildcards:

+ für genau eine Ebene, z.B.:

text
minabox/+/rfid/tag-scanned        # Alle Geräte
# nur in Debug-/Analyse-Tools, nicht im produktiven Service-Code, z.B.:

text
minabox/box1/#                    # Debug-Client für eine Box
Wildcards nur als komplette Topic-Ebene verwenden, nicht innerhalb eines Wortes [web:17][web:27][web:40].

Retained Messages:

Retain AN für Zustände:

text
minabox/<device-id>/audio/status
minabox/<device-id>/system/online
Retain AUS für einmalige Events:

text
minabox/<device-id>/rfid/tag-scanned
minabox/<device-id>/button/pressed
Ziel: Neue Subscriber bekommen den aktuellen Status, aber keine alten Events.

5.5 Backend als MQTT–WebSocket-Bridge
Backend-Service:

Subscribed auf relevante MQTT-Topics (RFID, Buttons, Audio-Status, System)

Aggregiert Events und Status

Schiebt Events/Status via WebSocket an die WebUI

Exponiert REST-API für Queries/Commands

WebUI:

Verbindung zum Backend via WebSocket (Real-Time Updates)

REST-Calls für Commands (Play, Pause, Config)

Kein direkter MQTT-Zugriff (Security & Vereinfachung)

Warum kein direktes MQTT im WebUI:

Einfachere Frontend-Implementierung (nur HTTP/WebSocket)

Backend kann filtern, aggregieren, validieren

Services bleiben im internen Netz, nicht direkt exponiert

5.6 MQTT Message Format
JSON mit Timestamps:

json
{
  "event": "tag_scanned",
  "data": {
    "tag_id": "ABC123",
    "reader_id": "pn532_01"
  },
  "timestamp": "2026-02-14T13:30:00Z"
}
6. Logging & Monitoring
6.1 Logging-Framework
Library: structlog (strukturiertes JSON-Logging)

Beispiel:

python
import structlog

logger = structlog.get_logger("rfid_service")
logger.info("tag_scanned", tag_id="ABC123", reader_id="pn532_01")
6.2 Log-Levels
Level	Verwendung	Beispiel
DEBUG	Entwickler-Details	"GPIO pin initialized"
INFO	Normale Operation	"Tag scanned", "Playback started"
WARNING	Wiederholbare Fehler	"RFID timeout, retrying"
ERROR	Aktion fehlgeschlagen	"Tag not found", "File missing"
CRITICAL	Service-/System-Ausfall	"MQTT unreachable", "HW failure"
Production: INFO

Development: DEBUG

6.3 Log-Output
Standard: stdout (durch Docker aufgenommen)

bash
docker compose logs -f                # Alle Services
docker compose logs -f rfid           # Nur RFID-Service
docker compose logs --tail=100 rfid   # Letzte 100 Zeilen
Optionale Log-Rotation über Docker-Logging-Driver:

text
services:
  rfid:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
6.4 Health-Checks
Jeder Service exponiert /health:

python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "rfid",
        "uptime": get_uptime(),
        "mqtt_connected": mqtt_client.is_connected()
    }
Docker Health-Check:

text
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1
7. Error Handling & Retry-Strategien
7.1 Exception-Hierarchie
Template (pro Service kopieren und anpassen):

python
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
7.2 Retry-Strategien
Library: tenacity

Hardware-Retries (schnell):

python
from tenacity import retry, stop_after_attempt, wait_fixed

@retry(stop=stop_after_attempt(3), wait=wait_fixed(0.5))
def read_rfid_tag() -> str:
    try:
        return rfid_reader.read()
    except Exception as e:
        logger.warning("rfid_read_failed", error=str(e))
        raise RFIDReadError(f"Read failed: {e}")
Netzwerk-Retries (exponentielles Backoff):

python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
)
def connect_mqtt():
    ...
7.3 Graceful Degradation
Services sollen bei Teil-Ausfällen weiterlaufen:

python
try:
    await mqtt_client.publish("minabox/box1/rfid/tag-scanned", payload)
except MQTTConnectionError:
    logger.warning("mqtt_unavailable_caching")
    local_cache.append(payload)
7.4 Einheitliches REST Error-Format
json
{
  "error": {
    "code": "TAG_NOT_FOUND",
    "message": "Tag ABC123 not found",
    "details": {"tag_id": "ABC123"}
  }
}
8. Testing
8.1 Philosophie
Fokus auf Business-Logic und API-Tests

Hardware-Tests primär manuell auf dem Gerät

Logs als primäres Debugging-Tool

Kein harter Coverage-Zwang; lieber sinnvolle Tests als Zahlenoptimierung

8.2 Test-Framework
pytest für Unit- und Integrationstests

bash
pip install pytest pytest-asyncio
pytest tests/
8.3 Manuelle Test-Checklisten
Pro Service Checkliste in docs/TESTING.md:

text
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
9. Docker & Deployment
9.1 Dockerfile-Standards
Base-Image: python:3.11-slim

Multi-Stage-Build empfohlen:

text
# Stage 1: Build
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

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
9.2 Zentrales docker-compose.yml
(verkürzt, siehe detaillierten Stand in deinem bisherigen Dokument):

mosquitto

backend

rfid

audio

hardware

Gemeinsames Netzwerk minabox-network

10. Graceful Shutdown
Wichtige Punkte (kurz):

Services müssen SIGTERM und SIGINT abfangen

Shutdown-Reihenfolge:

Neue Requests stoppen

Laufende Operationen (mit Timeout) beenden

MQTT sauber disconnecten

DB-Verbindungen schließen

Hardware freigeben

Jeder Schritt wird geloggt

Timeouts sind Pflicht, keine unendlichen Waits

(Detaillierter Code siehe bisherige Templates in deinem Dokument.)

11. Datenbank & Persistence
Backend als einziger direkter DB-Nutzer (z.B. SQLite + SQLAlchemy + Alembic)

Andere Services greifen nur via REST-API auf Daten zu

Typische Tabellen:

tags (Tag → Content-Mapping)

content (Audio-Inhalte, Metadaten)

12. Configuration Management
12.1 Zwei Ebenen
Zentrale .env im Root (gemeinsame Settings: MQTT-Broker, Ports, Logging)

Service-spezifische JSON-Configs unter config/*.json pro Service

12.2 Schema-basierte Config
Jeder Service definiert ein eigenes Schema (config_schema.py) und einen ConfigManager, der:

.env + JSON lädt

Werte validiert

Hot-Reload ermöglicht (z.B. via MQTT-Config-Update)

13. Best Practices
DRY (Don't Repeat Yourself) – Gemeinsam genutzte Funktionalität nach shared/

SOLID-Prinzipien – insbesondere Single Responsibility & Dependency Inversion

12-Factor-App – für Konfiguration, Logs, Disposability, etc.

Semantic Versioning – für APIs und Service-Releases

KISS (Keep It Simple) – einfache Lösung > überkomplexe „perfekte“ Lösung

14. Referenzen
Phoniebox (RPi-Jukebox-RFID) – Feature-Inspiration

TonUINO – Arduino-basierte Alternative

12-Factor-App: https://12factor.net/

Python Best Practices: https://docs.python-guide.org/

MQTT Topics & Best Practices:

https://www.hivemq.com/blog/mqtt-essentials-part-5-mqtt-topics-best-practices/ [web:17]

https://www.emqx.com/en/blog/advanced-features-of-mqtt-topics [web:18]

Letzte Aktualisierung: 2026-02-14
Version: 1.3
