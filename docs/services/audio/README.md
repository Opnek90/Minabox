# Audio Service

The audio service is the only component in Minabox that actually produces
sound. It receives playback commands over MQTT, executes them locally through
libVLC, and reports what it is doing back over MQTT so backend, WebUI, LED and
display can follow along.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-audio` |
| Source | `services/audio-service/src/audio_service/` |
| Version | `services/audio-service/VERSION` |
| Compose service | `audio` (no profile — always on) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn, libVLC |
| Speaks | MQTT; REST on `8003` (host `127.0.0.1:8003`) |
| Needs | MQTT broker, the host's PulseAudio/PipeWire socket, `/mnt/audio` read-only, `/announcements` read-only |

## 1. Purpose & Responsibility

- Robust playback of local files and HTTP/HTTPS streams through libVLC.
- Output on a PulseAudio/PipeWire sink of the host, selectable at runtime
  (built-in speaker, Bluetooth headset, USB card).
- Volume management with child protection (`min_volume` / `max_volume`).
- One clear status interface for every other service.
- Resume support: the last position survives a service restart.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Playlists, shuffle, repeat, tag logic | backend |
| Deciding which track comes next | backend — `audio/next` and `audio/prev` are subscribed but not implemented |
| Any database | backend |
| Talking to the WebUI directly | backend |
| Equalizer, DSP, multi-room sync | not supported |
| ALSA | nothing — `/dev/snd` is deliberately not mapped |

The runtime is **PulseAudio/PipeWire only**. The legacy ALSA path was removed;
`OutputDeviceType` still carries `auto`, `alsa` and `default` purely as
compatibility values so older `audio.json` files can be migrated on load.

## 2. File & Folder Structure

```
services/audio-service/
├── Dockerfile                  libvlc5 + plugins, pulseaudio-utils; not the `vlc` package (see 6)
├── assets/test-tone.wav        the tone POST /api/v1/test-tone plays
├── config/audio.json           runtime configuration (see 5.2)
├── state/audio_state.json      persisted playback state (see 3.5)
├── VERSION                     service version, single source
├── src/audio_service/
│   ├── main.py                 entry point: config, logging, runner, uvicorn, shutdown
│   ├── config.py               environment + audio.json → AppConfig
│   ├── config_schema.py        AudioConfig, EnvConfig, OutputDeviceType, the volume validator
│   ├── config_manager.py       JSON config with hot reload and legacy-value migration
│   ├── exceptions.py           service-specific exception hierarchy
│   ├── core/
│   │   ├── service.py          ** the orchestration ** (961 lines) — command handlers,
│   │   │                       status loop, device switching, config reload
│   │   ├── troubleshoot.py     steps 2–6 of the sound-repair chain
│   │   ├── state_manager.py    playback state persistence, atomic writes
│   │   └── mqtt_handler.py     topic → command routing and payload validation
│   ├── infrastructure/
│   │   ├── vlc_backend.py      ** the playback engine ** (708 lines) — libVLC,
│   │   │                       pipeline prewarm, sink selection, the volume clamp
│   │   ├── audio_backend.py    the AudioBackend ABC + AudioStatus / PlaybackState
│   │   ├── pulse_detector.py   `pactl list sinks` parsing with a TTL cache
│   │   └── mqtt_client.py      thin subclass of the shared MQTT base client
│   ├── api/routes.py           /health, /api/v1/status, /devices, /switch-device,
│   │                           /test-tone, /troubleshoot
│   └── models/schemas.py       request/response models for the REST API
└── tests/                      see section 8
```

Connection handling, reconnect backoff, subscription replay and status replay
are **not** implemented here — they come from `shared_lib.mqtt.BaseMQTTClient`.
`mqtt_client.py` only adds the decode-and-forward hook and the topic helper.

## 3. Runtime Flow

### 3.1 Playback

`play` is serialised by an `asyncio.Lock`, and a play that is still running is
cancelled when a new one arrives. Without that, rapid button presses used to
corrupt the VLC pipeline and produce the "LED on, no sound" symptom.

Before VLC is handed the media, the service checks how long the audio pipeline
has been idle. PipeWire/PulseAudio suspend the ALSA sink after a few seconds of
silence, and reopening the hardware buffers costs 100–300 ms — audible as a
stutter at the start of a track. If more than four seconds have passed since
the last `stop()`, 300 ms of silence is written through `pacat` first, so VLC
starts on a warm sink. Consecutive tracks take the fast path.

Pause and resume work around libVLC behaviour too: `pause()` is asynchronous
and takes about a second, so the service waits for `State.Paused` before
returning. On resume VLC may already have discarded its audio buffer; that is
detected through a position jump larger than 100 ms after the toggle, and the
media is reloaded and seeked to the saved position.

`play` with a payload starts a new track. `play` with an empty payload resumes:
if VLC is paused it resumes in place, otherwise the persisted state is replayed
from `last_source_uri` at `last_position_ms`.

### 3.2 Volume and child protection

`AudioConfig` holds `min_volume`, `max_volume` and `default_volume`, and the
model validator keeps them consistent (`min < max`, `default` inside the
range). `VLCBackend.set_volume()` clamps **every** requested value into
`[min_volume, max_volume]`, so no MQTT command and no API call can exceed the
limit set by the parents.

Lowering `max_volume` while something plays is handled explicitly: a config
reload calls `_enforce_volume_limits()`, which pulls the running volume back
into range. Just swapping the config would leave the volume above the new limit
until the next `set_volume`, and the WebUI slider would sit outside its own
scale.

**Mute goes through libVLC's own mute, not through the volume.** Setting the
volume to 0 would hit the same clamp and stop at `min_volume`: on a box with
`min_volume = 15`, pressing the volume knob merely turned the music down to 15
while the status already reported `muted: true`. Because the volume is never
touched, unmuting has nothing to restore.

The mute flag lives in the service, not in the player, and is reapplied after a
re-initialisation — a fresh player starts unmuted, so switching output while
muted would otherwise bring the sound back unasked. It is not persisted across
restarts: a box that reboots comes back audible.

### 3.3 Output device selection

`PulseSinkDetector` runs `pactl list sinks` and parses each block's `Name`,
`Description` and, from `Properties`, `node.nick` and `alsa.card_name`. The
display name prefers `node.nick`, then `alsa.card_name`, then `Description` —
that is what makes a WM8960 HAT show up under its real name instead of a
generic "Built-in Audio".

`pactl` is expensive on a Raspberry Pi and the status loop asks every two
seconds, so results are cached for `CACHE_TTL_SECONDS` (10 s). The cache is
bypassed for explicit user-facing queries (`GET /api/v1/devices`,
`POST /api/v1/test-tone`) and invalidated on every device switch and
re-initialisation. That TTL is also the ceiling on how stale the Bluetooth icon
on the OLED can be; the exact fix would be event-driven invalidation when a
Bluetooth device connects, which needs the host-helper to reach this service.

`enabled_output_devices` restricts which sinks are offered; an empty list means
all. `device_display_names` maps a sink name to a user-facing label; when two
sinks would end up with the same label, the sink name is appended in brackets.

Switching writes the new sink into the config, invalidates the detector cache,
shuts VLC down, re-initialises it, and — if a track was playing or paused —
resumes it at the position captured just before the restart.

### 3.4 Configuration reload

`config/update` validates and persists. `config/reload` re-reads the file and
decides whether the output device changed; only then is VLC restarted,
otherwise the new config is handed to the backend in place. Invalid config
leaves the previous one active and answers `success: false`.

`ConfigManager` migrates legacy values while loading: `output_device_type` of
`alsa`, `auto`, `default` or empty becomes `pulseaudio`, and
`output_device_name` of `auto` or `default` becomes an empty string ("host
default sink"). A migrated file is written back.

### 3.5 State persistence and resume

`state/audio_state.json` holds `last_track_id`, `last_source_type`,
`last_source_uri`, `last_position_ms`, `last_state` and `last_volume`, written
on volume changes, pause, stop and shutdown.

The box is meant to survive having its plug pulled, so the file is written to a
temporary file in the same directory, `fsync`ed, and moved into place with
`os.replace()`. A reader therefore only ever sees a complete file; a corrupt
file falls back to defaults instead of taking the service down.

`last_volume` is `0` when nothing has been remembered yet. That zero is what
tells the service to fall back to `default_volume` on a box that has never
played anything — a non-zero default here would read as a remembered volume,
and a freshly set up box would start at `max_volume`.

There is **no automatic resume on startup**. The service restores the last
volume but waits for a `play` command before producing sound.

### 3.6 Startup and shutdown

Startup loads the state, initialises VLC, applies the initial volume (the
remembered one if there is one, otherwise `default_volume`, both clamped),
starts the status loop, and only then connects to MQTT — in the background,
retrying forever. Startup does not depend on the broker being reachable; that
dependency is what used to take the service down when the broker restarted.

Shutdown on SIGTERM/SIGINT cancels a running playback task and the status loop,
stops the MQTT client, reports the current position **before** stopping VLC (so
the position is still accurate), saves the state, announces `service-stopped`,
and releases the VLC instance.

## 4. Public Interfaces

Topic scheme `minabox/<device-id>/<domain>/<action>`, built centrally by
`AppConfig.get_mqtt_topic()`. All publishes use QoS 1.

### 4.1 MQTT — published

| Topic | Retained | When |
| --- | --- | --- |
| `audio/status` | **yes** | every 2 s, but only when the state fingerprint changed; and after every command |
| `audio/error` | no | a command failed |
| `audio/position-report` | no | on pause, stop and shutdown — lets the backend persist the resume position |
| `audio/config/response` | no | answer to `config/update`, `config/reload`, `config/get` |
| `system/service-started` | no | once at startup, replayed after a reconnect |
| `system/service-stopped` | no | on graceful shutdown |

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
- `volume`: the value actually applied, already clamped. libVLC has two ways of
  saying "ask me later" and neither is a level: **-1** with no player or after
  `stop()` released the media, and **0** in the moment after `play()` while the
  audio output is still coming up. The service reports the last level it set
  instead. Passing them on cost a spurious volume change at each end of a track
  — a drop to the minimum when a figure was lifted off the reader, and a dip to
  zero and back when one was put on. What makes the second case decidable is
  that every write goes through the clamp, so the box cannot be at a level
  outside the configured range.
- `min_volume` / `max_volume`: those bounds. They are in the payload because
  `max_volume` is a hard **clamp**, not a scale: on a box configured to 40 this
  message reports `volume: 40` at the top. A subscriber showing a percentage
  cannot tell that from halfway up a box configured to 80 without them.
- `volume_step`: what one `volume-up`/`volume-down` without a payload is worth.
  The display draws one block per detent and must not guess it.
- `position_ms`: a snapshot, not a live value. It is excluded from the
  fingerprint below, so it only reaches subscribers when something else
  changes. Everything that moves it out of band — a seek, a resume, the next
  track — runs through the play command, which publishes unconditionally;
  seeking waits for VLC to confirm the jump first, because `set_time()` is
  asynchronous and the old position would otherwise be the one published.
- `multiple_output_devices` / `bluetooth_sink_available`: derived from the sink
  list; the display uses them to decide whether to show the output switcher and
  the Bluetooth icon.

**The fingerprint.** The periodic publish compares `state`, `track_id`,
`source_uri`, `volume`, `muted`, `multiple_output_devices`,
`bluetooth_sink_available` and the volume bounds. `position_ms` and `timestamp`
are deliberately excluded, so a playing track does not push a message every two
seconds. The bounds are in there even though they rarely change: without them a
new `max_volume` would not reach a subscriber until the next track. The status
is published with `remember=True`, so the shared client replays it after a
reconnect — otherwise a broker restart would leave the service connected but
silent.

**The last will.** The same topic carries a will, registered before the first
connect: a retained payload with `state: "stopped"` and no track. If the
process dies without a clean disconnect — SIGKILL, OOM, power loss — the broker
publishes it on the service's behalf. Without it the retained `playing` would
outlive the service, and the LED ring, the OLED and the WebUI would all keep
showing playback that stopped long ago. MQTT fixes the payload when the session
opens, so its `timestamp` is the connection time; consumers must read `state`,
never the age of the message.

`audio/error`:

```json
{
  "error_code": "playback_error",
  "message": "Playback failed: Audio file not found: /mnt/audio/x.mp3",
  "timestamp": "2026-08-23T21:21:00+00:00"
}
```

Error codes actually emitted: `playback_error`, `volume_error`,
`switch_device_error`.

`audio/position-report` (skipped for streams and for `position_ms <= 0`):

```json
{
  "source_uri": "/mnt/audio/album1/01-track.mp3",
  "source_type": "file",
  "position_ms": 12345,
  "duration_ms": 240000
}
```

### 4.2 MQTT — subscribed

| Topic | Payload | Effect |
| --- | --- | --- |
| `audio/play` | `{track_id, source_type, source_uri, start_position_ms?}` | load and play; an empty payload means resume |
| `audio/pause` | – | report position, then pause |
| `audio/stop` | – | report position, stop, clear persisted state |
| `audio/next` | – | subscribed, **not implemented** — logs a warning |
| `audio/prev` | – | subscribed, **not implemented** — logs a warning |
| `audio/set-volume` | `{volume}` | set volume, clamped to `[min_volume, max_volume]` |
| `audio/volume-up` | `{step?}` (default 5) | raise volume |
| `audio/volume-down` | `{step?}` (default 5) | lower volume |
| `audio/mute-toggle` | – | mute / unmute |
| `audio/announce` | `{source_uri, duck_percent?, volume_percent?}` | duck the music, play one spoken clip over it, put the level back (see 4.4) |
| `audio/switch-device` | `{sink_name?, alsa_device?, direction?}` | switch output sink |
| `audio/config/update` | full `audio.json` | validate and write the config file |
| `audio/config/reload` | – | re-read the file, re-init VLC if the device changed |
| `audio/config/get` | – | publish the current config on `audio/config/response` |
| `config/general` | `{log_level}` | apply the log level at runtime (note: **not** under `audio/`) |

### 4.3 REST

Served by uvicorn on `AUDIO_SERVICE_PORT` (default 8003). Health at the root,
everything else under `/api/v1`. There is no authentication, so the port is
published on loopback only: the backend reaches the service over the compose
network as `http://audio:8003`, while `switch-device` and `test-tone` stay out
of reach from the WLAN.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | liveness and dependency state |
| `GET` | `/api/v1/status` | current `AudioStatus` plus a timestamp |
| `GET` | `/api/v1/devices?enabled_only=false` | detected Pulse sinks, cache bypassed |
| `POST` | `/api/v1/switch-device` | switch the output sink, returns the new status |
| `POST` | `/api/v1/test-tone` | play the bundled test tone on a sink |
| `POST` | `/api/v1/troubleshoot` | steps 2–6 of the sound-repair chain, ending with the tone |

