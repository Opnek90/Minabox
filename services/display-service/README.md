# Display Service

I2C OLED (SSD1306 128x64) status display service for Minabox. Shows configurable elements (volume, sleep timer, mute, play state, clock) on a 0.96" I2C OLED.

## Features

- **Dynamic config**: Enable/disable and reorder elements via Admin UI (config/display.json).
- **Element types**: volume, sleep_timer, mute, play_state, clock.
- **MQTT**: Subscribes to `audio/status` for state, volume, muted.
- **Sleep timer**: Polls backend `GET /api/v1/audio/sleep-timer` for remaining time.
- **Config reload**: Subscribes to `display/config/reload` for hot-reload.
- **Hardware**: Uses `/dev/i2c-1`, address 0x3C (configurable). Same I2C bus as RFID (different address).

## Config

`config/display.json`:

- `enabled`: global on/off
- `i2c_bus`, `i2c_address`: hardware (default 1, 60)
- `elements`: `[{ id, type, enabled, order }]` — only enabled elements are shown, in order.

## Run

Part of the Minabox stack via `docker compose up`. Requires I2C enabled (`raspi-config` → Interface Options → I2C).
