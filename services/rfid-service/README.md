# RFID Service

**Version:** 0.1.0  
**Python:** 3.13+

Hardware abstraction service for RFID tag reading in the Minabox project.

---

## Purpose

The RFID service is responsible for:

- Reading RFID tags from hardware readers (PN532, mock, etc.)
- Operating in two modes: **Normal** (playback triggering) and **Learning** (tag registration)
- Publishing tag events to MQTT for consumption by other services
- Duplicate suppression to prevent repeated scans of the same tag
- Tag removal detection

**Non-Goals:**
- No database access (tags are mapped by the backend service)
- No direct audio control (publishes events, backend orchestrates playback)
- No web UI (controlled via MQTT commands from backend/WebUI)

---

## Architecture

See [docs/services/rfid/Architecture.md](../../docs/services/rfid/Architecture.md) for detailed architecture documentation.

### Key Components

- **Hardware Layer** (`hardware/`): Abstraction for different RFID readers
  - `RFIDReader`: Abstract interface
  - `PN532Reader`: Real PN532 hardware implementation
  - `MockReader`: Mock for testing without hardware
  - `create_reader()`: Factory for reader creation

- **MQTT Client** (`mqtt_client.py`): Connection management with retry logic
- **RFID Manager** (`rfid_manager.py`): Core logic (scanning, modes, events)
- **Event Models** (`models/`): Pydantic models for MQTT payloads
- **Configuration** (`config*.py`): Schema-based config management

---

## Configuration

### Required Environment Variables

Set in root `.env` file:

```bash
# Device identification
MINABOX_DEVICE_ID=box1

# MQTT broker
MQTT_BROKER=mqtt
MQTT_PORT=1883

# Logging
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR | CRITICAL
Service Configuration
Located in config/service.json:

json
{
  "reader": {
    "reader_type": "mock",
    "interface": "i2c",
    "scan_interval_ms": 200,
    "duplicate_suppression_ms": 2000
  }
}
Reader Types:

"mock": Mock reader for testing (no hardware required)

"pn532": PN532 NFC/RFID reader (requires pip install pn532pi)

Interfaces:

"i2c": I²C bus (Raspberry Pi default)

"spi": SPI interface

"uart": Serial UART

MQTT Topics
Published Events
Normal Mode
Topic: minabox/<device-id>/rfid/tag-scanned

QoS: 1

Retain: No

Payload:

json
{
  "tag_id": "04A224BC19",
  "reader_id": "pn532_i2c",
  "timestamp": "2026-02-16T22:48:00Z"
}
Learning Mode
Topic: minabox/<device-id>/rfid/tag-scanned-learning

QoS: 1

Retain: No

Payload: Same as tag-scanned

Tag Removed
Topic: minabox/<device-id>/rfid/tag-removed

QoS: 1

Retain: No

Payload:

json
{
  "tag_id": "04A224BC19",
  "reader_id": "pn532_i2c",
  "timestamp": "2026-02-16T22:48:10Z"
}
Status (Retained)
Topic: minabox/<device-id>/rfid/status

QoS: 1

Retain: Yes

Payload:

json
{
  "state": "normal",
  "reader_id": "pn532_i2c",
  "error": null,
  "timestamp": "2026-02-16T22:48:00Z"
}
States: idle, normal, learning, error

Error Codes: reader_not_found, reader_init_failed, read_timeout, protocol_error

Subscribed Commands
Set Mode
Topic: minabox/<device-id>/rfid/cmd/set-mode

Payload:

json
{"mode": "learning"}
or

json
{"mode": "normal"}
Development
Local Setup
bash
# Navigate to service directory
cd services/rfid-service

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For real PN532 hardware
pip install pn532pi

# Set environment variables
export MINABOX_DEVICE_ID=box1
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export LOG_LEVEL=DEBUG

# Run service
python -m rfid_service.main
Docker Build
bash
# Build image
docker build -t minabox-rfid-service:latest .

# Run standalone (requires MQTT broker)
docker run --rm \
  -e MINABOX_DEVICE_ID=box1 \
  -e MQTT_BROKER=mqtt \
  -e MQTT_PORT=1883 \
  -e LOG_LEVEL=INFO \
  -v $(pwd)/config:/app/config \
  minabox-rfid-service:latest
Production (Docker Compose)
The service is orchestrated via the root docker-compose.yml:

bash
# Start all services
docker compose up -d

# View RFID service logs
docker compose logs -f rfid

# Restart RFID service
docker compose restart rfid
Adding New Reader Types
To add support for a new RFID reader (e.g., RC522):

1. Create Reader Implementation
src/rfid_service/hardware/rc522_reader.py:

python
from typing import Literal
from .reader_interface import RFIDReader

class RC522Reader(RFIDReader):
    def __init__(self, interface: Literal["i2c", "spi", "uart"], **kwargs):
        # RC522-specific initialization
        pass
    
    def initialize(self) -> None:
        # Initialize RC522 hardware
        pass
    
    def read_tag_uid(self) -> str | None:
        # Read tag from RC522
        pass
    
    def cleanup(self) -> None:
        # Cleanup RC522 resources
        pass
    
    @property
    def reader_id(self) -> str:
        return f"rc522_{self._interface}"
2. Update Config Schema
src/rfid_service/config_schema.py:

python
reader_type: Literal["pn532", "rc522", "mock"]  # Add rc522
3. Update Reader Factory
src/rfid_service/hardware/reader_factory.py:

python
elif reader_type == "rc522":
    from .rc522_reader import RC522Reader
    return RC522Reader(interface=interface)
4. Update Configuration
config/service.json:

json
{
  "reader": {
    "reader_type": "rc522",
    "interface": "spi"
  }
}
Done! No other code changes needed.

Testing
Manual Testing Checklist
Hardware Tests (with real reader)
 Tag placed → tag_id logged and event published

 Tag removed → removal event published

 Unknown tag → handled gracefully

 Reader disconnect → service recovers

Integration Tests
 Tag scan → MQTT event received by backend

 Learning mode → backend receives learning event

 Mode switch (normal ↔ learning) → status updated

 Duplicate suppression → repeated scans within 2s ignored

Error Handling
 Missing env vars → service fails with clear error

 Invalid config → validation error logged

 MQTT broker down → retry with exponential backoff

 Reader hardware error → error state published

Troubleshooting
Service won't start
Check environment variables:

bash
docker compose exec rfid env | grep -E "MQTT|MINABOX|LOG"
Check config file:

bash
docker compose exec rfid cat /app/config/service.json
No tags detected
Check reader type:

Mock reader only returns predefined tags

For real hardware, ensure reader_type: "pn532" and pn532pi installed

Check hardware connection:

I2C: i2cdetect -y 1 (should show device at 0x24)

SPI: Verify GPIO connections

UART: Check /dev/ttyS0 permissions

MQTT connection fails
Check broker:

bash
docker compose ps mqtt
docker compose logs mqtt
Test connection:

bash
mosquitto_sub -h localhost -p 1883 -t "minabox/box1/#" -v
References
[Framework.md](../../docs/Framework.md) – Technical standards

RFID Architecture – Detailed architecture

PN532 Library – Hardware driver

aiomqtt Documentation – MQTT client

Last Updated: 2026-02-16
Maintainer: Minabox Project