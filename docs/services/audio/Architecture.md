# Audio Service – Architecture

## 1. Purpose & Responsibility

The audio service is the only component in Minabox that actually produces
sound. It receives playback commands over MQTT, executes them locally on the
Raspberry Pi through libVLC, and reports what it is doing back over MQTT so
Backend, WebUI, LED and display services can follow along.

Goals:

- Robust playback of local files and HTTP/HTTPS streams through libVLC.
- Output on a PulseAudio/PipeWire sink of the host, selectable at runtime
  (built-in speaker, Bluetooth headset, USB card).
- Volume management with child protection (`min_volume` / `max_volume`).
- A single, clear status interface for every other service.
- Resume support: the last position survives a service restart.

Out of scope: no playlist, shuffle or tag logic (that lives entirely in the
backend service), no database, no direct WebUI interaction, no equalizer/DSP,
no multi-room sync.

The runtime is **PulseAudio/PipeWire only**. The legacy ALSA path was removed;
`OutputDeviceType` still carries `auto`, `alsa` and `default` purely as
compatibility values so that older `audio.json` files can be migrated on load.

---

## 2. File & Folder Structure

Relevant path: `services/audio-service/src/audio_service/`

```text
audio_service/
├── __init__.py              # Package init, re-exports ConfigManager, config schema, exceptions
├── main.py                  # Entry point: config, logging, service runner, uvicorn, graceful shutdown
├── config.py                # Loads environment variables + config/audio.json into AppConfig
├── config_schema.py         # Pydantic schemas: AudioConfig, EnvConfig, AppConfig, OutputDeviceType
├── config_manager.py        # JSON config with hot-reload and legacy-value migration on load
├── exceptions.py            # Service-specific exception hierarchy
├── core/
│   ├── __init__.py
│   ├── service.py           # Orchestration: command handlers, status loop, device switching, config reload
│   ├── state_manager.py     # Playback state persistence (state/audio_state.json), atomic writes
│   └── mqtt_handler.py      # Topic → command routing, payload validation, log-level handling
├── infrastructure/
│   ├── __init__.py
│   ├── vlc_backend.py       # libVLC playback engine, pipeline prewarm, Pulse sink selection
│   ├── audio_backend.py     # Abstract AudioBackend interface (ABC) + AudioStatus / PlaybackState
│   ├── pulse_detector.py    # Pulse/PipeWire sink detection via `pactl list sinks`, with TTL cache
│   └── mqtt_client.py       # Thin subclass of the shared MQTT base client
├── api/
│   ├── __init__.py
│   └── routes.py            # FastAPI: /health, /api/v1/status, /devices, /switch-device, /test-tone
└── models/
    ├── __init__.py
    └── schemas.py           # Pydantic request/response models for the REST API
```

Tests live in `services/audio-service/tests/` and cover the Pulse sink detector
(parsing plus cache behaviour), the state manager (atomic writes, corrupt-file
recovery) and the go-live hardening (startup volume selection, status after
stop, volume clamping, the last will). The VLC backend itself is only covered
where it can run without libVLC.

Connection handling, reconnect backoff, subscription replay and status replay
are **not** implemented here — they come from `shared_lib.mqtt.BaseMQTTClient`.
`mqtt_client.py` only adds the decode-and-forward hook and the topic helper.

---

## 3. Public Interfaces

### 3.1 MQTT

Topic scheme: `minabox/<device-id>/<domain>/<action>`, built centrally by
`AppConfig.get_mqtt_topic()`. All publishes use QoS 1.

#### Published by the audio service

| Topic | Retained | When |
|---|---|---|
| `audio/status` | yes | Every 2 s, but only when the state fingerprint changed; and after every command |
| `audio/error` | no | A command failed |
| `audio/position-report` | no | On pause, stop and shutdown — lets the backend persist the resume position |
| `audio/config/response` | no | Answer to `config/update`, `config/reload` and `config/get` |
| `system/service-started` | no | Once at startup, replayed after a reconnect |
| `system/service-stopped` | no | On graceful shutdown |

`audio/status` payload:

