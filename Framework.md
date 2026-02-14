# Minabox - Framework Guidelines

**Version:** 1.1  
**Letzte Änderung:** 2026-02-14

Dieses Dokument definiert die technischen Standards und Best Practices für das gesamte Minabox-Projekt. Alle Services müssen diesen Richtlinien folgen, um Konsistenz, Wartbarkeit und Qualität sicherzustellen.

---

## 1. Technologie-Stack

### Core
- **Python:** 3.11+
- **Package Manager:** Poetry oder pip-tools
- **Container:** Docker & Docker Compose
- **Orchestrierung:** docker-compose.yml (zentral)

### Development
- **IDE:** Beliebig (VSCode empfohlen)
- **Git:** Konventionelle Commit-Messages
- **Branching:** Feature-Branches, main = stable

---

## 2. Code-Qualität Standards

### Tools

**Linting & Formatting:**
- **Ruff** - Linting, Import-Sortierung, Code-Modernisierung (ersetzt Flake8 + isort)
- **Black** - Code-Formatting (88 Zeichen, einheitlicher Stil)
- **mypy** - Type-Checking (moderate Strenge)

**Konfiguration in `pyproject.toml`:**

```toml
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
```

### Pre-commit Hooks

`.pre-commit-config.yaml`:

```text
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/psf/black
    rev: 24.2.0
    hooks:
      - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
```

Setup:

```bash
pip install pre-commit
pre-commit install
```

### Type-Hints

Alle Funktionen müssen Type-Hints haben:

```python
def process_tag(tag_id: str, timeout: int = 5) -> Optional[str]:
    """Process RFID tag."""
    pass
```

---

## 3. Projekt-Struktur pro Service

### Standard-Struktur

```text
service-name/                   # z.B. rfid/, audio/, hardware/
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
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt           # Für Docker
└── README.md
```

### Namenskonventionen

- **Services:** Lowercase mit Bindestrichen: `rfid-service`, `audio-service`
- **Python-Packages:** Lowercase mit Unterstrichen: `rfid_service`, `audio_service`
- **Funktionen:** snake_case: `read_tag()`, `play_audio()`
- **Klassen:** PascalCase: `RFIDReader`, `AudioPlayer`
- **Konstanten:** UPPER_CASE: `MAX_VOLUME`, `DEFAULT_TIMEOUT`

---

## 4. Service-Kommunikation

### Architektur: Hybrid MQTT + REST

**MQTT für Events (asynchron, Event-Driven):**
- Hardware-Events (Button, RFID-Scan)
- Status-Changes (Playback, Volume)
- System-Events (Service-Start, Fehler)

**REST für Queries & Commands (synchron):**
- Status-Abfragen: `GET /api/v1/audio/status`
- Direkte Commands: `POST /api/v1/audio/play`
- Konfiguration: `GET /api/v1/rfid/tags`

### MQTT Broker

- **Technologie:** Eclipse Mosquitto
- **Port:** 1883
- **QoS:** QoS 1 (at least once) für wichtige Events

### MQTT Topic-Schema

Namenskonvention: `minabox/<service>/<entity>/<action>`

```text
# RFID-Service
minabox/rfid/tag/scanned
minabox/rfid/tag/removed
minabox/rfid/reader/status

# Audio-Service
minabox/audio/playback/started
minabox/audio/playback/stopped
minabox/audio/playback/paused
minabox/audio/playback/progress
minabox/audio/volume/changed

# Hardware-Service
minabox/hardware/button/play
minabox/hardware/button/next
minabox/hardware/button/prev
minabox/hardware/rotary/volume

# System
minabox/system/service/started
minabox/system/service/error
```

### Backend als MQTT-WebSocket Bridge

**Backend-Service:**
- Subscribed zu allen relevanten MQTT-Topics
- Aggregiert Events und Status
- Pushed über WebSocket an WebUI
- Exponiert REST API für Queries/Commands

