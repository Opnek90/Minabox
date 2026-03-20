# Minabox Doc-Code Drift Report (2026-03-20)

This report lists concrete mismatches between current code and the existing documentation. It is meant to drive the doc sync work (REST endpoints, MQTT topics/actions, WebSocket message `type`s, and config schemas).

## Backend Service (`backend-service`)

### REST API
- **Health endpoint path**
  - Code exposes `GET /health` at the root of the backend service (see `services/backend-service/src/backend_service/app_factory.py`).
  - Docs claim `GET /api/v1/health` (but backend routers mount under `/api/v1`).
- **Additional audio endpoints not documented**
  - Code has (mounted under `/api/v1/audio/...`): `/seek`, `/session`, `/repeat`, `/shuffle`, `/devices`, `/switch-device` (see `services/backend-service/src/backend_service/api/routes_audio.py`).
  - Docs currently document only a subset (play/pause/stop/next/prev/volume/sleep-timer).
- **Extra config/admin enumeration endpoints not documented**
  - Code provides: `/api/v1/config/leds/states`, `/api/v1/config/leds/patterns`, `/api/v1/config/buttons/actions` (see `services/backend-service/src/backend_service/api/routes_config.py`).

### WebSocket
- **Incoming commands vs. ack**
  - Code’s WebSocket endpoint only parses incoming JSON and replies with `{"type":"ack","message":"Received"}` (see `services/backend-service/src/backend_service/api/websocket.py`).
  - Docs mention optional command handling; current code does not implement those commands.
- **WebSocket `type` set is incomplete in docs**
  - Code broadcasts additional `type`s: `tag_not_found`, `tag_blocked`, `sleep_timer_status`, `button_raw_event`, `repeat_mode`, `shuffle_mode`, `usage_denied` (see `services/backend-service/src/backend_service/core/handlers/*` and `core/mqtt_handlers.py`).
  - Docs currently focus only on `audio_status`, `rfid_scanned*`, `button_action`, `system_alert*` and an incorrect `service_status`.
- **Payload shape differs from docs**
  - `audio_status.data` is enriched with fields like `track_title`, `track_artist`, `track_album`, `track_cover_art_url`, `playlist_position`, `playlist_total` (see `services/backend-service/src/backend_service/core/handlers/audio_handler.py`).
  - `rfid_scanned_learning.data` includes `{ tag_id, already_assigned, timestamp }` and does not include `reader_id` (see `rfid_handler.py`).

### MQTT
- **Backend subscriptions missing in docs**
  - Backend subscribes to `audio/position-report` and `button/raw-event` (see `app_factory.py` subscription list).
  - Docs currently list a smaller subscription set.

## Audio Service (`audio-service`)

### REST API
- **Wrong health endpoint in docs**
  - Code exposes `GET /health` (root), and mounts API routes under `/api/v1` for: `/status`, `/devices`, `/switch-device` (see `services/audio-service/src/audio_service/api/routes.py` and `create_app()`).
  - Docs claim `/api/v1/health`.
- **Config schema differs**
  - Code supports `min_volume` in `config/audio.json` (see `services/audio-service/src/audio_service/config_schema.py`).
  - Docs omit `min_volume`.

### MQTT
- **Additional commands not documented**
  - Audio MQTT handler supports `mute-toggle` and `switch-device` in addition to the documented playback/volume commands (see `services/audio-service/src/audio_service/core/mqtt_handler.py`).

## RFID Service (`rfid-service`)

### MQTT
- **Reload-config is not implemented**
  - RFID MQTT client subscribes only to `cmd/set-mode` and `config/general` (see `services/rfid-service/src/rfid_service/infrastructure/mqtt_client.py`).
  - Docs mention `cmd/reload-config` as optional.

## Button Service (`button-service`)

### MQTT (action topic mapping and actions list)
- **Action topic set differs from docs**
  - Code supports actions: `play_pause`, `next`, `prev`, `volume_up`, `volume_down`, `mute_toggle` (and `mute` alias), `sleep_timer_toggle`, `repeat_cycle`, `shuffle_toggle`, `next_output_device` (see `services/backend-service/src/backend_service/core/handlers/button_handler.py` and `services/backend-service/src/backend_service/api/routes_config.py`).
  - Button MQTT publishes action topics by hyphenating action names (e.g. `mute_toggle` -> `mute-toggle`) (see `services/button-service/src/button_service/infrastructure/mqtt_client.py`).
- **Raw event payload fields differ**
  - Backend WS event `button_raw_event.data` uses `{button_id, name, event_type, timestamp}` (see `button_handler.py`).
  - Docs include an outdated `source` field.

## LED Service (`led-service`)

### MQTT / logical states
- **Logical state catalog is incomplete**
  - LED state derivation rules include: `rfid_removed`, `rfid_tag_blocked`, `system_online`, `system_booting`, `usage_denied`, `backend_unreachable` (see `services/led-service/src/led_service/core/state_manager.py`).
  - Docs currently list only a subset.
- **Config schema differs**
  - `config/leds.json` contains `enabled` per LED; docs omit it (see `services/led-service/src/led_service/config_schema.py`).

## Display Service (`display-service`)

### Config / element types
- **Element types list is incomplete**
  - Code supports display elements: `repeat`, `shuffle`, `bluetooth` in addition to `volume`, `sleep_timer`, `mute`, `play_state`, `clock`, `error_state` (see `services/display-service/src/display_service/config_schema.py` and `config/display.json`).
  - Docs omit these extra element types.

### Backend polling
- **Session polling for repeat/shuffle is implemented**
  - Display main polls `GET /api/v1/audio/session` and updates repeat/shuffle UI (see `services/display-service/src/display_service/main.py`).
  - Docs currently mention only the sleep-timer poll loop.

## WebUI (`webui-service`)

### WebSocket events used by the frontend
- WebUI subscribes to WS events `audio_status` and `rfid_scanned_learning`, and uses `button_raw_event` in the ButtonConfigPanel (see `services/webui-service/src/hooks/useAudioStatus.ts`, `pages/RfidPage.tsx`, `components/admin/ButtonConfigPanel.tsx`).
- Docs currently describe additional events (`service_status`, command handling via WS) which are not wired in the current frontend.