```json
{
  "state": "playing",
  "track_id": "track_123",
  "source_type": "file",
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "position_ms": 12345,
  "duration_ms": 240000,
  "volume": 25,
  "min_volume": 0,
  "max_volume": 40,
  "volume_step": 5,
  "muted": false,
  "multiple_output_devices": true,
  "bluetooth_sink_available": true,
  "timestamp": "2026-08-23T21:20:00+00:00"
}
```

- `state`: `playing` | `paused` | `stopped` | `error`
- `duration_ms`: `null` for streams and while unknown
- `volume`: the value actually applied, already clamped to the configured bounds
- `min_volume` / `max_volume`: those bounds. They are in the payload because
  `max_volume` is a hard **clamp**, not a scale: on a box configured to 40 this
  message reports `volume: 40` at the stop. A subscriber that shows a percentage
  cannot tell that from halfway up a box configured to 80 without them
- `volume_step`: what one `volume/up` or `volume/down` without a payload is
  worth. The display draws one block per detent and must not guess it
- `position_ms`: a snapshot, not a live value. It is excluded from the
  fingerprint below, so it only reaches subscribers when something else
  changes. Everything that moves it out of band - a seek, a resume, the next
  track - runs through the play command, which publishes unconditionally;
  seeking waits for VLC to confirm the jump first, because `set_time()` is
  asynchronous and the old position would otherwise be the one published
- `multiple_output_devices` / `bluetooth_sink_available`: derived from the sink
  list; the display service uses them to decide whether to show the output
  switcher and the Bluetooth icon

The periodic publish compares a **fingerprint** of `state`, `track_id`,
`source_uri`, `volume`, `muted`, `multiple_output_devices`,
`bluetooth_sink_available` and the volume bounds. `position_ms` and `timestamp`
are deliberately excluded, so a playing track does not push a message every two
seconds. The bounds are in there even though they rarely change: without them a
new `max_volume` would not reach a subscriber until the next track, and every
display of a percentage would keep using the old range in the meantime. The
status is published with `remember=True`, which makes the shared MQTT client
replay it after a reconnect — otherwise a broker restart would leave the
service connected but silent.

The same topic carries a **last will**, registered before the first connect: a
retained payload with `state: "stopped"` and no track. If the process dies
without a clean disconnect — SIGKILL, OOM, power loss — the broker publishes it
on the service's behalf. Without it the retained `playing` would outlive the
service, and the LED ring, the OLED and the WebUI would all keep showing
playback that stopped long ago. MQTT fixes the payload when the session opens,
so its `timestamp` is the connection time; consumers must read `state`, never
the age of the message.

`audio/error` payload:

```json
{
  "error_code": "playback_error",
  "message": "Playback failed: Audio file not found: /mnt/audio/x.mp3",
  "timestamp": "2026-08-23T21:21:00+00:00"
}
```

Error codes actually emitted: `playback_error`, `volume_error`,
`switch_device_error`.

`audio/position-report` payload (skipped for streams and for `position_ms <= 0`):

```json
{
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "source_type": "file",
  "position_ms": 12345,
  "duration_ms": 240000
}
```

#### Subscribed by the audio service

| Topic | Payload | Effect |
|---|---|---|
| `audio/play` | `{track_id, source_type, source_uri, start_position_ms?}` | Load and play; an empty payload means resume |
| `audio/pause` | – | Report position, then pause |
| `audio/stop` | – | Report position, stop, clear persisted state |
| `audio/next` | – | Subscribed, **not implemented** — logs a warning |
| `audio/prev` | – | Subscribed, **not implemented** — logs a warning |
| `audio/set-volume` | `{volume}` | Set volume, clamped to `[min_volume, max_volume]` |
| `audio/volume-up` | `{step?}` (default 5) | Raise volume |
| `audio/volume-down` | `{step?}` (default 5) | Lower volume |
| `audio/mute-toggle` | – | Mute (remember previous volume) / unmute |
| `audio/switch-device` | `{sink_name?, alsa_device?, direction?}` | Switch output sink |
| `audio/config/update` | full `audio.json` | Validate and write the config file |
| `audio/config/reload` | – | Re-read the file, re-init VLC if the device changed |
| `audio/config/get` | – | Publish the current config on `audio/config/response` |
| `config/general` | `{log_level}` | Apply the log level at runtime (note: not under `audio/`) |

`play` with a payload starts a new track. `play` with an empty payload resumes:
if VLC is paused it resumes in place, otherwise the persisted state is replayed
from `last_source_uri` at `last_position_ms`.

