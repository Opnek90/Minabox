# Audio Service

VLC-based audio playback service for Minabox. It is controlled via MQTT and exposes a small REST API used by the Backend and WebUI (status, device selection, output switching).

For the full interface/flow details (REST endpoints, MQTT topics, payload shapes, and state transitions), see [`docs/services/audio/Architecture.md`](../../docs/services/audio/Architecture.md).

## REST API

Endpoints (mounted at the service root):
- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/devices?enabled_only=false`
- `POST /api/v1/switch-device` (body: `sink_name` or `alsa_device`, and optional `direction`)

## MQTT Topics

Topic prefix pattern:
- `minabox/<device-id>/...`

Commands (subscribe):
- `minabox/<device-id>/audio/play`
- `minabox/<device-id>/audio/pause`
- `minabox/<device-id>/audio/stop`
- `minabox/<device-id>/audio/next`
- `minabox/<device-id>/audio/prev`
- `minabox/<device-id>/audio/set-volume` (body: `{ "volume": number }`)
- `minabox/<device-id>/audio/volume-up` (body: optional `{ "step": number }`)
- `minabox/<device-id>/audio/volume-down` (body: optional `{ "step": number }`)
- `minabox/<device-id>/audio/mute-toggle`
- `minabox/<device-id>/audio/switch-device` (body: `{ "sink_name"?: string, "alsa_device"?: string, "direction"?: "next" }`)

Configuration (subscribe):
- `minabox/<device-id>/audio/config/update` (body: full `config/audio.json`)
- `minabox/<device-id>/audio/config/reload` (body: empty `{}` payload)
- `minabox/<device-id>/audio/config/get` (body: empty `{}` payload; publishes to `audio/config/response`)

General config (subscribe for runtime log level):
- `minabox/<device-id>/config/general` (MQTT payload includes `log_level`)

Status (publish):
- `minabox/<device-id>/audio/status` (includes audio state + metadata; used by Backend WS `audio_status` and by WebUI)
- `minabox/<device-id>/audio/error`
- `minabox/<device-id>/audio/position-report` (published by Backend on stop/pause for resume tracking)
- `minabox/<device-id>/audio/config/response` (response to `config/get`)

## Configuration

Main config file: `config/audio.json`

Key fields (subset):
- `output_device_type`: `"pulseaudio"` (legacy `alsa/auto/default` are migrated)
- `output_device_name`: Pulse/PipeWire sink name (empty string = host default sink)
- `enabled_output_devices`: optional allow-list of sink names
- `min_volume`, `max_volume`, `default_volume`: volume bounds and startup volume

