# Display Service

I2C OLED (SSD1306 128×64) status display for Minabox. Layout: a **header**
across the full width, then **two columns** below it. What appears where is
configuration.

Full documentation: [docs/services/display/Architecture.md](../../docs/services/display/Architecture.md).

## What it shows

Nine element types, each placeable in any of the three areas:

| Type | Shows | Appears |
| --- | --- | --- |
| `clock` | `HH:MM` | always |
| `volume` | `NN%` | always |
| `play_state` | play / pause / stop icon | always |
| `mute` | mute icon | while muted |
| `bluetooth` | Bluetooth icon | when a BT sink exists and more than one output is enabled |
| `error_state` | exclamation icon | for 5 minutes after an error |
| `sleep_timer` | moon icon + remaining minutes | while the timer runs |
| `repeat` | repeat icon | while repeat-all is on |
| `shuffle` | shuffle icon | while shuffle is on |

Icons are drawn as vectors by `IconRenderer`, not loaded from files — there is
nothing to replace on disk.

## Where the data comes from

- **MQTT:** `audio/status`, `audio/error`, `system/service-error`,
  `display/config/reload`, `config/general`.
- **Backend REST:** `GET /api/v1/audio/sleep-timer` (every 5 s),
  `GET /api/v1/audio/session` (every 15 s) and
  `GET /api/v1/system/network-status` (every 20 s, for the network screen).

The render loop ticks once a second but only pushes a frame when the content
actually changed — the panel shares `/dev/i2c-1` with the RFID reader, so an
identical redraw is pure bus contention.

## Config

`config/display.json`, written by the backend and mounted read-only:

- `enabled` — global on/off
- `i2c_bus`, `i2c_address` — hardware (default `1`, `60` = 0x3C)
- `font_size` — `small` | `medium` | `large`
- `font` — `default` | `sans` | `mono` | `roboto` | `ubuntu` | `noto` |
  `liberation` | `terminus` (only DejaVu ships in the image; the rest fall back)
- `elements` — `[{ id, type, enabled, order, area }]`, `area`: 0 = header,
  1 = left, 2 = right

Changes take effect on `display/config/reload` without a restart, including a
changed I2C address or switching the display off.

## API

- `GET /health` — reports `degraded` when the broker is away, or when the
  display is enabled but no panel answered.
- `POST /test` — six-second test pattern for the setup wizard; 404 when there is
  no panel.

## Run

Part of the Minabox stack, under the `display` compose profile. Requires I2C
enabled (`raspi-config` → Interface Options → I2C).

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/display-service/tests -q
```