### 3.2 REST

Served by uvicorn on `AUDIO_SERVICE_PORT` (default 8003). Health sits at the
root, everything else under `/api/v1`. There is no authentication, so the port
is published on the loopback interface only (`127.0.0.1:8003`): the backend
reaches the service over the Compose network as `http://audio:8003`, while
`switch-device` and `test-tone` stay out of reach from the WLAN.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness and dependency state |
| `GET` | `/api/v1/status` | Current `AudioStatus` plus a timestamp |
| `GET` | `/api/v1/devices?enabled_only=false` | Detected Pulse sinks, cache bypassed |
| `POST` | `/api/v1/switch-device` | Switch the output sink, returns the new status |
| `POST` | `/api/v1/test-tone` | Play the bundled test tone on a sink |

`GET /health`:

```json
{
  "status": "healthy",
  "service": "audio",
  "version": "0.1.1",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "timestamp": "2026-08-23T20:45:00+00:00"
}
```

`status` is `healthy` when MQTT is connected **and** VLC is initialised,
otherwise `degraded`. The endpoint answers HTTP 200 in both cases, so a broker
outage does not make Docker restart a service that is otherwise fine.

`POST /api/v1/switch-device` takes `{"sink_name": "..."}` or
`{"direction": "next"}`; `alsa_device` is a deprecated alias for `sink_name`.
An unknown or non-enabled sink is answered with HTTP 400.

`POST /api/v1/test-tone` takes an optional `{"sink_name": "..."}` and plays
`assets/test-tone.wav` through `paplay`. It deliberately bypasses the VLC
backend: the setup wizard has to be able to check a speaker while music is
playing, and taking over the player would stop the music. Unknown sinks are
rejected with HTTP 404, because `paplay` would otherwise fall back to the
default output silently and report success — which in the wizard would mean the
user selects output A, hears output B and believes A is verified.

---

## 4. Core Functions

### 4.1 Playback

`play` is serialised by an `asyncio.Lock`, and a play that is still running is
cancelled when a new one arrives. Without that, rapid button presses used to
corrupt the VLC pipeline and produce the "LED on, no sound" symptom.

Before VLC is handed the media, the backend checks how long the audio pipeline
has been idle. PipeWire/PulseAudio suspend the ALSA sink after a few seconds of
silence, and reopening the hardware buffers costs 100–300 ms — audible as a
stutter at the beginning of a track. If more than four seconds have passed
since the last `stop()`, 300 ms of silence is written through `pacat` first, so
VLC starts on a warm sink. Consecutive tracks take the fast path.

Pause and resume also work around libVLC behaviour: `pause()` is asynchronous
and takes about a second, so the backend waits for `State.Paused` before
returning. On resume, VLC may already have discarded its audio buffer; the
backend detects that through a position jump larger than 100 ms after the
toggle and falls back to reloading the media and seeking to the saved position.

### 4.2 Volume and child protection

`AudioConfig` holds `min_volume`, `max_volume` and `default_volume`, and the
model validator keeps them consistent (`min < max`, `default` inside the range).
`VLCBackend.set_volume()` clamps every requested value into
`[min_volume, max_volume]`, so no MQTT command and no API call can exceed the
limit set by the parents.

Lowering `max_volume` while something is playing is handled explicitly: a
config reload calls `_enforce_volume_limits()`, which pulls the running volume
back into the allowed range. Just swapping the config would leave the current
volume above the new limit until the next `set_volume`, and the WebUI slider
would sit outside its own scale.

Mute goes through libVLC's own mute, not through the volume. Setting the
volume to 0 would run into the same clamp and stop at `min_volume`: on a box
with `min_volume = 15`, pressing the volume knob merely turned the music down
to 15 while the status already reported `muted: true`. Because the volume is
never touched, unmuting has nothing to restore.

The mute flag lives in the service, not in the player, and is reapplied after
a re-initialisation — a fresh player starts unmuted, so switching output while
muted would otherwise bring the sound back unasked. It is not persisted across
restarts: a box that reboots comes back audible.

### 4.3 Output device selection