**WebUI:**
- Verbindet zu Backend via WebSocket (permanente Verbindung)
- Empfängt Real-Time Updates ohne Polling
- Sendet Commands via REST API

**Warum kein direktes MQTT im WebUI:**
- Einfacher für Frontend (nur HTTP/WebSocket)
- Backend kann filtern/aggregieren
- Bessere Security
- Services nicht direkt exponiert

### MQTT Message Format

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

## 5. Logging & Monitoring

### Logging-Framework

**Library:** structlog (strukturiertes JSON-Logging)

Setup:

```python
import structlog

logger = structlog.get_logger("service_name")
logger.info("event_name", key="value", tag_id="ABC123")
```

### Log-Levels

| Level    | Verwendung                | Beispiel                                       |
|----------|---------------------------|------------------------------------------------|
| DEBUG    | Entwickler-Details        | "GPIO Pin initialized", "MQTT received"        |
| INFO     | Normale Operations        | "Tag scanned", "Playback started"              |
| WARNING  | Wiederholbare Fehler      | "RFID timeout, retrying"                       |
| ERROR    | Fehler verhindert Aktion  | "Tag not found", "File missing"                |
| CRITICAL | Service-Ausfall           | "MQTT unreachable", "Hardware failure"         |

- **Production:** INFO
- **Development:** DEBUG

### Log-Output

stdout (captured by Docker):

```bash
docker compose logs -f                # Alle Services
docker compose logs -f rfid          # Nur RFID
docker compose logs --tail=100 rfid  # Letzte 100 Zeilen
```

Später (optional): Docker Logging Driver mit Rotation

```text
# docker-compose.yml
services:
  rfid:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Health-Checks

Jeder Service exponiert `/health` Endpoint:

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "rfid",
        "uptime": get_uptime(),
        "mqtt_connected": mqtt_client.is_connected()
    }
```

Docker Health-Check:

```text
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1
```

---

## 6. Error Handling & Retry-Strategien

### Exception-Hierarchie

Template (pro Service kopieren und anpassen):

```python
# service_name/exceptions.py

class MinaboxError(Exception):
    """Base Exception für alle Minabox-Fehler"""
    pass

class HardwareError(MinaboxError):
    """Hardware-Kommunikation fehlgeschlagen"""
    pass

class RFIDReadError(HardwareError):
    """RFID-Tag konnte nicht gelesen werden"""
    pass

class ServiceCommunicationError(MinaboxError):
    """Service nicht erreichbar"""
    pass

class MQTTConnectionError(ServiceCommunicationError):
    """MQTT-Broker nicht erreichbar"""
    pass

class DataError(MinaboxError):
    """Daten-bezogene Fehler"""
    pass

class TagNotFoundError(DataError):
    """RFID-Tag nicht in Datenbank"""
    pass
```

### Retry-Strategien

**Library:** tenacity

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
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60)
)
def connect_mqtt():
    pass
```

### Graceful Degradation

Services funktionieren auch bei Teil-Ausfällen weiter:

```python
# MQTT down → Cache Events local
try:
    await mqtt.publish("event", payload)
except MQTTConnectionError:
    logger.warning("mqtt_unavailable_caching")
    local_cache.append(payload)
    # Service läuft weiter
```

### REST Error-Format

Einheitlich für alle APIs:

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

## 7. Testing

### Testing-Philosophie

Pragmatischer Ansatz:
- Automatisierte Tests nur wo sinnvoll (Business-Logic, APIs)
- Hardware-Tests manuell auf dem Pi
- Logs sind primäres Debugging-Tool
- Kein Coverage-Zwang

### Test-Framework (optional)

**pytest** für Business-Logic und API-Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

### Manuelle Test-Checklisten

Pro Service eine Checkliste in `docs/TESTING.md`:

```text
# RFID-Service - Manuelle Tests

## Hardware-Tests
- [ ] Tag auflegen → Tag-ID in Logs
- [ ] Tag entfernen → Event getriggert
- [ ] Unbekannter Tag → Error-Handling
- [ ] Reader disconnect → Service recovered

