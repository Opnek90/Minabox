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
- `bindings`: mapping from logical state (e.g. `system_online`) to a pattern (`solid`, `blink`, `pulse`, `off`)

Pattern fields (subset):
- `pattern_type`
- `duration_ms` (optional; `0`/`null` means “until overridden” for `solid`)
- `interval_ms` (required for `blink`)
- `repeat` (optional; `0`/`null` means repeat indefinitely)

## MQTT Topics

Topic prefix pattern:
- `minabox/<device-id>/...`

Subscriptions (key ones):
- Audio status: `.../audio/status`
- RFID events: `.../rfid/tag-scanned`, `.../rfid/tag-removed`, `.../rfid/unknown-tag`
- RFID blocked: `.../rfid/tag-blocked` (derived from Backend content restrictions)
- System events: `.../system/service-started`, `.../system/service-error`, `.../system/booting`
- Button raw events: `.../button/raw-event`
- Backend health: `.../backend/unreachable`
- Parental/usage outside limits: `.../led/usage-denied`

Configuration & log-level:
- `.../config/general` (MQTT payload includes `log_level`)
- `.../led/config/update` (full config JSON)
- `.../led/config/reload`
- `.../led/config/get` and response on `.../led/config/response`