```json
{
  "status": "healthy",
  "service": "audio",
  "version": "0.2.4",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "output_device": "alsa_output.platform-soc_sound.stereo-fallback",
  "output_device_available": true,
  "timestamp": "2026-08-23T20:45:00+00:00"
}
```

`status` is `healthy` when MQTT is connected, VLC is initialised **and** the
configured output device actually exists; otherwise `degraded`. The endpoint
answers 200 in all cases, so a broker outage does not make Docker restart a
service that is otherwise fine.

The device check exists because configured is not the same as usable. After a
restart in which the PN532 held the I2C bus, the wm8960 codec failed to probe
once and gave up; `aplay -l` showed only HDMI and the headphone jack, and no
sound came out of the box — while this endpoint reported `healthy`, because the
broker was connected and VLC had come up. A dark display is a blemish; a mute
box is broken.

`output_device` is the configured sink name, or `null` when
`output_device_name` is empty (host default sink — nothing is pinned down, so
nothing can be missing). A sink lookup that *fails* is not reported as a
missing device: not being able to ask is not the same as the answer being no.
The lookup is capped at 2 s, well under the container health check's 5 s — the
detector shells out to `pactl` and gives it 10 s, and without the cap a hung
`pactl` on a cold cache would make `/health` miss the check three times over.

