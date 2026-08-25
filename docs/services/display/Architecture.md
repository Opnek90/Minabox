# Display Service – Architecture

## 1. Purpose & Responsibility

The display service is the output stage for the box's small I2C OLED panel
(SSD1306, 128×64, monochrome). It collects state that other services have
already decided — audio status over MQTT, sleep timer and playback session over
the backend REST API — and renders it as a fixed three-area layout whose content
is entirely driven by configuration.

Goals:

- Render the panel behind an abstraction, so nothing else in the stack knows
  about I2C, page addressing or 1-bit images.
- Keep "what is shown, and where" purely configuration, so a box can display a
  clock and a volume readout or nothing at all without a code change.
- Fail quietly. A missing panel, an unreachable broker or a backend that does
  not answer must never take the process down.
- Touch the I2C bus as rarely as possible. The OLED shares `/dev/i2c-1` with the
  PN532 RFID reader, which is the box's primary input path.

Out of scope: no business logic, no database, no writes to other services. The
service owns nothing it displays, and its own configuration is owned by the
backend — the display service reads `config/display.json` but is not the
authority on its contents.

---

## 2. File & Folder Structure

Relevant path: `services/display-service/`

```text
display-service/
├── Dockerfile                  # Two-stage build on python:3.13-slim
├── requirements.txt            # FastAPI, uvicorn, pydantic, aiomqtt, structlog, httpx, luma.oled, Pillow
├── VERSION                     # Own version number (docs/Versionierung.md)
├── tests/                      # 123 tests, no hardware needed
│   ├── display_test_doubles.py # FakePanel and the element builder
│   ├── conftest.py             # A service wired to neither panel nor broker
│   ├── test_build_areas.py
│   ├── test_config_reload.py   # Device lifetime and the render loop
│   ├── test_display_config_schema.py
│   ├── test_display_health_endpoint.py
│   ├── test_display_state_manager.py
│   ├── test_element_renderers.py
│   └── test_render_fingerprint.py   # The redraw decision
├── config/
│   ├── display.json            # Live config (not in git, seeded from the example)
│   └── display.json.example    # Template used by scripts/setup-folders.sh
└── src/display_service/
    ├── __init__.py
    ├── main.py                 # Entry point, element renderers, render loop, backend polls
    ├── config.py               # Loads the environment into AppConfig
    ├── config_schema.py        # Pydantic: DisplayElement, DisplayServiceConfig, EnvConfig
    ├── config_manager.py       # Thin subclass of shared_lib JsonConfigManager (load/reload)
    ├── exceptions.py           # Service-specific exception hierarchy
    ├── api/
    │   ├── __init__.py
    │   └── routes.py           # FastAPI: GET /health, POST /test
    ├── core/
    │   ├── __init__.py
    │   └── state_manager.py    # In-memory cache: audio, sleep timer, session, error flag
    └── infrastructure/
        ├── __init__.py
        ├── display_controller.py  # Theme, icon renderer, DisplayRenderer, module-level API
        └── mqtt_client.py         # Subscriptions and message dispatch
```

The connection lifecycle itself lives in `shared_lib.mqtt.BaseMQTTClient`:
reconnect with exponential backoff, replay of subscriptions after a reconnect,
and a `publish()` that reports failure instead of raising. `mqtt_client.py` only
adds the topics and the dispatch this service needs.

---

## 3. The Layout Model

The panel is divided into three fixed areas. Which elements land in which area
is configuration; the geometry is not.

```text
┌────────────────────────────────────────┐
│  area 0 — header, full width, 16 px    │   up to 6 items, side by side
├────────────────────────────────────────┤   ← separator line
│  area 1          │  area 2             │   up to 3 items each,
│  left column     │  right column       │     stacked and vertically centred
│  64 px           │  64 px              │
└────────────────────────────────────────┘
```

All geometry is one frozen `Theme` dataclass in `display_controller.py` — the
single source of truth for width, header height, column width, padding, slot
height and gap, icon size and the font tables. The body slots are sized so that
three items fill the body exactly: `3 × 13 px + 2 × 2 px gap = 43 px`.

