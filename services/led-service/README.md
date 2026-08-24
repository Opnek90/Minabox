# LED Service

GPIO-based LED control for Minabox. The service subscribes to MQTT events, derives logical states (e.g. `audio_playing`, `rfid_scanned`, `usage_denied`), and renders LED patterns based on `config/leds.json`.

Detailed MQTT topic mapping, logical state derivation rules, and payload shapes are documented in [`docs/services/led/Architecture.md`](../../docs/services/led/Architecture.md).

## REST API

Service root endpoints:
- `GET /health`
- `POST /test` (body: `{ "led_id": string }`)

## Configuration

Main config file: `config/leds.json`

Each LED entry:
- `id`, `name`, `gpio`
- `enabled` (when `false`, the LED ignores state changes and stays off)
- `bindings`: mapping from logical state (e.g. `system_online`) to a pattern (`solid`, `blink`, `pulse`, `off`, `glow`)

Pattern fields:
- `pattern_type`
- `interval_ms` (required for `blink`): on-time, and off-time, of one blink
- `duration_ms` (required for `pulse`): on-time per pulse; cleared on every other pattern type
- `repeat` (optional): number of complete cycles — one blink is on *and* off again. `0`/`null` repeats until another state overrides the LED
- `cycle_ms`, `min_brightness`, `max_brightness` (`glow` only)

A pattern the service could not run — a `pulse` without a duration, a `glow`
whose `min_brightness` is not below its `max_brightness` — is repaired with a
default and a warning rather than rejected, so one bad binding cannot stop the
service from starting.

## MQTT Topics

Topic prefix pattern:
- `minabox/<device-id>/...`

Subscriptions (key ones):
- Audio status: `.../audio/status`
- RFID events: `.../rfid/tag-scanned`, `.../rfid/tag-removed`, `.../rfid/unknown-tag`
- RFID blocked: `.../rfid/tag-blocked` (published by the backend for a blocked card)
- System events: `.../system/service-started`, `.../system/service-error`, `.../system/booting`
- Button raw events: `.../button/raw-event`
- Backend health: `.../backend/unreachable`
- Parental/usage outside limits: `.../led/usage-denied`

Configuration & log-level:
- `.../config/general` (MQTT payload includes `log_level`)
- `.../led/config/update` (full config JSON)
- `.../led/config/reload`
- `.../led/config/get` and response on `.../led/config/response`

