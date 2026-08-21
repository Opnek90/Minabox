# Minabox - Entwicklungsanweisungen für KI-Assistenten

**Version:** 1.0.0  
**Letzte Änderung:** 2026-02-15

Dieses Dokument enthält spezifische Anweisungen für KI-Assistenten (wie Perplexity, Claude, ChatGPT) zur Code-Entwicklung im Minabox-Projekt. Es ergänzt die technischen Standards aus `Framework.md` und die Service-spezifischen Architekturen.

---

## Übersicht & Kontext

### Projektziel

Minabox ist eine Open-Source-Alternative zur Toniebox – eine Mikroservice-basierte Audioplayer-Lösung für Kinder mit RFID-Steuerung, basierend auf Raspberry Pi.

### Repository-Struktur

```text
Minabox/
├── docs/
│   ├── Framework.md                    # PFLICHTLEKTÜRE: Technische Standards
│   ├── DEPLOYMENT.md                   # Deployment-Strategien
│   ├── DEVELOPMENT_INSTRUCTIONS.md     # Dieses Dokument
│   └── services/
│       ├── backend/Architecture.md     # Backend-Service Architektur
│       ├── rfid/Architecture.md        # RFID-Service Architektur
│       ├── audio/Architecture.md       # Audio-Service Architektur
│       ├── button/Architecture.md      # Button-Service Architektur
│       ├── led/Architecture.md         # LED-Service Architektur
│       └── webui/Architecture.md       # WebUI-Service Architektur
├── services/                        # Service-Implementierungen
├── infrastructure/                  # Infrastruktur-Configs (Mosquitto etc.)
├── shared/                          # Gemeinsame Libraries
├── docker-compose.yml               # Zentrales Compose-File
├── pyproject.toml                   # Root-Config (Python 3.13, Tools)
└── .pre-commit-config.yaml          # Pre-commit Hooks (Ruff, Black, mypy)
```

---

## Grundlegende Arbeitsweise

### 1. Dokumentation ZUERST lesen

**KRITISCH:** Bevor du Code für einen Service schreibst, MUSST du folgende Dokumente lesen:

1. **`docs/Framework.md`** – Technische Standards, Code-Qualität, Projektstruktur, MQTT-Schema
2. **`docs/services/<service-name>/Architecture.md`** – Service-spezifische Architektur, API, Verantwortlichkeiten, Datei-/Ordnerstruktur mit Funktion pro Datei sowie Refactoring-Checkliste
3. **`pyproject.toml`** – Aktuelle Tool-Konfiguration (Python 3.13, Ruff, Black, mypy)

**Verwende GitHub-MCP-Tools, um diese Dateien zu laden!**

```python
# Beispiel-Workflow:
1. get_file_contents("docs/Framework.md")
2. get_file_contents("docs/services/backend/Architecture.md")
3. get_file_contents("pyproject.toml")
4. Dann erst Code schreiben!
```

### 2. Standards strikt einhalten

- **Python 3.13** ist Pflicht (nicht 3.11, nicht 3.12)
- **Type-Hints** für alle Funktionen und Methoden
- **Strukturiertes Logging** mit `structlog`
- **MQTT Topic-Schema:** `minabox/<device-id>/<domain>/<action>`
- **Namenskonventionen:**
  - Services: `lower-kebab-case` (z.B. `rfid-service`)
  - Python-Packages: `lower_snake_case` (z.B. `rfid_service`)
  - Funktionen: `snake_case`
  - Klassen: `PascalCase`
  - Konstanten: `UPPER_CASE`

### 3. Service-Struktur einhalten

Jeder Service folgt dieser Standard-Struktur (siehe `Framework.md` Kapitel 4):

