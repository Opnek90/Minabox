# Display Service

I2C OLED (SSD1306 128x64) status display service for Minabox. Layout: **header** (full width) for clock and error indicator, then **two columns** (left | right) for volume, play state, mute, sleep timer, etc.

## Features

- **Layout**: Area 0 = header (full width), area 1 = left column, area 2 = right column.
- **Element types**: volume, sleep_timer, mute, play_state (as play/pause/stop icons), clock, error_state (exclamation when error).
- **MQTT**: Subscribes to `audio/status`, `audio/error`, `system/service-error`, and `display/config/reload`.
- **Sleep timer**: Moon icon + remaining minutes; data from backend `GET /api/v1/audio/sleep-timer`.
- **Error state**: Shows exclamation icon in header when `audio/error` or `system/service-error` is received; cleared on next `audio/status`.
- **Icons**: PNGs in `src/display_service/assets/icons/` (icon_mute.png, icon_moon.png, icon_play.png, icon_pause.png, icon_stop.png, icon_error.png). Replace 16×16 images to customize.

## Config

`config/display.json`:

- `enabled`: global on/off
- `i2c_bus`, `i2c_address`: hardware (default 1, 60)
- `elements`: `[{ id, type, enabled, order, area }]` — `area`: 0 = header, 1 = left, 2 = right. Only enabled elements are shown, in order.

## Run

Part of the Minabox stack via `docker compose up`. Requires I2C enabled (`raspi-config` → Interface Options → I2C).

**Scripts:** `scripts/generate_icon_assets.py` – generates or updates icon assets from a source (run from service root if needed).