`PulseSinkDetector` runs `pactl list sinks` and parses each block's `Name`,
`Description` and, from `Properties`, `node.nick` and `alsa.card_name`. The
display name prefers `node.nick`, then `alsa.card_name`, then `Description` —
that is what makes a WM8960 HAT show up under its real name instead of a
generic "Built-in Audio".

`pactl` is expensive on a Raspberry Pi and the status loop asks every two
seconds, so results are cached for `CACHE_TTL_SECONDS` (10 s). The cache is
bypassed for explicit user-facing queries (`GET /api/v1/devices`,
`POST /api/v1/test-tone`) and invalidated on every device switch and
re-initialisation. The TTL is also the ceiling on how stale the Bluetooth icon
on the OLED can be; the exact fix would be event-driven invalidation when a
Bluetooth device connects, which needs the host-helper to reach this service.

`enabled_output_devices` restricts which sinks are offered; an empty list means
all of them. `device_display_names` maps a sink name to a user-facing label.
When two sinks would end up with the same label, the sink name is appended in
brackets to keep them distinguishable.

Switching writes the new sink into the config, invalidates the detector cache,
shuts VLC down, re-initialises it, and — if a track was playing or paused —
resumes it at the position captured just before the restart.

### 4.4 Configuration and hot reload

`config/audio.json` is the single source of truth at runtime. `ConfigManager`
extends the shared `JsonConfigManager` and migrates legacy values while
loading: `output_device_type` of `alsa`, `auto`, `default` or empty becomes
`pulseaudio`, and `output_device_name` of `auto` or `default` becomes an empty
string, which means "host default sink". A migrated file is written back.

`config/update` validates and persists. `config/reload` re-reads the file and
decides whether the output device changed; only then is VLC restarted,
otherwise the new config is handed to the backend in place. Invalid config
leaves the previous one active and answers with `success: false`.

### 4.5 State persistence and resume

`state/audio_state.json` holds `last_track_id`, `last_source_type`,
`last_source_uri`, `last_position_ms`, `last_state` and `last_volume`. It is
written on volume changes, pause, stop and shutdown.

The box is meant to survive having its plug pulled, so the file is written to a
temporary file in the same directory, `fsync`ed, and moved into place with
`os.replace()`. A reader therefore only ever sees a complete file; a corrupt
file falls back to defaults instead of taking the service down.

`last_volume` is `0` when nothing has been remembered yet. That zero is what
tells the service to fall back to `default_volume` on a box that has never
played anything — a non-zero default here would read as a remembered volume,
and a freshly set up box would start at `max_volume` instead.

There is no automatic resume on startup. The service restores the last volume,
but waits for a `play` command before producing sound.

### 4.6 Startup and shutdown

Startup loads the state, initialises VLC, applies the initial volume (the
remembered one if there is one, otherwise `default_volume`, both clamped into
`[min_volume, max_volume]`), starts the status loop, and only then connects to
MQTT — in the background, retrying forever. Startup does not depend on the
broker being reachable; that dependency is what used to take the service down
when the broker restarted.

Shutdown, triggered by SIGTERM or SIGINT, cancels a running playback task and
the status loop, stops the MQTT client, reports the current position **before**
stopping VLC (so the position is still accurate), saves the state, announces
`service-stopped`, and releases the VLC instance.

---

## 5. Dependencies

### Hardware / OS

Raspberry Pi (3/4/5) with a working PulseAudio or PipeWire server on the host.
The container gets access through the host's Pulse socket, mounted read-only,
with `PULSE_SERVER` pointing at it. `/dev/snd` is deliberately **not** mapped —
the container never talks to ALSA directly.

Tested outputs: WM8960 Audio HAT, HiFiBerry, IQaudio, USB sound cards, the
3.5 mm jack, HDMI, and Bluetooth sinks (`bluez_output.*`).

### System packages

- `libvlc5`, `vlc-plugin-base`, `vlc-plugin-access-extra` — playback engine,
  codecs and the HTTP/HTTPS access modules
- `pulseaudio-utils` — `pactl` (sink discovery), `pacat` (pipeline prewarm),
  `paplay` (test tone)
- `curl` — container health check

Explicitly **not** the `vlc` package: that is the desktop player and pulls in
`vlc-plugin-qt`, which drags Qt5 and the whole Mesa stack — libLLVM, libgallium,
libz3 — into the image. None of it is reachable from a headless service, and
together it was roughly 400 MB, more than half the image. No ALSA tooling
either, since `/dev/snd` is not mapped.

