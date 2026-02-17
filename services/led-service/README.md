# LED Service

GPIO-based LED control service for Minabox. Controls simple single-color LEDs to display system status, audio playback state, and RFID events.

## Features

- **Pattern-based LED control**: Solid, blink, and pulse patterns
- **Flexible state mapping**: Map logical states (e.g., `audio_playing`, `system_error`) to LED patterns
- **Hot-reload configuration**: Update LED configuration via MQTT without service restart
- **MQTT integration**: Subscribes to relevant topics and derives logical states
- **Health check API**: FastAPI endpoint for monitoring
- **Graceful shutdown**: Clean resource cleanup on SIGTERM/SIGINT

## Architecture

See [`docs/services/led/Architecture.md`](../../docs/services/led/Architecture.md) for detailed architecture documentation.

### Logical States

The service reacts to logical states derived from MQTT messages:

**System:**
- `system_online`, `system_booting`, `system_error`, `system_updating`

**Audio:**
- `audio_playing`, `audio_paused`, `audio_stopped`, `audio_buffering`

**RFID:**
- `rfid_scanned`, `rfid_unknown_tag`

**User Interaction:**
- `button_pressed`, `config_change`

**Network:**
- `backend_unreachable`, `mqtt_disconnected`

### Pattern Types

- **solid**: LED permanently on (or off)
- **blink**: LED toggles at regular intervals
- **pulse**: LED briefly lights up then turns off

## Configuration

### Environment Variables (Required)

These must be set in the root `.env` file:

```bash
MINABOX_DEVICE_ID=box1        # Device ID for MQTT topics
MQTT_BROKER=mqtt              # MQTT broker hostname
MQTT_PORT=1883                # MQTT broker port
LOG_LEVEL=INFO                # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LED Configuration
LEDs are configured in config/leds.json:

json
{
  "leds": [
    {
      "id": "led_5",
      "name": "Power-LED",
      "gpio": 5,
      "bindings": {
        "system_online": {
          "pattern_type": "solid",
          "duration_ms": 0
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
Fields:

id: Internal LED identifier (e.g., led_5)

name: Human-readable name for UI and logs

gpio: GPIO pin number

bindings: Map of logical states to patterns

pattern_type: "solid", "blink", or "pulse"

duration_ms: Pattern duration (0 = infinite for solid)

interval_ms: Blink interval (required for blink)

repeat: Number of repetitions (0 = infinite)

MQTT Topics
Subscriptions
The service subscribes to:

text
minabox/{device-id}/audio/status
minabox/{device-id}/rfid/tag-scanned
minabox/{device-id}/rfid/tag-removed
minabox/{device-id}/rfid/unknown-tag
minabox/{device-id}/system/service-started
minabox/{device-id}/system/service-error
minabox/{device-id}/system/booting
minabox/{device-id}/button/raw-event
minabox/{device-id}/backend/unreachable
minabox/{device-id}/led/config/update
minabox/{device-id}/led/config/reload
minabox/{device-id}/led/config/get
Config API
Update configuration:

text
Topic: minabox/{device-id}/led/config/update
Payload: Full LED configuration JSON
Reload from disk:

text
Topic: minabox/{device-id}/led/config/reload
Payload: (empty)
Get current config:

text
Topic: minabox/{device-id}/led/config/get
Payload: (empty)
Response:

text
Topic: minabox/{device-id}/led/config/response
Payload:
{
  "success": true,
  "error": null,
  "timestamp": "2026-02-17T07:54:00Z"
}
REST API
Health Check
text
GET /health
Response:

json
{
  "status": "healthy",
  "service": "led",
  "device_id": "box1",
  "leds_configured": 2,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
Development
Local Setup
bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MINABOX_DEVICE_ID=box1
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export LOG_LEVEL=DEBUG

# Run service
python -m led_service.main
Docker Build
bash
# From service directory
docker build -t minabox/led-service:latest .

# Run
docker run --rm \
  --device /dev/gpiomem \
  -e MINABOX_DEVICE_ID=box1 \
  -e MQTT_BROKER=mqtt \
  -e MQTT_PORT=1883 \
  -e LOG_LEVEL=INFO \
  minabox/led-service:latest
Code Quality
bash
# Format code
ruff format src/

# Lint
ruff check src/ --fix

# Type check
mypy src/
Hardware Setup
GPIO Pins
Connect LEDs with appropriate current-limiting resistors:

text
GPIO Pin → Resistor (220Ω) → LED Anode (+)
LED Cathode (-) → Ground
Raspberry Pi GPIO Access
For GPIO access, the container needs:

Device access: --device /dev/gpiomem

Or run as privileged: --privileged

Or add user to gpio group on host

Logging
The service uses structured logging with structlog:

Development (LOG_LEVEL=DEBUG):

text
2026-02-17 07:54:19 [info] led_initialized led_id=led_5 led_name=Power-LED gpio=5
Production (LOG_LEVEL=INFO):

json
{"event": "led_initialized", "led_id": "led_5", "led_name": "Power-LED", "gpio": 5, "level": "info", "timestamp": "2026-02-17T07:54:19.123456Z"}
Troubleshooting
LEDs not responding
Check GPIO permissions: User must have access to /dev/gpiomem

Verify GPIO pin numbers in config/leds.json

Check LED wiring and resistor values

Check logs: docker logs led-service

MQTT connection issues
Verify MQTT_BROKER and MQTT_PORT environment variables

Check network connectivity to MQTT broker

Check MQTT broker logs

Config updates not applied
Check MQTT config/response topic for error messages

Validate JSON syntax in config payload

Check logs for validation errors

License
Part of the Minabox project - Open Source Toniebox alternative.

text

***

## ✅ Chat 4 abgeschlossen!

Folgende **4 Dateien** sind jetzt fertig:

1. ✅ `requirements.txt` (erweitert um FastAPI, uvicorn)
2. ✅ `src/led_service/api/__init__.py` - API Package Init
3. ✅ `src/led_service/api/routes.py` - FastAPI Health-Check
4. ✅ `src/led_service/main.py` (erweitert um FastAPI-Integration)
5. ✅ `Dockerfile` - Production-ready Multi-Stage Build
6. ✅ `README.md` - Vollständige Dokumentation

**Der LED-Service ist jetzt KOMPLETT!** 🎉🎉🎉

***

## 📦 Vollständige Service-Struktur

services/led-service/
├── Dockerfile ✅
├── README.md ✅
├── requirements.txt ✅
├── pyproject.toml ✅
├── config/
│ └── leds.json ✅
├── src/
│ └── led_service/
│ ├── init.py ✅
│ ├── main.py ✅
│ ├── config.py ✅
│ ├── config_schema.py ✅
│ ├── config_manager.py ✅
│ ├── exceptions.py ✅
│ ├── led_patterns.py ✅
│ ├── led_controller.py ✅
│ ├── state_manager.py ✅
│ ├── mqtt_client.py ✅
│ └── api/
│ ├── init.py ✅
│ └── routes.py ✅