## Integration-Tests
- [ ] Tag-Scan → MQTT Event published
- [ ] Audio-Service empfängt Event
- [ ] LED zeigt Status
```

---

## 8. Docker & Deployment

### Dockerfile-Standards

- **Base-Image:** python:3.11-slim
- **Multi-Stage-Build Template:**

```text
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
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

RUN useradd -m -u 1000 minabox && chown -R minabox:minabox /app
USER minabox

CMD ["python", "-m", "service_name.main"]
```

### docker-compose.yml (Root)

Zentrale Orchestrierung:

```text
version: '3.8'

services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: minabox-mosquitto
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - mosquitto-data:/mosquitto/data
    restart: unless-stopped
    networks:
      - minabox-network

  backend:
    build: ./backend
    container_name: minabox-backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    depends_on:
      - mosquitto
    restart: unless-stopped
    networks:
      - minabox-network

  rfid:
    build: ./rfid
    container_name: minabox-rfid
    env_file:
      - .env
    volumes:
      - ./config/rfid.json:/app/config/rfid.json
    devices:
      - /dev/i2c-1:/dev/i2c-1
    privileged: true
    depends_on:
      - mosquitto
    restart: unless-stopped
    networks:
      - minabox-network

  audio:
    build: ./audio
    container_name: minabox-audio
    env_file:
      - .env
    volumes:
      - ./config/audio.json:/app/config/audio.json
      - ./audio/content:/app/content
    devices:
      - /dev/snd:/dev/snd
    depends_on:
      - mosquitto
    restart: unless-stopped
    networks:
      - minabox-network

  hardware:
    build: ./hardware
    container_name: minabox-hardware
    env_file:
      - .env
    volumes:
      - ./config/hardware.json:/app/config/hardware.json
    privileged: true
    depends_on:
      - mosquitto
    restart: unless-stopped
    networks:
      - minabox-network

volumes:
  mosquitto-data:

networks:
  minabox-network:
    driver: bridge
```

### Systemd Auto-Start

`/etc/systemd/system/minabox.service`:

```text
[Unit]
Description=Minabox Services
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/minabox
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Aktivieren:

```bash
sudo systemctl enable minabox
sudo systemctl start minabox
```

---

## 9. Graceful Shutdown

Alle Services müssen bei Shutdown (SIGTERM, SIGINT) sauber herunterfahren und Ressourcen freigeben. Dies ist kritisch für Datenintegrität und verhindert Ressourcen-Leaks.

### Signal-Handling

Jeder Service muss SIGTERM und SIGINT abfangen:

```python
# service_name/main.py
import signal
import asyncio
from typing import Any

class ServiceShutdown(Exception):
    """Raised to trigger graceful shutdown"""
    pass

shutdown_event = asyncio.Event()

def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals"""
    logger.info("shutdown_signal_received", signal=signal.Signals(signum).name)
    shutdown_event.set()

# Register handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

### Shutdown-Sequence

Standardisierte Shutdown-Reihenfolge für alle Services:

```python
async def shutdown_sequence(
    mqtt_client: MQTTClient,
    fastapi_app: FastAPI,
    hardware_resources: Optional[Any] = None
) -> None:
    """
    Graceful shutdown sequence.
    
    Order:
    1. Stop accepting new requests (HTTP/MQTT)
    2. Finish current operations (with timeout)
    3. Disconnect MQTT cleanly
    4. Close database connections
    5. Release hardware resources
    6. Final logging
    """
    logger.info("shutdown_initiated")
    
    try:
        # 1. Stop accepting new work
        logger.info("shutdown_step", step="stop_accepting_requests")
        # FastAPI stops automatically, MQTT unsubscribe
        await mqtt_client.unsubscribe_all()
        
        # 2. Wait for current operations (max 10 seconds)
        logger.info("shutdown_step", step="finishing_current_tasks")
        try:
            await asyncio.wait_for(
                finish_pending_operations(),
                timeout=10.0
            )
            logger.info("shutdown_step", step="tasks_completed")
        except asyncio.TimeoutError:
            logger.warning("shutdown_timeout", step="pending_operations")
        
        # 3. Disconnect MQTT cleanly (sends disconnect packet)
        logger.info("shutdown_step", step="mqtt_disconnect")
        try:
            await asyncio.wait_for(
                mqtt_client.disconnect(),
                timeout=3.0
            )
            logger.info("mqtt_disconnected")
        except Exception as e:
            logger.error("mqtt_disconnect_failed", error=str(e))
        
        # 4. Close database connections (Backend only)
        if hasattr(globals(), 'db_connection'):
            logger.info("shutdown_step", step="database_close")
            await db_connection.close()
        
        # 5. Release hardware resources (Hardware/RFID/Audio services)
        if hardware_resources:
            logger.info("shutdown_step", step="hardware_cleanup")
            hardware_resources.cleanup()
        
        # 6. Final log
        logger.info("shutdown_completed", uptime=get_uptime())
        
    except Exception as e:
        logger.critical("shutdown_error", error=str(e))
        raise