Items are placed by area:

- **Header:** the width is divided into `128 / n` equal zones, one item centred
  in each. Six items therefore get 21 px each.
- **Columns:** items are stacked into 13 px slots and the whole block is centred
  vertically in the body.

Anything beyond the per-area limit is dropped at render time with a
`display_area_item_dropped` warning; the same limits are checked once at startup
and on every reload, which logs `display_area_overcrowded` before the first
frame is lost.

### Icons

Icons are **drawn**, not loaded. `IconRenderer` builds each one from PIL
`ImageDraw` primitives on a coordinate grid normalised to a 0–1 unit square, so
an icon stays sharp at any size, and the image ships no icon files. Rendered
icons are cached per name for the lifetime of the process.

Known icons: `play`, `pause`, `stop`, `mute`, `moon` / `sleep_timer`, `error`,
`repeat`, `shuffle`, `bluetooth`. An unknown name falls back to the first three
letters of its name as upper-case text, so a typo is visible on the panel rather
than silently blank.

### Fonts

`font_size` maps to a pixel height (`small` 9, `medium` 12, `large` 14) and
`font` to a list of candidate TTF paths that are tried in order. The first file
that exists and loads wins; if none does, the service logs `font_not_found` and
falls back to PIL's built-in bitmap font. Loaded fonts are cached per
`size:family` key.

Only `fonts-dejavu-core` is installed in the image, which covers `sans` and
`mono`. The other families (`roboto`, `ubuntu`, `noto`, `liberation`,
`terminus`) are offered by the schema and resolve on a host that has them, but
inside the container they fall back to the built-in font.

---

## 4. Element Types

An element type is a small function with the signature

```python
(audio, sleep_timer, session, state_manager) -> dict | None
```

registered in the `_ELEMENT_RENDERERS` table in `main.py`. Returning `None`
means "nothing to show right now", which is how the conditional types disappear
when they have nothing to say. Adding a type means adding a table entry and a
schema literal; the layout code is not touched.

| Type | Shows | Source | Conditional |
| --- | --- | --- | --- |
| `clock` | `HH:MM` | container clock (`TZ`) | no |
| `volume` | `NN%` | MQTT `audio/status` | no |
| `play_state` | play / pause / stop icon | MQTT `audio/status` | no |
| `mute` | mute icon | MQTT `audio/status` | only while muted |
| `bluetooth` | Bluetooth icon | MQTT `audio/status` | only when a BT sink exists *and* more than one output device is enabled |
| `error_state` | exclamation icon | MQTT `audio/error`, `system/service-error` | for 5 minutes after the last error |
| `sleep_timer` | moon icon + remaining minutes | backend poll | only while the timer is active |
| `repeat` | repeat icon | backend poll | only while `repeat_mode == "all"` |
| `shuffle` | shuffle icon | backend poll | only while shuffle is on |

Remaining minutes are rounded **up** (`(remaining_ms + 59999) // 60000`), so a
timer never reads `0m` while it is still running.

The error indicator expires after `ERROR_STATE_TIMEOUT` (5 minutes). It is also
cleared by any incoming `audio/status` — but the audio service only publishes
that when the status actually changed, so on an otherwise idle box the timeout
is the only thing that takes the icon down again.

---

## 5. Runtime Flow

`main.py` starts five things and then waits for a signal:

1. **Display init.** `display_init(bus, address)` opens the SSD1306 over I2C. A
   failure is a warning, not an error — the service keeps running, and the render
   loop retries every `DISPLAY_INIT_RETRY_INTERVAL` (30 s) for as long as the
   display is enabled and no panel answers. Those retries log at debug level, so
   a box that simply has no panel does not write a warning twice a minute.
2. **MQTT loop.** Started in the background; an unreachable broker no longer
   fails startup. `system/service-started` is published with `remember=True`, so
   it is republished after every reconnect.