```text
service-name/
├── src/
│   └── service_name/
│       ├── __init__.py
│       ├── main.py              # Einstiegspunkt
│       ├── api/                 # FastAPI Routes
│       ├── core/                # Business Logic
│       ├── models/              # Pydantic Models
│       ├── config_schema.py     # Config-Schema
│       ├── config_manager.py    # Config-Manager
│       └── config.py            # Config-Loading
├── tests/
├── config/
│   └── service.json
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Code-Entwicklung: Schritt-für-Schritt

### Phase 1: Vorbereitung

1. **Dokumentation laden:**
   ```bash
   # Verwende GitHub-MCP-Tools:
   - get_file_contents("docs/Framework.md")
   - get_file_contents("docs/services/<service>/Architecture.md")
   - get_file_contents("pyproject.toml")
   ```

2. **Service-Verzeichnis prüfen:**
   ```bash
   - get_file_contents("services/<service-name>")
   - Prüfe, welche Dateien bereits existieren
   ```

3. **Abhängigkeiten identifizieren:**
   - Welche MQTT-Topics subscribed der Service?
   - Welche Topics published er?
   - Welche REST-Endpoints werden benötigt?
   - Welche Services sind Abhängigkeiten?

### Phase 2: Dateien erstellen

**Reihenfolge ist wichtig!**

1. **`requirements.txt`** – Dependencies
2. **`pyproject.toml`** – Tool-Config (aus Root-Template kopieren)
3. **`src/<service>/__init__.py`** – Package-Init
4. **`src/<service>/models/schemas.py`** – Pydantic-Models
5. **`src/<service>/config_schema.py`** – Config-Schema
6. **`src/<service>/config_manager.py`** – Config-Manager
7. **`src/<service>/config.py`** – Config-Loading
8. **`src/<service>/core/mqtt_client.py`** – MQTT-Client
9. **`src/<service>/core/<logic>.py`** – Business Logic
10. **`src/<service>/api/routes.py`** – REST-Endpoints (falls nötig)
11. **`src/<service>/main.py`** – Einstiegspunkt
12. **`Dockerfile`** – Multi-Stage-Build (Python 3.13-slim)
13. **`config/service.json`** – Default-Config
14. **`README.md`** – Service-Dokumentation

### Phase 3: Code-Qualität sicherstellen

**Prüfe JEDEN erstellten Code gegen:**

- ✅ Python 3.13 Syntax
- ✅ Type-Hints für alle Funktionen
- ✅ Structlog statt print()
- ✅ Pydantic für alle Configs und Models
- ✅ FastAPI für REST-APIs
- ✅ aiomqtt oder paho-mqtt für MQTT
- ✅ Graceful Shutdown (SIGTERM/SIGINT)
- ✅ Health-Check-Endpoint (`/health`)
- ✅ Exception-Hierarchie (siehe Framework.md Kapitel 8)
- ✅ Retry-Strategien mit `tenacity`

---

## MQTT-Integration

### Topic-Schema einhalten

**IMMER** das globale Schema verwenden:

```text
minabox/<device-id>/<domain>/<action>
```

**Beispiele:**

```python
# RICHTIG:
minabox/box1/rfid/tag-scanned
minabox/box1/audio/play
minabox/box1/button/volume-up

# FALSCH:
rfid/tag-scanned          # Fehlt device-id
minabox/rfid-scan         # Falsches Format
Minabox/Box1/RFID/Scan    # Groß-/Kleinschreibung
```

### QoS und Retained Messages

- **QoS 1** für Events und Commands (Standard)
- **QoS 0** nur für häufige Telemetrie
- **Retained:** Nur für Status-Topics (z.B. `audio/status`, `system/online`)
- **Nicht Retained:** Events (z.B. `tag-scanned`, `button/pressed`)

### Message-Format

Alle MQTT-Messages als JSON mit Timestamp:

```python
import json
from datetime import datetime, timezone

payload = {
    "event": "tag_scanned",
    "data": {
        "tag_id": "ABC123",
        "reader_id": "pn532_01"
    },
    "timestamp": datetime.now(timezone.utc).isoformat()
}

mqtt_client.publish(
    "minabox/box1/rfid/tag-scanned",
    json.dumps(payload),
    qos=1
)
```

---

## REST-API-Standards

### Base-Path

Alle REST-APIs verwenden: `/api/v1/`

### Health-Check (Pflicht)

Jeder Service MUSS einen Health-Check-Endpoint haben:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "service-name",
        "version": "0.1.0",
        "uptime_seconds": get_uptime(),
        "mqtt_connected": mqtt_client.is_connected()
    }
```

### Error-Format

Einheitliches Error-Format:

```python
from fastapi import HTTPException

raise HTTPException(
    status_code=404,
    detail={
        "error": {
            "code": "TAG_NOT_FOUND",
            "message": "Tag ABC123 not found in database",
            "details": {"tag_id": "ABC123"}
        }
    }
)
```