```

### Main-Loop mit Shutdown

Template für `main.py`:

```python
async def main() -> None:
    """Main entry point with graceful shutdown"""
    
    # Initialize resources
    mqtt_client = await init_mqtt()
    app = create_fastapi_app()
    hardware = init_hardware() if HAS_HARDWARE else None
    
    logger.info("service_started", service="rfid_service", version="1.0")
    
    # Publish startup event
    await mqtt_client.publish(
        "minabox/system/service/started",
        json.dumps({"service": "rfid", "timestamp": datetime.utcnow().isoformat()})
    )
    
    try:
        # Run service tasks
        await asyncio.gather(
            run_mqtt_loop(mqtt_client),
            run_api_server(app),
            run_hardware_loop(hardware) if hardware else asyncio.sleep(0),
        )
    except ServiceShutdown:
        logger.info("shutdown_requested")
    except Exception as e:
        logger.critical("service_crashed", error=str(e))
        raise
    finally:
        # Always run shutdown sequence
        await shutdown_sequence(mqtt_client, app, hardware)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.critical("fatal_error", error=str(e))
        sys.exit(1)
```

### MQTT Disconnect Best Practices

Saubere MQTT-Trennung verhindert "Last Will" Messages:

```python
class MQTTClientWrapper:
    async def disconnect(self) -> None:
        """Cleanly disconnect from MQTT broker"""
        try:
            # Cancel pending publishes
            await self._flush_queue(timeout=2.0)
            
            # Unsubscribe from all topics
            for topic in self.subscriptions:
                await self.client.unsubscribe(topic)
                logger.debug("mqtt_unsubscribed", topic=topic)
            
            # Send disconnect packet
            await self.client.disconnect()
            logger.info("mqtt_disconnect_clean")
            
        except Exception as e:
            logger.error("mqtt_disconnect_error", error=str(e))
            # Force disconnect
            self.client.force_disconnect()
```

### Timeout-Handling

Alle Shutdown-Operationen müssen Timeouts haben:

```python
async def finish_pending_operations() -> None:
    """Wait for pending operations to complete"""
    
    tasks = [
        wait_for_audio_playback(),
        wait_for_rfid_read(),
        flush_event_cache(),
    ]
    
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("shutdown_task_timeout", task=task.__name__)
            # Continue with next task
```

### Docker Integration

Docker sendet SIGTERM bei `docker stop`, dann nach 10 Sekunden SIGKILL:

```dockerfile
# Dockerfile
STOPSIGNAL SIGTERM

# Gibt 30 Sekunden für Graceful Shutdown
# In docker-compose.yml:
services:
  rfid:
    stop_grace_period: 30s