**`POST /api/v1/switch-device`** takes `{"sink_name": "..."}` or
`{"direction": "next"}`; `alsa_device` is a deprecated alias for `sink_name`.
An unknown or non-enabled sink is answered with HTTP 400.

**`POST /api/v1/troubleshoot`** is the chain behind the WebUI's "Fix sound
problem" button. It walks steps 2 to 6 — the sink, the stream, and the
service's own volume and mute — repairs what it can repair safely, and plays
the test tone last. Two rules hold it together:

- **Idempotent.** The dialog offers the button again after a "no, still
  nothing", so a second run must not undo the first one's work.
- **Only what is demonstrably wrong.** A sink is raised when it reads below
  20 %, never because 40 % is not the number one would pick; the service volume
  only when it is below its own configured `min_volume`. A box someone
  deliberately turned down quietly comes out of this exactly as quiet.

The tone comes last because of step 4: a mute WirePlumber remembers for the
media role only appears once a stream has opened the output, and can only be
corrected there. The tone is that stream. A step that fails does not end the
run — the tone is what the user is waiting for, and the steps after a failed
one may well be the ones that fix it.

When the configured sink is gone, the fallback prefers one the user actually
allowed in `enabled_output_devices`. It reaches past that list only when none
of the allowed outputs is present any more, and says so in the step's `detail`:
at that point the alternative is a box that stays silent.
`switch_output_device()` takes `allow_disabled` for this one caller; every
other one is a deliberate user choice and stays inside the list.

