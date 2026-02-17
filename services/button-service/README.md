# Button Service

GPIO-based button and rotary encoder service for Minabox. Reads physical inputs (push buttons, rotary encoders), classifies events (short/long press, rotate CW/CCW), applies configurable mapping, and publishes action events via MQTT.

## Features

- **Push buttons**: Short press, long press (configurable hold time)
- **Rotary encoders**: Rotation (CW/CCW) and switch (press)
- **Configurable mapping**: Basic (one action per button) or advanced (per-event-type actions)
- **Hot-reload configuration**: Update button config via MQTT without restart
- **FIFO event processing**: Deterministic handling of rapid or simultaneous inputs
- **Health check API**: FastAPI `/health` endpoint
- **Graceful shutdown**: Clean GPIO and MQTT teardown on SIGTERM/SIGINT

## Architecture

See [docs/services/button/Architecture.md](../../docs/services/button/Architecture.md) for full architecture.

### Event types (raw)

- `short_press`, `long_press`, `double_press` (push)
- `rotate_cw`, `rotate_ccw`, `press` (encoder rotation and switch)

### MQTT topics (published)

- **Actions**: `minabox/<device-id>/button/<action>` (e.g. `play-pause`, `volume-up`, `next`)
- **Raw events** (optional/debug): `minabox/<device-id>/button/raw-event`
- **Config response**: `minabox/<device-id>/button/config/response`

### Config API (subscribed)

- `minabox/<device-id>/button/config/update` – full config JSON
- `minabox/<device-id>/button/config/reload` – reload from disk
- `minabox/<device-id>/button/config/get` – request current config

## Configuration

### Environment variables (required)

Set in root `.env` or container env:

```bash
MINABOX_DEVICE_ID=box1
MQTT_BROKER=mqtt
MQTT_PORT=1883
LOG_LEVEL=INFO   # DEBUG, INFO, WARNING, ERROR, CRITICAL
# Optional: set to true to skip GPIO init (e.g. in containers without /dev/gpiomem)
DISABLE_GPIO=false
```

### Button configuration

`config/buttons.json`:

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

- **mode**: `basic` → single `action` for all events; `advanced` → `actions` map (event_type → action name).
- **type**: `push` → `gpio`; `rotary` → `clk`, `dt`, `sw` (BCM pin numbers).
- Action names are published as topic suffix (e.g. `play_pause` → topic `.../button/play-pause`).

## REST API

### Health

```http
GET /health
```

Example response:

```json
{
  "status": "healthy",
  "service": "button",
  "device_id": "box1",
  "buttons_configured": 2,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

## Development

### Local run

```bash
cd services/button-service
pip install -r requirements.txt

export MINABOX_DEVICE_ID=box1
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export LOG_LEVEL=DEBUG

python -m button_service.main
```

### Docker build and run

**Option A – from repo root (recommended)**

The Button service is defined in the root `docker-compose.yml`. Ensure `.env` has `MQTT_BROKER`, `MQTT_PORT`, `MINABOX_DEVICE_ID`, `LOG_LEVEL`, then:

```bash
# From repository root
docker compose build button
docker compose up -d button

# Logs
docker compose logs -f button
```

**Option B – standalone from service directory**

```bash
cd services/button-service
docker build -t minabox/button-service:latest .

docker run --rm \
  --device /dev/gpiomem \
  -e MINABOX_DEVICE_ID=box1 \
  -e MQTT_BROKER=mqtt \
  -e MQTT_PORT=1883 \
  -e LOG_LEVEL=INFO \
  -p 8000:8000 \
  minabox/button-service:latest
```

Für GPIO nutzt der Container **RPi.GPIO**; das Host-**Device-Tree** wird read-only gemountet (`/proc/device-tree`), damit die Pi-Erkennung im Container greift. Zusätzlich: `/dev/gpiomem`, User `1000:986`, `group_add: "986"`.

### Code quality

```bash
ruff format src/
ruff check src/ --fix
mypy src/
```

## Hardware

- **Push button**: One leg to GPIO, other to GND (internal pull-up). BCM pin numbers in `gpio`.
- **Rotary encoder**: CLK/DT to two GPIOs, SW (switch) to a third. BCM pins: `clk`, `dt`, `sw`.

**Pin-Konflikt vermeiden:** Kein GPIO-Pin darf gleichzeitig im LED-Service (`config/leds.json`) und im Button-Service (`config/buttons.json`) vorkommen. Sonst konfiguriert ein Service den Pin (z. B. als Output für LED), der andere überschreibt ihn (z. B. als Input für Button) – die LED reagiert dann nicht mehr. Die Beispiel-Config hier verwendet nur Pins, die in der Standard-`leds.json` (17, 27, 22) nicht vorkommen.

## Troubleshooting

- **No button events**: Check `config/buttons.json` and GPIO pins; ensure container has `--device /dev/gpiomem`.
- **MQTT not connected**: Verify `MQTT_BROKER`, `MQTT_PORT` and network to broker; check logs.
- **Config update fails**: Ensure JSON is valid and matches schema; check `button/config/response` for `success: false` and `error` field.
- **Health check fails**: Ensure port 8000 is exposed and service has started (see logs).

## License

Part of the Minabox project – Open Source Toniebox alternative.