---

## Dockerfile-Standards

**Multi-Stage-Build mit Python 3.13:**

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

**Wichtig:**
- Base-Image: `python:3.13-slim` (nicht 3.11, nicht 3.12!)
- Multi-Stage für kleinere Images
- Non-root User (`minabox`)
- Health-Check integriert

---

## Config-Management

### Zwei-Ebenen-Ansatz

1. **Globale `.env`** (Root) – MQTT-Broker, Ports, Device-ID, Log-Level
2. **Service-JSON** (`config/service.json`) – Service-spezifische Settings

### Config-Schema mit Pydantic

```python
# config_schema.py
from pydantic import BaseModel, Field

class ServiceConfig(BaseModel):
    mqtt_broker: str = Field(default="mosquitto")
    mqtt_port: int = Field(default=1883)
    device_id: str = Field(default="box1")
    log_level: str = Field(default="INFO")
    # Service-spezifische Felder...

    class Config:
        json_schema_extra = {
            "example": {
                "mqtt_broker": "mosquitto",
                "mqtt_port": 1883,
                "device_id": "box1",
                "log_level": "INFO"
            }
        }
```

### Hot-Reload via MQTT

Services müssen Config-Updates via MQTT unterstützen:

- Subscribe: `minabox/<device-id>/<service>/config/update`
- Publish: `minabox/<device-id>/<service>/config/response`

---

## Logging-Standards

### Structlog verwenden

```python
import structlog

logger = structlog.get_logger("service_name")

# Richtig:
logger.info(
    "tag_scanned",
    tag_id="ABC123",
    reader_id="pn532_01",
    timestamp=datetime.now(timezone.utc).isoformat()
)

# Falsch:
print("Tag scanned: ABC123")  # Niemals print() verwenden!
```

### Log-Levels

- **DEBUG:** Entwickler-Details (GPIO-Init, Verbindungsaufbau)
- **INFO:** Normale Operations (Tag gescannt, Playback gestartet)
- **WARNING:** Wiederholbare Fehler (Timeout, Retry)
- **ERROR:** Fehler (Tag not found, File missing)
- **CRITICAL:** System-Ausfall (MQTT unreachable, Hardware-Fehler)

---

## Graceful Shutdown

**Jeder Service MUSS Signals abfangen:**

```python
import signal
import asyncio

class Service:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

    def handle_shutdown(self, signum, frame):
        logger.info("shutdown_initiated", signal=signum)
        self.running = False

    async def shutdown(self):
        logger.info("shutdown_starting")
        
        # 1. Stop accepting new requests
        logger.info("shutdown_step_1_stop_requests")
        
        # 2. Wait for ongoing operations (with timeout)
        try:
            await asyncio.wait_for(
                self.finish_operations(),
                timeout=10.0
            )
            logger.info("shutdown_step_2_operations_finished")
        except asyncio.TimeoutError:
            logger.warning("shutdown_step_2_timeout")
        
        # 3. Disconnect MQTT
        await self.mqtt_client.disconnect()
        logger.info("shutdown_step_3_mqtt_disconnected")
        
        # 4. Close DB connections (if any)
        # ...
        
        # 5. Release hardware
        # ...
        
        logger.info("shutdown_complete")
```

---

## Testing-Strategie

### Fokus auf Business-Logic

- Unit-Tests für Core-Logic
- Integration-Tests für API-Endpoints
- Hardware-Tests manuell auf dem Gerät

### pytest verwenden

```python
# tests/unit/test_logic.py
import pytest
from service_name.core.logic import process_tag

def test_process_tag_valid():
    result = process_tag("ABC123")
    assert result.tag_id == "ABC123"
    assert result.valid is True

def test_process_tag_invalid():
    with pytest.raises(ValueError):
        process_tag("")
```

---

## Häufige Fehler vermeiden

### ❌ DON'T

```python
# Falsche Python-Version
FROM python:3.11-slim  # ❌ Falsch!

# Print statt Logging
print("Tag scanned")  # ❌ Falsch!

# Keine Type-Hints
def process_tag(tag_id):  # ❌ Falsch!
    return tag_id

# Falsches MQTT-Topic-Schema
mqtt.publish("rfid/scan", data)  # ❌ Falsch!

# Hardcoded Werte
MQTT_BROKER = "localhost"  # ❌ Falsch!

# Keine Error-Handling
data = json.loads(payload)  # ❌ Falsch!
```