Steps 1 (is there a sound card at all?) and 7 (an ALSA mixer at zero) are not
here — `/proc/asound/cards` and `amixer` are not reachable from this container.
They are the host-helper's `POST /audio/repair`, and the backend stitches both
halves together, host first: a mixer at zero has to be raised *before* the tone
plays, or the tone proves nothing.

Every repair is recorded in the response, so the debug export still shows
afterwards what the button actually did. The `detail` field is technical
wording for exactly that; the user is shown a translated sentence keyed on the
step id, never a sink name or a stream index.

**`POST /api/v1/test-tone`** takes an optional `{"sink_name": "..."}` and plays
`assets/test-tone.wav` via `paplay`, tagged `--property=media.role=Music` — the
exact PipeWire role the music player's libVLC instance ends up with
(`--role=music`, translated by PipeWire's ACP layer). A plain `paplay` call
would run under `application.name:paplay`, a *different* stream role with its
own remembered volume and mute, and used to be audible on a box whose *music*
role was remembered as muted while nothing else was.

It is not libVLC any more, though it was until this was measured on a real box:
libVLC's own `pulse` output module repeatedly lost sync against PipeWire's
pulse-compatibility layer mid-stream (`cannot synchronize start`, `write index
corrupt`) and dropped or truncated playback. `paplay` against the identical
role played cleanly every time; full volume is forced (`--volume=65536`) so a
quiet remembered role volume cannot be mistaken for "sound is fine" either. A
separate `paplay` process, not the service's own player, is what keeps the
original promise: the setup wizard has to be able to check a speaker while
music is playing. Unknown sinks are rejected with HTTP 404, because `paplay`
reports no error for them — it falls back to the default output silently, which
in the wizard would mean the user selects output A, hears output B and believes
A is verified.

### 4.4 Spoken announcements

`audio/announce` plays one short clip — a card name, "I do not know this
card", a warning before the listening time is over — over whatever is running.
The backend decides the sentence and has the clip made
([tts service](../tts/README.md)); `source_uri` is a path into the shared clip
volume, mounted read-only here at `/announcements`. Nothing is synthesised in
this service.

**Ducking, not pausing.** A pause would have to be undone at a position, and a
radio stream has none — it would come back at "now", which for a story is the
wrong place and for a live stream is not even defined. Turning the music down
to `duck_percent` of its current level and back up needs no memory of where
anything was, and it is what a person in the room would do. `duck_percent: 100`
switches ducking off; with nothing playing there is no level to touch and none
is written.

**A different media role.** The clip runs through `paplay` as `Notification`,
not `Music` — the test tone's reasoning about a second client applies
unchanged, but the role does not. WirePlumber remembers mute *per role*, and
`Music` is the role this service mutes: on a muted box every announcement would
be swallowed, including "the sound is off", which is the one sentence that
exists for exactly that moment. The configured sink is named explicitly on the
command line, so the different role changes which stream is muted and nothing
about where the phrase comes out.

**The level always comes back.** Restoring runs in a `finally`, including for a
clip that failed or timed out: a phrase that does not come out is a missed
courtesy, while music left at 30 % looks like a broken speaker and becomes a
support case. While a clip is running the periodic status publish is held off,
so the ducked level never reaches the WebUI slider as a value somebody set;
anything that really changes state still publishes.

## 5. Configuration

### 5.1 Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `MQTT_BROKER`, `MQTT_PORT` | – | broker address, required |
| `MINABOX_DEVICE_ID` | – | first segment of every topic, required |
| `LOG_LEVEL` | – | initial log level, overridable via `config/general` |
| `AUDIO_SERVICE_HOST` | `0.0.0.0` | FastAPI bind address |
| `AUDIO_SERVICE_PORT` | `8003` | FastAPI port |
| `AUDIO_CONFIG_PATH` | `config/audio.json` | config file |
| `AUDIO_STATE_PATH` | `state/audio_state.json` | state file |
| `AUDIO_TEST_TONE_PATH` | `/app/assets/test-tone.wav` | test tone asset |
| `PULSE_SERVER` | – | host Pulse socket; without it no sink discovery, no prewarm, no test tone |

Compose additionally sets `XDG_RUNTIME_DIR`,
`PULSE_PROP_module-suspend-on-idle.timeout=0` and `PULSE_PROP_media.role=music`
— the last one reaches only the `pacat` prewarm, not the music: libVLC sets its
own media role, pinned with `--role=music` in `_build_vlc_args()`.

### 5.2 `config/audio.json`

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
| --- | --- | --- |
| `output_device_type` | `pulseaudio` | kept for migration; the runtime always uses `pulseaudio` |
| `output_device_name` | `""` | Pulse sink name; empty means the host default sink |
| `enabled_output_devices` | `[]` | allow-list for the device selector; empty means all |
| `device_display_names` | `{}` | sink name → label shown in the WebUI |
| `min_volume` | `5` | lower bound, prevents accidental silence |
| `max_volume` | `70` | upper bound, child protection |
| `default_volume` | `40` | volume at startup when no state was persisted |

The config directory is bind-mounted read-write — unlike led and display, this
service writes its own file (a device switch persists the new sink).

## 6. Dependencies

**Hardware / OS.** Raspberry Pi (3/4/5) with a working PulseAudio or PipeWire
server on the *host*. The container gets access through the host's Pulse
socket, mounted read-only, with `PULSE_SERVER` pointing at it. `/dev/snd` is
deliberately **not** mapped — the container never talks to ALSA directly.
Tested outputs: WM8960 Audio HAT, HiFiBerry, IQaudio, USB sound cards, the
3.5 mm jack, HDMI, and Bluetooth sinks (`bluez_output.*`).

**System packages.** `libvlc5`, `vlc-plugin-base`, `vlc-plugin-access-extra`
(playback engine, codecs, HTTP/HTTPS access), `pulseaudio-utils` (`pactl` for
sink discovery, `pacat` for the prewarm, `paplay` for the test tone), `curl`
for the health check.

Explicitly **not** the `vlc` package: that is the desktop player and pulls in
`vlc-plugin-qt`, which drags Qt5 and the whole Mesa stack — libLLVM,
libgallium, libz3 — into the image. None of it is reachable from a headless
service, and together it was roughly 400 MB, more than half the image. No ALSA
tooling either, since `/dev/snd` is not mapped.

**Python.** `python-vlc`, `fastapi`, `uvicorn[standard]`, `aiomqtt`,
`pydantic`, `structlog`, plus `minabox-shared` — see
[shared-lib](../shared-lib/README.md).

**Services.** The MQTT broker for every command and status report; the backend
sends the commands and consumes `position-report`. Compose starts this service
after the backend is healthy. `/mnt/audio` is mounted **read-only** — this
service plays files, it never writes them.

## 7. Errors, Health & Logging

| State | Condition |
| --- | --- |
| `healthy` | MQTT connected, VLC initialised, configured output device present |
| `degraded` | any of those missing |

`GET /health` answers 200 in both cases; the difference is in the `status`
field, which the backend surfaces in the system overview.

Every command handler catches its exceptions, logs them structured, and — for
playback, volume and device switching — publishes on `audio/error`. A failing
command never takes the service down. `VLCBackend.play()` wraps every failure
into `PlaybackError`, including the missing-file case, so the outside world
always sees `playback_error` with the original message.

The status loop, the shutdown path and the device probing inside the status
publish each swallow their own errors: a sink list that cannot be read must not
stop the status from being published, and a failing shutdown step must not
prevent the remaining steps from running. Config errors leave the previous
configuration active; a missing config file is created with defaults; a corrupt
state file falls back to defaults.

Logging is structlog — JSON at INFO, console at DEBUG, changeable at runtime by
publishing `{"log_level": "DEBUG"}` on `config/general`. Event names are stable
identifiers, not sentences: `audio_service_started`, `pipeline_cold_prewarming`,
`play_interrupted_cancelling_previous`, `volume_clamped_to_limits`,
`resume_buffer_lost_replaying`, `position_report_published`,
`pulse_sinks_detected`, `state_saved`.

## 8. Development & Tests

The service needs libVLC and a Pulse server, so it does not run meaningfully on
a development machine without them — the tests are written so they do not have
to.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/audio-service/tests -q
```

| File | Covers |
| --- | --- |
| `test_pulse_detector.py` | `pactl` output parsing, display-name preference, cache behaviour |
| `test_state_manager.py` | atomic writes, corrupt-file recovery, the `last_volume == 0` rule |
| `test_go_live_hardening.py` | startup volume selection, status after stop, volume clamping, the last will |
| `test_volume_reporting.py` | the libVLC −1 / 0 cases described in 4.1 |
| `test_audio_status_payload.py` | the status payload and its fingerprint |
| `test_seek_position.py` | seeking, and waiting for VLC to confirm the jump |
| `test_output_device_health.py` | `/health` when the configured sink is gone, and when the lookup itself fails |
| `test_troubleshoot.py` | the repair chain: idempotence, "only what is demonstrably wrong", the fallback |
| `test_announce_command.py` | the announcement: ducking, the level always coming back, no overlap, a malformed payload |

The VLC backend itself is only covered where it can run without libVLC.

```bash
.venv/bin/ruff check services/audio-service
```

```bash
./scripts/build-local.sh audio
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add an MQTT command | `core/mqtt_handler.py` (routing + payload validation) | a handler in `core/service.py`, the subscription list in `infrastructure/mqtt_client.py`, table 4.2, the backend's publisher |
| change how an announcement is mixed in | `core/service.py` (`_handle_announce`) | `test_announce_command.py`, section 4.4 — the restore path is the part that must not break |
| add a status field | `infrastructure/audio_backend.py` (`AudioStatus`) | the publish in `core/service.py`, **the fingerprint** if it should trigger a publish, table 4.1, and every consumer (backend WS, display, LED, WebUI) |
| change playback behaviour | `infrastructure/vlc_backend.py` | `test_seek_position.py`; the pause/resume workarounds in 3.1 exist for measured reasons |
| add a REST endpoint | `api/routes.py` + `models/schemas.py` | the backend proxy route if the WebUI needs it, table 4.3 |
| add a config field | `config_schema.py` | `config/audio.json.example`, migration in `config_manager.py` if it replaces something, table 5.2, the WebUI settings page |
| change volume limits or clamping | `infrastructure/vlc_backend.py` (`set_volume`) and `core/service.py` (`_enforce_volume_limits`) | `test_volume_reporting.py`, `test_go_live_hardening.py` — this is the child-protection path |
| add a troubleshoot step | `core/troubleshoot.py` | `test_troubleshoot.py`, the WebUI's translated step texts, and check whether the step belongs in host-helper instead |
| support another output backend | `infrastructure/audio_backend.py` (the ABC) | a new backend class, `pulse_detector.py`'s equivalent, `config_schema.py` |

### Invariants

- **Every volume write goes through the clamp.** It is the child protection,
  and the status payload's meaning depends on it: a reported volume outside the
  configured range would be undecidable.
- **Mute never touches the volume.** The clamp would swallow it, and unmuting
  would have nothing to restore.
- **`position_ms` stays out of the status fingerprint.** Including it publishes
  a message every two seconds during playback for no new information.
- **The last will stays registered before the first connect.** Without it a
  killed process leaves a retained `playing` that every display believes.
- **The state file is written atomically.** The box is expected to lose power
  mid-write.
- **`/health` answers 200 while degraded, and its sink lookup stays capped.**
  Both exist so a slow or absent sound server cannot become a restart loop.
- **`/mnt/audio` stays read-only here.** Writing media is the media-downloader's
  and the backend's job.
- **Playback stays serialised behind its lock.** Concurrent `play` calls
  corrupted the VLC pipeline; that is what the lock and the cancel are for.
- **The test tone plays under the music role, at forced volume.** Any other
  role tests a path that cannot fail the way the music fails.
- **An announcement plays under the *notification* role, on the named sink.**
  The music role is the one this service mutes, and WirePlumber remembers mute
  per role — under `Music` a muted box would swallow "the sound is off".
- **The ducked volume is always restored, in a `finally`.** Music left quiet by
  a failed announcement is indistinguishable from a broken speaker.

## 10. Related Documents

- [`services/audio-service/README.md`](../../../services/audio-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/backend/README.md`](../backend/README.md) — sender of every command, consumer of `position-report`
- [`docs/services/host-helper/README.md`](../host-helper/README.md) — the host half of the sound repair (`POST /audio/repair`)
- [`docs/services/display/README.md`](../display/README.md) — consumer of `audio/status`
- [`docs/services/shared-lib/README.md`](../shared-lib/README.md) — MQTT base client