3. **Render loop**, 1 Hz.
4. **Sleep timer poll**, every 5 s.
5. **Session poll**, every 15 s.
6. **API server** (uvicorn, inside the already running event loop).

### The render loop

The loop ticks every second, but a frame is only pushed when the content
actually changed. That decision is the `_render_fingerprint`: a `json.dumps` of
the built areas plus font size and font family, with `sort_keys=True` so key
order cannot produce a false difference and `default=str` so an unexpected value
type cannot raise inside the loop.

Why it exists: the clock only resolves to `HH:MM`, so 59 of 60 frames per minute
used to be byte-identical redraws — pure contention on the bus the RFID reader
needs. `tests/test_render_fingerprint.py` pins the behaviour from both sides:
identical content must produce an identical fingerprint, and every field that
reaches the panel must change it.

Two things override the skip:

- **Forced redraw** every 60 s, so a panel that glitched heals itself.
- **Display re-appearance.** When `is_available()` goes from false to true the
  remembered fingerprint is discarded, because the panel's content is unknown.
  This is what makes the init retry above visible: the panel comes back mid-run
  and is redrawn even though nothing about the content changed.

The test pattern holds the loop off for `TEST_PATTERN_SECONDS` (6 s) via a
deadline that is set *before* drawing, so the loop cannot slip between the draw
and the lock.

### Backend polls

Both polls share `_poll_backend()`. The `httpx.AsyncClient` lives for the whole
loop rather than per request: building and tearing one down per poll was
measurably expensive — httpcore runs an import lookup on every close, and with
two loops polling every 5 s that dominated this service's CPU time. Reusing it
also keeps the connection alive.

`ConnectError` and `TimeoutException` are swallowed silently: a backend that is
still starting is the normal case, not an incident.

The two intervals differ on purpose. The sleep timer counts down and is drawn to
the minute, so it is polled every 5 s. Repeat and shuffle only change when
somebody presses a button and are drawn as a single icon, so 15 s is enough — at
a measured 12 ms of CPU per request that is worth the difference.

---

## 6. Public Interfaces

### 6.1 MQTT — subscribed

All topics are prefixed `minabox/<device-id>/`. All are subscribed at QoS 1 and
registered before the first connect, so the base client replays them on every
reconnect.

| Topic | Effect |
| --- | --- |
| `audio/status` | Updates the cached audio state (`state`, `volume`, `muted`, `multiple_output_devices`, `bluetooth_sink_available`) and clears the error flag. |
| `audio/error` | Sets the error flag. |
| `system/service-error` | Sets the error flag. |
| `display/config/reload` | Reloads `config/display.json`, applies any hardware change, and redraws immediately. |
| `config/general` | Applies the log level, handled by `BaseMQTTClient.apply_general_config()`. |

### 6.2 MQTT — published

| Topic | When | Payload |
| --- | --- | --- |
| `system/service-started` | at startup, and again after every reconnect | `{"service": "display"}` |

### 6.3 REST

The API listens on `0.0.0.0:8000` inside the container (`API_PORT`, default
8000) and is published as `8006` on the host.

**`GET /health`**