### ✅ DO

```python
# Richtige Python-Version
FROM python:3.13-slim  # ✅ Richtig!

# Structlog
logger.info("tag_scanned", tag_id="ABC123")  # ✅ Richtig!

# Type-Hints
def process_tag(tag_id: str) -> TagResult:  # ✅ Richtig!
    return TagResult(tag_id=tag_id)

# Korrektes MQTT-Topic-Schema
mqtt.publish(f"minabox/{device_id}/rfid/tag-scanned", data)  # ✅ Richtig!

# Config aus Environment
mqtt_broker = config.mqtt_broker  # ✅ Richtig!

# Error-Handling
try:
    data = json.loads(payload)
except json.JSONDecodeError as e:
    logger.error("json_parse_error", error=str(e))
    raise
```

---

## Workflow-Checkliste

Bevor du Code committed:

- [ ] `docs/Framework.md` gelesen?
- [ ] `docs/services/<service>/Architecture.md` gelesen?
- [ ] Python 3.13 verwendet?
- [ ] Type-Hints überall vorhanden?
- [ ] Structlog statt print()?
- [ ] MQTT-Topic-Schema korrekt?
- [ ] Health-Check-Endpoint vorhanden?
- [ ] Graceful Shutdown implementiert?
- [ ] Config via Pydantic validiert?
- [ ] Dockerfile mit python:3.13-slim?
- [ ] requirements.txt vollständig?
- [ ] README.md geschrieben?
- [ ] Exception-Handling korrekt?
- [ ] Retry-Strategien wo nötig?

### Veröffentlichen

Jeder Dienst trägt seine eigene Versionsnummer
([Versionierung.md](Versionierung.md)). Deshalb gehört zu jedem Commit, der
einen Dienst verändert:

- [ ] `services/<dienst>-service/VERSION` um eine Patch-Stelle angehoben
      (`0.1.0` → `0.1.1`) — für **jeden** betroffenen Dienst. Änderungen an
      `shared-lib` oder am MQTT-Vertrag betreffen alle abhängigen Dienste.
- [ ] Eintrag in `CHANGELOG.md` **und** `CHANGELOG.en.md`, ein Satz aus
      Nutzersicht.
- [ ] `python3 scripts/build_manifest.py` ausgeführt und
      `release-manifest.json` mitcommittet.

Die CI prüft das: sie baut nur geänderte Dienste, weigert sich, einen bereits
vergebenen Versions-Tag zu überschreiben, und lässt gar nicht erst bauen, wenn
die aktuelle Version eines Dienstes nicht im Changelog steht.

---

## Hilfreiche GitHub-MCP-Befehle

```python
# Dokumentation laden
get_file_contents("docs/Framework.md")
get_file_contents("docs/services/backend/Architecture.md")

# Service-Struktur prüfen
get_file_contents("services/backend-service")

# Existierende Dateien prüfen
get_file_contents("services/backend-service/src")

# Neue Datei erstellen
create_or_update_file(
    path="services/backend-service/src/backend_service/main.py",
    content="...",
    message="Add main.py for backend service"
)

# Mehrere Dateien gleichzeitig pushen
push_files(
    branch="main",
    files=[
        {"path": "file1.py", "content": "..."},
        {"path": "file2.py", "content": "..."}
    ],
    message="Add multiple files"
)
```

---

## Support & Referenzen

### Interne Dokumentation

- **Framework.md** – Technische Standards (PFLICHT!)
- **DEPLOYMENT.md** – Deployment-Strategien
- **docs/services/*/Architecture.md** – Service-spezifische Architekturen

### Externe Referenzen

- Python 3.13 Docs: https://docs.python.org/3.13/
- FastAPI: https://fastapi.tiangolo.com/
- Pydantic: https://docs.pydantic.dev/
- Structlog: https://www.structlog.org/
- MQTT Best Practices: https://www.hivemq.com/blog/mqtt-essentials-part-5-mqtt-topics-best-practices/

---

**Letzte Aktualisierung:** 2026-02-15  
**Version:** 1.0.0

**WICHTIG:** Dieses Dokument ist als Richtlinie für KI-Assistenten gedacht. Bei Widersprüchen hat `Framework.md` Vorrang!
