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

See [docs/services/button/](../../docs/services/button/README.md) for full architecture.

### Event types (raw)

- `short_press`, `long_press`, `double_press` (push)
- `rotate_cw`, `rotate_ccw`, `press` (encoder rotation and switch)

### MQTT topics (published)

- **Actions**: `minabox/<device-id>/button/<action>` (e.g. `play-pause`, `volume-up`, `next`)
- **Raw events**: `minabox/<device-id>/button/raw-event` – every accepted press, before mapping. Not debug-only: the LED service and the WebUI hardware test both rely on it.
- **Config response**: `minabox/<device-id>/button/config/response` – currently without a subscriber.

### Config API (subscribed)

- `minabox/<device-id>/button/config/reload` – reload from disk. This is the one the backend uses.
- `minabox/<device-id>/button/config/update` – full config JSON. Supported, but nothing publishes it.
- `minabox/<device-id>/button/config/get` – request current config. Supported, but nothing publishes it, and the reply carries no config.

## Configuration

### Environment variables (required)

Set in root `.env` or container env:

```bash
MINABOX_DEVICE_ID=box1
MQTT_BROKER=mqtt
MQTT_PORT=1883
LOG_LEVEL=INFO   # DEBUG, INFO, WARNING, ERROR, CRITICAL
# Optional: set to true to skip GPIO init (e.g. in containers without /dev/gpiochip0)
DISABLE_GPIO=false
# Optional: REST API port (default 8000)
API_PORT=8000
```

### Button configuration

`config/buttons.json`. Managed through the WebUI (*Admin -> Buttons*), which
writes the file and triggers a reload over MQTT. Editing it by hand works too;
send `minabox/<device-id>/button/config/reload` afterwards, or restart.

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
      "name": "Volume",
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
- **enabled**: `false` keeps publishing `raw-event` (so the WebUI hardware test still shows the button) but dispatches no action. Defaults to `true`.
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
  "version": "0.1.2",
  "device_id": "box1",
  "buttons_configured": 2,
  "buttons_available": 2,
  "gpio_enabled": true,
  "config_error": null,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`status` is `degraded` when the broker is away, when `buttons_available` is
below `buttons_configured` (a pin could not be claimed), or when
`config_error` is set (buttons.json does not load).

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

**Option B – build with the version numbers baked in**

`docker compose build` cannot read the VERSION file, so a compose build always
reports `0.0.0-dev`. The script does it properly and tags `:local`:

```bash
./scripts/build-local.sh button
MINABOX_BUTTON_TAG=local docker compose up -d button
docker compose up -d button   # back to the published image
```

The build context is `./services`, not this directory -- the Dockerfile copies
`shared-lib` as well, so `docker build .` from here cannot work.

For GPIO the container uses **lgpio**, which talks to `/dev/gpiochip0` directly and therefore works without a device-tree mount. The container needs `/dev/gpiochip0`, `/dev/gpiomem`, user `1000:986` and `group_add: "986"` -- `docker-compose.yml` sets all of that up.

### Code quality

```bash
ruff format src/
ruff check src/ --fix
mypy src/
```

## Hardware

- **Push button**: One leg to GPIO, other to GND (internal pull-up). BCM pin numbers in `gpio`.
- **Rotary encoder**: CLK/DT to two GPIOs, SW (switch) to a third. BCM pins: `clk`, `dt`, `sw`.

### CPU

lgpio's alert thread polls, so every claimed pin costs CPU even when nothing
happens. The build pins that poll interval via the `LG_ALERT_POLL_NS` build arg
in the Dockerfile (2 ms, against upstream's 0.5 ms) -- measured at roughly 3 %
of one core instead of 8 % on a Pi 4.

**Avoid pin conflicts:** no GPIO pin may appear in both the LED service (`config/leds.json`) and the button service (`config/buttons.json`). Whichever service starts first claims the pin; the other one logs `gpio_input_init_failed` and leaves that button inactive, while every other button keeps working. `/health` then reports `degraded` with `buttons_available` below `buttons_configured`. The example config here only uses pins the default `leds.json` does not (17, 27, 22, 4, 16).

## Troubleshooting

- **No button events**: check `config/buttons.json` and the GPIO pins. `docker logs minabox-button | grep gpio_input_init_failed` names any pin that could not be claimed -- usually one that also appears in `leds.json`.
- **MQTT not connected**: Verify `MQTT_BROKER`, `MQTT_PORT` and network to broker; check logs.
- **Config update fails**: the WebUI rejects an incomplete button before saving, and the backend answers `422` with the offending button and field. If the file was edited by hand, `/health` reports `config_error` and the service comes up without buttons rather than restarting in a loop.
- **Health check fails**: Ensure port 8000 is exposed and service has started (see logs).

## License

Part of the Minabox project – Open Source Toniebox alternative.