```json
{
  "status": "healthy",
  "service": "display",
  "version": "0.1.1",
  "device_id": "box1",
  "display_enabled": true,
  "display_available": true,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`status` is `degraded` while the broker connection is down — the value is the
live socket state, not "did startup succeed once" — and also while the display
is enabled but no panel answered. Configured is not the same as usable, and a
blank panel reporting `healthy` is the one thing somebody looking at it would be
asking about. A display switched off in the config stays `healthy`: that is a
choice, not a fault.

The HTTP status is 200 either way. The container health check only asks whether
the endpoint answers at all — a restart would fix neither a dead broker nor a
missing panel.

**`POST /test`** — draws `Minabox` / `Display OK` for six seconds so the setup
wizard can confirm the panel is wired correctly. Returns `{"tested": true}`, or
404 when no panel is attached or the service is disabled, so the wizard can say
so instead of claiming a successful test. The backend proxies this as
`POST /api/v1/config/display/test`; the WebUI calls it from the hardware step of
the setup wizard.

---

## 7. Configuration

**File:** `config/display.json`, mounted read-only into the container. The
backend owns the file and publishes `display/config/reload` after every write.

```json
{
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60,
  "font_size": "large",
  "font": "sans",
  "elements": [
    { "id": "time",  "type": "clock",      "enabled": true, "order": 0, "area": 0 },
    { "id": "vol",   "type": "volume",     "enabled": true, "order": 0, "area": 1 },
    { "id": "state", "type": "play_state", "enabled": true, "order": 0, "area": 1 },
    { "id": "mute",  "type": "mute",       "enabled": true, "order": 1, "area": 2 }
  ]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `enabled` | bool | Global on/off. When false, nothing is drawn. |
| `i2c_bus` | int > 0 | Bus number, `1` for `/dev/i2c-1`. |
| `i2c_address` | int ≥ 0 | Device address, `60` = `0x3C` for the SSD1306. |
| `font_size` | `small` \| `medium` \| `large` | 9, 12 or 14 px. |
| `font` | `default` \| `sans` \| `mono` \| `roboto` \| `ubuntu` \| `noto` \| `liberation` \| `terminus` | Family; falls back to the built-in font when the file is absent. |
| `elements` | list | The elements, see below. |

Element:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | non-empty string | Free identifier, only used to tell entries apart in the WebUI. |
| `type` | element type | One of the nine types in section 4. |
| `enabled` | bool | Whether the element is considered at all. |
| `order` | int ≥ 0 | Position within the area; lower comes first (left in the header, higher in a column). |
| `area` | `0` \| `1` \| `2` | Header, left column, right column. |

A reload does not only redraw. If `i2c_bus` or `i2c_address` changed, the device
is closed and reopened on the new address; if `enabled` went false the panel is
blanked; if it went true on a box that started with the display off, the device
is opened. Otherwise a changed setting would sit in the file until the next
container restart while the WebUI reported success.

**Environment:** `MQTT_BROKER`, `MQTT_PORT`, `MINABOX_DEVICE_ID`, `LOG_LEVEL`
(all required), plus `BACKEND_URL` (default `http://backend:8080`), `API_PORT`
(default 8000, set from `DISPLAY_API_PORT` in compose) and `TZ`.

Only the environment is read into `AppConfig`. `display.json` belongs to
`ConfigManager`, which is the copy that can be reloaded — a second parse at
startup would go stale the first time the file changed.

The backend exposes `GET /api/v1/config/display/element-types` so the admin UI
can offer the available types without hardcoding them.

---

## 8. Dependencies

- **Hardware:** an SSD1306 OLED on `/dev/i2c-1`, shared with the PN532 RFID
  reader.
- **MQTT broker:** Mosquitto, host and port from the root `.env`.
- **Publishing services:** audio (`audio/status`, `audio/error`), backend
  (`system/service-error`, `config/general`, `display/config/reload`).
- **Backend:** owns `display.json`, serves `GET /api/v1/audio/sleep-timer` and
  `GET /api/v1/audio/session`, proxies the display test to `POST /test`.
- **WebUI:** the admin panel where elements and areas are assigned, and the
  setup wizard's hardware step.
- **shared-lib:** `BaseMQTTClient`, `JsonConfigManager`, `load_env`,
  `setup_structlog`, `get_version`.
- **Python:** `luma.oled` for the SSD1306 protocol, `Pillow` for the 1-bit
  frame, `httpx` for the backend polls.

---

## 9. Deployment

The service runs as the compose service `display` under the `display` profile,
so a box without a panel simply never starts it.

| Setting | Value | Why |
| --- | --- | --- |
| `devices` | `/dev/i2c-1` | The only host access this container gets. |
| `user` | `${HOST_UID}:${I2C_GID}` | Runs unprivileged; the i2c group is what grants bus access. |
| `volumes` | `config:ro` | The backend writes the file, the service only reads it. |
| `ports` | `8006:${DISPLAY_API_PORT:-8000}` | Health and test endpoint. The container port, the published port and the health check all read the same variable, so they cannot disagree. |
| `logging` | `json-file`, 10 MB × 3 | The driver default is unlimited growth, and the box runs from an SD card. |
| `depends_on` | `mqtt` + `backend` healthy | The polls would otherwise fail for the first minute. |
| `environment` | `TZ` | The clock element renders container-local time. |

The image is a two-stage build on `python:3.13-slim`, 285 MB. Every dependency
resolves to a prebuilt `aarch64` wheel — pip is called with `--only-binary=:all:`
so that stays true — and the builder therefore needs no compiler. Pillow ships
its own copies of freetype, libjpeg and libpng under `PIL/../pillow.libs`, so the
runtime stage adds only `fonts-dejavu-core`, for the `sans` and `mono` families,
and `curl`.

`curl` is there for the health check, deliberately. Replacing it with a Python
probe, as the LED and button images did, saves 14.5 MB but costs 6 % of a CPU
core: `python:3.13-slim` ships no compiled bytecode for the standard library and
this container runs unprivileged against root-owned directories, so every probe
recompiles `ssl`, `email` and `http.client` from source — 2.13 s of CPU against
0.052 s, every 30 seconds. See
[Offene-Punkte 1.4](../Offene-Punkte.md) and the go-live review.

Shutdown is handled on `SIGTERM`/`SIGINT`: the API server stops, the MQTT loop
and the three background loops are cancelled and awaited, then the panel is
blanked and the I2C handle closed — so nothing stays on screen after
`docker compose down`, and nothing holds the bus the RFID reader shares.

---

## 10. Errors & Logging

Logging is structlog through `shared_lib.logging.setup_structlog`: human
readable at `DEBUG`, JSON from `INFO` upwards.

| Event | Level | Meaning |
| --- | --- | --- |
| `display_initialized` | info | The panel answered on the configured bus and address. |
| `display_init_failed` | warning | No panel on that bus and address. The render loop keeps retrying every 30 s, at debug level. |
| `display_address_changed` | info | A reload changed the bus or address; the device is being reopened. |
| `display_shutdown` | info | The device was closed — at shutdown, or before reopening on a new address. |
| `error_state_expired` | debug | The error indicator timed out and came off the panel. |
| `display_area_overcrowded` | warning | More elements are enabled in an area than it can hold; the surplus will be dropped. |
| `display_area_item_dropped` | warning | The surplus was dropped for this frame. |
| `unknown_element_type` | warning | The config names a type with no renderer. |
| `display_render_failed` | warning | A frame could not be pushed; the next tick tries again. |
| `display_test_pattern_shown` | info | `POST /test` reached the panel. |
| `font_not_found` | warning | None of the candidate paths existed; the built-in font is used. |
| `icon_unknown` | debug | An icon name has no renderer; the name is drawn as text instead. |
| `config_reload_success` / `config_reload_failed` | info / error | Result of a `display/config/reload`. |
| `audio_status_parse_failed` | warning | An `audio/status` payload was not usable JSON. |
| `render_loop_error` | warning | The loop caught something and kept going. |

Behaviour on failure:

- **No panel at startup:** logged as a warning, the service keeps running and
  retries every 30 s, and `/health` reports `degraded` with
  `display_available: false` until one answers.
- **Invalid config file at startup:** loading raises and the process exits, so
  the container restarts — and keeps restarting. That is why the backend
  validates a display config against the same rules before writing it
  (`_validate_display_config`, held to this schema by
  `test_display_config_validation.py`). Logging is configured before the config
  is read, so the failure comes out as a JSON log line rather than a bare
  traceback.
- **Failed reload:** the previous configuration stays active and the failure is
  logged; the panel keeps showing what it showed.
- **Broker unreachable:** startup continues. The base client retries forever and
  `/health` reports `mqtt_connected: false` meanwhile.
- **Backend unreachable:** the polls stay silent and the sleep timer, repeat and
  shuffle elements keep their last known value.