```

Health-Check während Shutdown:

```python
# service_name/api/routes.py
@app.get("/health")
async def health_check():
    if shutdown_event.is_set():
        # Return 503 during shutdown
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
                "service": "rfid"
            }
        )
    
    return {"status": "healthy", "service": "rfid"}
```

### Hardware-Cleanup

Hardware-Services müssen Geräte sauber freigeben:

```python
class RFIDReader:
    def cleanup(self) -> None:
        """Release hardware resources"""
        try:
            logger.info("hardware_cleanup", device="pn532")
            
            # Reset GPIO pins
            if self.reset_pin:
                GPIO.cleanup(self.reset_pin)
            
            # Close I2C bus
            if self.i2c_bus:
                self.i2c_bus.close()
            
            logger.info("hardware_cleanup_complete")
            
        except Exception as e:
            logger.error("hardware_cleanup_error", error=str(e))
```

### Testing Graceful Shutdown

Manuelle Tests in `docs/TESTING.md`:

```text
# Graceful Shutdown Tests

## Docker Stop
- [ ] `docker compose stop rfid` → Logs zeigen "shutdown_initiated"
- [ ] MQTT disconnect message sichtbar
- [ ] Keine ERROR-Logs während Shutdown
- [ ] Container stoppt innerhalb von stop_grace_period

## SIGTERM
- [ ] `docker kill --signal=SIGTERM minabox-rfid`
- [ ] Service beendet laufende Tasks
- [ ] Hardware wird freigegeben