### Python

`requirements.txt` holds the pinned versions. In use: `python-vlc`, `fastapi`,
`uvicorn[standard]`, `aiomqtt`, `pydantic`, `structlog`, plus `minabox-shared`
from `services/shared-lib`.

### Services

- MQTT broker (Mosquitto) — every command and every status report
- Backend service — sends the commands and consumes `position-report`;
  the audio service is started after the backend is healthy

### Configuration

Environment (`.env` and `docker-compose.yml`):

| Variable | Default | Meaning |
|---|---|---|
| `MQTT_BROKER`, `MQTT_PORT` | – | Broker address, required |
| `MINABOX_DEVICE_ID` | – | First segment of every topic, required |
| `LOG_LEVEL` | – | Initial log level, overridable at runtime via `config/general` |
| `AUDIO_SERVICE_HOST` | `0.0.0.0` | FastAPI bind address |
| `AUDIO_SERVICE_PORT` | `8003` | FastAPI port |
| `AUDIO_CONFIG_PATH` | `config/audio.json` | Config file |
| `AUDIO_STATE_PATH` | `state/audio_state.json` | State file |
| `AUDIO_TEST_TONE_PATH` | `/app/assets/test-tone.wav` | Test tone asset |
| `PULSE_SERVER` | – | Host Pulse socket; without it no sink discovery, no prewarm, no test tone |

`config/audio.json`:

```json
{
  "output_device_type": "pulseaudio",
  "output_device_name": "alsa_output.platform-soc_sound.stereo-fallback",
  "enabled_output_devices": [
    "alsa_output.platform-soc_sound.stereo-fallback",
    "bluez_output.00_09_A7_54_68_E0.1"
  ],
  "device_display_names": {
    "alsa_output.platform-soc_sound.stereo-fallback": "Lautsprecher",
    "bluez_output.00_09_A7_54_68_E0.1": "Headset"
  },
  "min_volume": 15,
  "max_volume": 35,
  "default_volume": 25
}
```

| Field | Default | Meaning |
|---|---|---|
| `output_device_type` | `pulseaudio` | Kept for migration; the runtime always uses `pulseaudio` |
| `output_device_name` | `""` | Pulse sink name; empty means the host default sink |
| `enabled_output_devices` | `[]` | Allow-list for the device selector; empty means all |
| `device_display_names` | `{}` | Sink name → label shown in the WebUI |
| `min_volume` | `5` | Lower bound, prevents accidental silence |
| `max_volume` | `70` | Upper bound, child protection |
| `default_volume` | `40` | Volume at startup when no state was persisted |

---

## 6. Errors & Status

### 6.1 Health states

| State | Condition |
|---|---|
| `healthy` | MQTT connected and VLC initialised |
| `degraded` | Either of those is missing — the broker is away or VLC failed to start |

`GET /health` answers 200 in both cases; the difference is in the `status`
field, which the backend surfaces in the system overview.

### 6.2 Error handling

Every command handler catches its exceptions, logs them structured, and — for
playback, volume and device switching — publishes on `audio/error`. A failing
command never takes the service down.

`VLCBackend.play()` wraps every failure into `PlaybackError`, including the
missing-file case, so the outside world always sees `error_code:
playback_error` with the original message in `message`.

The status loop, the shutdown path and the device probing inside the status
publish each swallow their own errors: a sink list that cannot be read must not
stop the status from being published, and a failing shutdown step must not
prevent the remaining steps from running.

Config errors leave the previous configuration active. A missing config file is
created with defaults; a corrupt state file falls back to defaults.

### 6.3 Logging

structlog, JSON at `INFO`, console at `DEBUG`, configured through
`shared_lib.logging.setup_structlog`. The level can be changed at runtime by
publishing `{"log_level": "DEBUG"}` on `minabox/<device-id>/config/general`.

Event names are stable identifiers, not sentences — `audio_service_started`,
`pipeline_cold_prewarming`, `play_interrupted_cancelling_previous`,
`volume_clamped_to_limits`, `resume_buffer_lost_replaying`,
`position_report_published`, `pulse_sinks_detected`, `state_saved`.