## Während Operation
- [ ] Shutdown während RFID-Scan → Scan wird abgeschlossen
- [ ] Shutdown während Audio-Playback → Playback stoppt sauber
- [ ] Queued MQTT-Messages werden gesendet
```

### Best Practices

1. **Idempotent Cleanup:** Cleanup-Funktionen müssen mehrfach aufrufbar sein
2. **Logging:** Jeder Shutdown-Schritt muss geloggt werden
3. **Timeout Everything:** Keine unendlichen Waits
4. **No Data Loss:** Cache/Queue vor Disconnect leeren
5. **Status Events:** MQTT-Event bei Shutdown publizieren
6. **Error Handling:** Fehler im Cleanup nicht weiterwerfen

---

## 10. Datenbank & Persistence

### SQLite im Backend-Container

- **Technologie:** SQLite 3
- **ORM:** SQLAlchemy
- **Migrations:** Alembic
- **Speicherort:** `/app/data/minabox.db` (gemounted als Volume)

### Schema-Beispiel

```sql
CREATE TABLE tags (
    tag_id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE content (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Zugriff

Nur Backend hat direkten DB-Zugriff:
- Andere Services fragen Backend via REST API
- Backend exponiert `/api/v1/tags`, `/api/v1/content`

Beispiel:

```python
# Audio-Service fragt Backend
response = await httpx.get(f"http://backend:8000/api/v1/tags/{tag_id}")
content = response.json()
```

---

## 11. Configuration Management

### Zwei-Ebenen-System

**1. Zentrale .env (Root-Ebene) - Gemeinsame Werte:**

```bash
# .env
MQTT_BROKER=mosquitto
MQTT_PORT=1883
LOG_LEVEL=INFO
BACKEND_URL=http://backend:8000
```

**2. Service-JSONs (config/*.json) - Service-spezifisch:**

```json
// config/rfid.json
{
    "i2c_bus": 1,
    "scan_cooldown_ms": 2000,
    "reset_pin": 6
}
```

### Schema-basierte Config (dezentral)

Jeder Service definiert sein eigenes Schema:

```python
# rfid_service/config_schema.py
from enum import Enum

class ParamType(Enum):
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"

RFID_SCHEMA = {
    "rfid": {
        "i2c_bus": {
            "type": ParamType.INTEGER,
            "default": 1,
            "range": [1, 2],
            "storage": "json",
            "description": "I2C bus number",
            "affects_services": ["rfid"]
        },
        "scan_cooldown_ms": {
            "type": ParamType.INTEGER,
            "default": 2000,
            "range": [500, 10000],
            "storage": "json",
            "description": "Cooldown between tag scans"
        }
    }
}
```

### ConfigManager pro Service

```python
# rfid_service/config_manager.py
class RFIDConfigManager:
    def __init__(self):
        self.schema = RFID_SCHEMA
        self._load_from_env()  # Lädt .env
        self._load_from_json("/app/config/rfid.json")
    
    def update_value(self, section: str, key: str, value: Any):
        self._validate_value(section, key, value)
        self._write_json_key(key, value)
        self.config[section][key] = value  # Hot-Reload!
        return True
    
    def reload(self):
        self._load_from_env()
        self._load_from_json("/app/config/rfid.json")

rfid_config = RFIDConfigManager()
```

### Hot-Reload via MQTT

**MQTT Config Protocol** - Jeder Service exponiert:

```text
minabox/{service}/config/schema          → Get Schema
minabox/{service}/config/get             → Get Values
minabox/{service}/config/update          → Update + Hot-Reload
minabox/{service}/config/validate-value  → Validate
minabox/{service}/config/reload          → Reload Config
```

Service implementiert:

```python
# rfid_service/main.py
async def mqtt_config_server():
    async with Client("mosquitto") as mqtt:
        await mqtt.subscribe("minabox/rfid/config/#")
        
        async for message in mqtt.messages:
            if message.topic.endswith("/update"):
                payload = json.loads(message.payload)
                try:
                    rfid_config.update_value(...)
                    response = {"success": True}
                except ValueError as e:
                    response = {"success": False, "error": str(e)}
                
                await mqtt.publish("response", json.dumps(response))
```

### Backend als Config-Gateway

Backend aggregiert Config von allen Services:

```python
# backend/api/config.py
@router.get("/parameters")
async def get_all_parameters():
    mqtt_client = get_mqtt_config_client()
    
    rfid = await mqtt_client.request_schema("rfid")
    audio = await mqtt_client.request_schema("audio")
    hardware = await mqtt_client.request_schema("hardware")
    
    return {**rfid, **audio, **hardware}

@router.post("/update")
async def update_parameter(request: ConfigUpdateRequest):
    service = get_service_for_section(request.section)
    
    result = await mqtt_client.update_parameter(
        service=service,
        section=request.section,
        key=request.key,
        value=request.value
    )
    return result
```

### 3-Ebenen-Validierung

1. **WebUI (Live)** - Während User tippt
2. **Backend (Pre-Check)** - Vor MQTT-Send
3. **Service (Final)** - Vor Schreiben

**Resultat:** Ungültige Werte werden nie gespeichert

### Config-Update-Flow

```text
WebUI ändert Wert
  ↓ HTTP POST /config/update
Backend empfängt
  ↓ MQTT: minabox/{service}/config/update
Service empfängt
  ├─ Validiert
  ├─ Schreibt JSON
  └─ Update in-memory (Hot-Reload!)
Backend empfängt Response
  ↓ HTTP Response
WebUI zeigt "✓ Gespeichert"

Gesamt: ~50ms
```

---

## Best Practices

- **DRY (Don't Repeat Yourself)** - Gemeinsam genutzte Funktionalität in `shared/` Package
- **SOLID-Prinzipien** - Insbesondere Single Responsibility und Dependency Inversion
- **12-Factor-App** - Für Cloud-native Mikroservices
- **Semantic Versioning** - Für APIs und Service-Releases
- **KISS (Keep It Simple)** - Einfache Lösung > Komplexe Lösung

---

## Referenzen

- **Phoniebox** - Inspiration für Features
- **TonUINO** - Arduino-basierte Alternative
- **12-Factor-App:** https://12factor.net/
- **Python Best Practices:** https://docs.python-guide.org/

---

**Letzte Aktualisierung:** 2026-02-14  
**Version:** 1.1
