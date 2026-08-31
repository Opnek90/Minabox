# Display Service

The output stage for the box's small I2C OLED panel (SSD1306, 128×64,
monochrome). It collects state other services have already decided — audio
status over MQTT, sleep timer and playback session over the backend REST API —
and draws one finished screen at a time. It owns nothing it displays.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-display` |
| Source | `services/display-service/src/display_service/` |
| Version | `services/display-service/VERSION` |
| Compose service | `display` (profile `display`) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn, luma.oled + Pillow |
| Speaks | MQTT; REST on container port `8000`, host `127.0.0.1:8006`; polls the backend over HTTP |
| Needs | `/dev/i2c-1` (shared with the RFID reader), MQTT broker, backend for the polls |

## 1. Purpose & Responsibility

- Render the panel behind an abstraction, so nothing else in the stack knows
  about I2C, page addressing or 1-bit images.
- Fail quietly. A missing panel, an unreachable broker or a backend that does
  not answer must never take the process down.
- **Touch the I2C bus as rarely as possible.** The OLED shares `/dev/i2c-1`
  with the PN532 RFID reader, which is the box's primary input path. Most of
  the design decisions below come from this one constraint.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Deciding anything it shows | the service that publishes the state |
| Owning `config/display.json` | backend — it writes the file, this service reads it |
| Any persistence or database | backend |
| Writing to any other service | nobody — this service only reads |

Its config directory is mounted **read-only**, which is that ownership made
physical.

## 2. File & Folder Structure

```
services/display-service/
├── Dockerfile                  two-stage python:3.13-slim, 285 MB (see 6.1)
├── requirements.txt            FastAPI, uvicorn, pydantic, aiomqtt, structlog, httpx, luma.oled, Pillow
├── VERSION                     service version, single source
├── config/
│   ├── display.json            live config — not in git, seeded by the installer
│   └── display.json.example    template used by scripts/setup-folders.sh
├── src/display_service/
│   ├── main.py                 ** the orchestration ** (857 lines) — screen priority,
│   │                           render loop, backend polls, reload, shutdown
│   ├── config.py               loads the environment into AppConfig
│   ├── config_schema.py        DisplayServiceConfig, EnvConfig
│   ├── config_manager.py       thin subclass of shared_lib JsonConfigManager
│   ├── exceptions.py           service-specific exception hierarchy
│   ├── core/
│   │   ├── state_manager.py    in-memory cache: audio, sleep timer, session,
│   │   │                       error flag, and the counted-on playback position
│   │   ├── idle_animation.py   how Knuffel behaves while nothing plays
│   │   └── night.py            pure function: is the clock inside the night window
│   ├── render/                 ** whole-frame screens: pure PIL, no device **
│   │   ├── primitives.py       text measuring and wrapping, glyphs, blocks, bar
│   │   ├── fonts.py            weight lookup against the four faces in the image
│   │   ├── knuffel.py          the creature and his moods
│   │   ├── marks.py            small glyphs: error, sleep timer, barred globe
│   │   ├── idle.py             the idle screen
│   │   ├── playing.py          PlayingView, the playing screen, and paused
│   │   ├── volume.py           VolumeView and the volume overlay
│   │   ├── network.py          hotspot credentials, or "Kein Netz"
│   │   ├── unknown_tag.py      a figure the box does not know
│   │   ├── tag_blocked.py      a figure the box knows but will not play
│   │   └── quota_over.py       the daily limit is reached
│   ├── infrastructure/
│   │   ├── display_controller.py  ** the panel ** — opening it, and partial
│   │   │                          frame pushes (see 3.3)
│   │   └── mqtt_client.py         subscriptions and message dispatch
│   └── api/routes.py           GET /health, POST /test
└── tests/                      see section 8
```

The connection lifecycle lives in `shared_lib.mqtt.BaseMQTTClient`;
`mqtt_client.py` only adds the topics and dispatch this service needs.

## 3. Runtime Flow

`main.py` starts six things and then waits for a signal:

1. **Display init.** `display_init(bus, address)` opens the SSD1306 over I2C. A
   failure is a warning, not an error — the service keeps running, and the
   render loop retries every `DISPLAY_INIT_RETRY_INTERVAL` (30 s) for as long
   as the display is enabled and no panel answers. Those retries log at debug
   level, so a box that simply has no panel does not write a warning twice a
   minute.
2. **MQTT loop**, in the background; an unreachable broker does not fail
   startup. `system/service-started` is published with `remember=True`.
3. **Render loop**, 1 Hz.
4. **Sleep timer poll**, every 5 s.
5. **Session poll**, every 15 s.
6. **API server** (uvicorn, inside the already running event loop).

### 3.1 Screens, not a layout

There is no layout to configure. Every state of the box has a screen of its
own, each drawn as a whole 128×64 frame by a module under `render/`, and each
picking its own sizes for what it has to say.

| Screen | When | What carries it |
| --- | --- | --- |
| idle | nothing playing | Knuffel, wandering |
| playing | playing | title, progress bar, remaining time |
| paused | paused | title, progress bar, Knuffel asleep with Zs |
| volume | the knob was turned, or mute | blocks, one per detent |
| notice | an unknown, blocked or over-quota figure | a picture and a few words |
| network | the fallback hotspot is up, or there is no network | SSID, password, URL — or "Kein Netz" |
| test pattern | `POST /test` | two lines of text |

Why the widget grid went: 128×64 lets you show *one* thing large or nine things
unreadably, and the grid chose nine. Removed with it: `_build_areas()` and the
element renderers, `show_areas()` and the whole `Theme`/`IconRenderer` layer,
the backend's `_DISPLAY_ELEMENT_TYPES` and `GET /display/element-types`, and the
WebUI's layout editor.

**Fonts.** The image installs `fonts-dejavu-core` and nothing else, so exactly
four faces exist: Sans and Serif, each regular and bold. `render/fonts.py` asks
for a **weight**, not a font name — anything outside that list would silently
fall back to PIL's 11 px bitmap default, which is how a display ends up
unreadable without anything appearing to be wrong. Sizes are not configured
either; the one decided at runtime is the playing screen's title, where
`fit_lines()` takes the largest size in which the title fits both the width and
its band.

**Drawing.** `render/primitives.py` holds what the screens share: measuring and
wrapping text against real pixel widths, the speaker glyph, the block row, the
bar. Everything under `render/` is pure PIL and touches no device, which is
what lets the whole visual layer be tested without an SSD1306 attached —
including `test_display_screen_edges.py`, which renders every screen in every
mood and asserts that nothing reaches the edge of the panel. PIL crops
silently, so an overflowing glyph is not an error; it is simply missing a
piece, and only on the glass.

### 3.2 The render loop and screen priority

The loop ticks every second, but a frame is only pushed when the content
actually changed. That decision is the `_render_fingerprint`: a `json.dumps` of
the frame's inputs with `sort_keys=True`, so key order cannot produce a false
difference, and `default=str`, so an unexpected value type cannot raise inside
the loop.

Why it exists: the clock only resolves to `HH:MM`, so 59 of 60 frames per
minute used to be byte-identical redraws — pure contention on the bus the RFID
reader needs.

Two things override the skip:

- **Forced redraw** every 60 s, so a panel that glitched heals itself.
- **Display re-appearance.** When `is_available()` goes false → true the
  remembered fingerprint is discarded, because the panel's content is unknown.
  This is what makes the init retry visible.

The test pattern holds the loop off for `TEST_PATTERN_SECONDS` (6 s) via a
deadline set *before* drawing, so the loop cannot slip between the draw and the
lock.

Which screen owns the panel is one method, `_current_screen()`, rather than a
chain of early returns. What beats what is the only thing that decides what a
person actually sees, so it is written down in one place:

| Screen | Wins because |
| --- | --- |
| `test_pattern` | it was asked for, and answering a different question is useless |
| `volume` | it reports a gesture with a hand still on the knob |
| `notice` | a figure was put on and the box is not going to play it |
| `playing` | something is playing |
| `network` | the box cannot be reached the usual way and should say how |
| `idle` | nothing else applies |

The **network** screen appears in exactly two states, from the 20 s poll of the
backend's `/system/network-status`: the fallback hotspot is up (it shows the
SSID, the password and `http://10.42.0.1` — the panel is the only place those
are written down), or there is no network at all (a short "Kein Netz"; the
host-helper brings the hotspot up on its own within a minute). "Local network,
no internet" is a corner mark, not a screen. The screen blanks at night with
the idle screen — an hour-long lit panel nobody is reading is only burn-in —
and its text block creeps through a few vertical positions for the same reason.
A failed poll falls back to "unknown", so a stale hotspot screen cannot outlive
the hotspot.

A **notice** is one of three: an unknown figure, a blocked one, or the daily
limit. They share a slot because they share a shape — something was put on the
reader and the box stayed quiet — and that is the shape a picture is good for.
Each has its own words, because "Wer bist du?" is a lie for a figure the box
recognises perfectly well.

### 3.3 Sending only what changed

A whole frame is 1024 bytes, and at the 100 kHz this bus runs at that is 92 ms
during which the RFID reader cannot get a word in. The SSD1306 accepts a
rectangle instead — `COLUMNADDR` and `PAGEADDR` together — so a 32×16 sprite
costs 64 bytes, or 5.8 ms.

`show_image()` works out the rectangle itself by diffing against the last frame
it sent, so every screen benefits without knowing about it. Past
`MAX_PARTIAL_BYTES` it hands back to luma's own full-frame path, which is both
faster and better tested at that size.

The risk is that this reaches past luma's public API for `_const`, `_colstart`
and `_pages`. They are probed once at init and the renderer falls back to whole
frames if a luma upgrade renames any of them — a slower panel rather than a
broken one. `test_display_partial_update.py` holds the byte packing against
luma's own offset and mask formulas, so the two cannot drift apart unnoticed.

Anything that writes to the panel behind `show_image()`'s back — `clear()`,
`show_lines()`, a failed push — calls `forget_frame()`, or the next diff is
taken against a frame that is no longer there.

### 3.4 The idle screen

Knuffel, and nothing else. No clock and no text: the audience standing in front
of an idle box cannot read, and a permanent element in permanent pixels burns
into an OLED — a creature that wanders spreads the wear by itself.

`core/idle_animation.py` holds the behaviour, `render/knuffel.py` the shape.
Pure random movement reads as broken, so what he does is mostly stillness with
the eyes working: he breathes a pixel up and down, blinks every few seconds,
waves now and then, and every twenty to sixty seconds picks a spot and walks
there two pixels at a time. Waving and walking exclude each other — one thing
at a time reads better — and whichever falls due during the other is pushed
back rather than skipped, because its deadline feeds `next_due()`.

Waving makes him **wider than his own box**: an arm tucked inside the body
outline is swallowed by it, so the hand reaches past the sprite. PIL clips
silently, so `BOUNDS` reserves `knuffel.wave_overhang()` on the right, and
`test_display_partial_update.py` checks that a waving Knuffel at the far edge
has exactly as many lit pixels as one in the middle.

The cost, at 38 px:

| | on the bus |
| --- | --- |
| breathing and blinking | **1.8 %** |
| while walking | 18 % |
| average over a minute | about 4 % |

`next_due()` is what keeps that true: the loop sleeps until Knuffel's next
breath rather than polling him. Each concern contributes exactly one deadline,
and only the one that can still happen — leaving the deadline for *starting* a
walk in the list after one had started handed the loop a time in the past, and
it spun at full speed for as long as the walk lasted.

`set_asleep()` stops everything for the night. A bright thing wandering around
a dark child's bedroom is the opposite of what a night mode is for, and a still
panel is also the cheapest thing this service can do.

**Marks.** The error flag, a running sleep timer and a struck-through globe
(the box is on the LAN but has no route to the wider internet) appear as small
glyphs top right, drawn only when there is something to say. An error is worth
a mark and not a screen: `audio/error` and `system/service-error` fire on
failures that have usually recovered by the time anyone looks, a full screen
would displace Knuffel for minutes, and the flag expires by itself precisely
because nothing tells this service whether the thing is still wrong — a screen
would claim more certainty than there is.

Knuffel keeps out of the strip rather than walking under it: on a one-bit panel
two lit shapes simply merge. `set_reserved()` narrows his range and walks him
out if the strip appears while he is standing there — and it takes the clock as
an argument, because starting a walk without setting its step deadline leaves
the one from the previous walk, a time already past.

### 3.5 Brightness and the night

This device stands in a child's bedroom, and at full contrast at eight in the
evening it is a light source. `device.contrast()` is one command and two bytes,
so doing something about it costs nothing.

Dimming alone is not enough for a dark room — luma says so itself, that a low
level "will not necessarily dim the display to nearly off" — which is what
`off_at_night` is for. It switches the panel off outright, **and only while the
idle screen is showing**: something playing, a hand on the knob or a figure on
the reader takes it back, because a dark panel in those moments reads as a
broken box rather than a considerate one.

The interesting part is not the dimming but the window. Every useful night runs
past midnight, and `20:00`–`07:00` compared as a plain interval is never true.
`core/night.py` is a pure function of two strings and a clock reading for that
reason, and equal ends mean *no* night rather than a permanent one — reading it
the other way would darken a box for a setting that looks like it does nothing.

### 3.6 The volume overlay

A volume or mute change takes the whole panel for `HUD_SECONDS` (1.5 s) and
then hands it back. Three details make it behave:

- **It waits for a change, not for a message.** `audio/status` is retained and
  republished for reasons that have nothing to do with volume, so the trigger
  compares the level, the bounds and mute against the last values seen. The
  first status after a connect is state, not a change — otherwise every restart
  would flash the overlay.
- **A level that moves with the play state is not a gesture.** The overlay
  means "somebody just turned the knob", so a message that also changes the
  play state is ignored (`volume_change_with_state_change_ignored`). The audio
  service used to report 0 once `stop()` had released the media, and lifting a
  figure off the reader therefore raised a full-screen "Leise". That is fixed at
  the source, and this is the guard that keeps the panel quiet if anything like
  it comes back.
- **The loop can be woken.** A one-second tick is far too slow for a knob, so
  `_wait_for_work()` waits on an `asyncio.Event` the message handler sets, and
  shortens its own timeout to the overlay's deadline so the panel comes back on
  time rather than up to a tick late.
- **Frames have a floor.** `MIN_REDRAW_INTERVAL` (0.15 s) caps how fast frames
  can follow one another. A turn of the knob arrives as a burst of one status
  per detent, and each full frame holds the shared I2C bus for 92 ms.

The overlay shows position within `[min_volume, max_volume]`, not the raw
volume: `max_volume` is a hard clamp, so a box configured to 40 reports
`volume: 40` at the top and printing that would claim "40 %" at full volume.
The bounds and `volume_step` arrive with `audio/status`.

The test pattern outranks the overlay, and asking for it clears any overlay
standing, so it cannot reappear on top of what the user asked to see.

### 3.7 The playing screen, and paused

`render/playing.py` draws the whole frame: the title, a progress bar and the
remaining time — one element for each of the two readers, because a
four-year-old can read the bar and nothing else on this panel.

**The title's size follows its length.** `fit_lines()` picks the largest size in
which the title fits *both* the width and the title band, so a short title is
set large and "Das Lied von der Raupe Nimmersatt" is still complete on two
lines at 12 px. Checking only the width picks a size whose second line then does
not fit the band, and that line silently disappears — as it did.

**The remaining time is counted here, not asked for.** `position_ms` is
excluded from the audio service's status fingerprint on purpose, so a playing
track publishes nothing. The state manager keeps the position from the last
message together with the clock reading when it arrived and counts on from
there. Every event that moves the position out of band — a seek, a resume, the
next track — reaches us as a play command, which publishes unconditionally and
re-anchors the count. Its clock is injectable so tests can move time; patching
`time.monotonic` is not an option, because asyncio reads its event loop clock
from there and a frozen one stops every await in the process.

**The title comes from the backend, and its poll can be woken.** Fifteen
seconds is fine for repeat and shuffle but not for a title, so a changed
`track_id` pulls the next session poll forward.

**The bar is quantised.** `PROGRESS_QUANTUM_PX` (3) decides when the frame is
worth pushing: a bar advancing pixel by pixel would ask for a full frame — 92 ms
of the shared bus — every few seconds on a short track.

While muted, the screen draws a small crossed speaker top right and the title
gives up the width for it.

**Paused** has its own layout in the same module. It used to be the playing
screen with the word "Pause" where the remaining time goes — which serves
whoever can read, and the person most often standing in front of this panel
cannot yet. So Knuffel falls asleep instead: eyes shut, with `z`, `Z`, `Z`
climbing off his upper right the way a comic does it. The title and the bar
stay — what is on and how far in are both still true while paused — and only
their bands move up. The remaining time is the one thing dropped, and it is the
one thing that is frozen anyway.

The Zs are the animation and they are the whole cost. One Z, then two, then
three, then round again — on a panel that cannot fade anything out, appearing
one after another is what reads as breathing.
`PAUSED_SLEEP_PHASE_SECONDS` is 2.0: exactly two render ticks, so the rhythm is
even rather than limping between one tick and two, and three phases make a
six-second breath. Knuffel himself does not move between phases, so the diffed
partial update is about four pages of 28 columns every two seconds. The phase
is derived from the render loop's clock rather than counted up, and it is part
of the screen's fingerprint *only while paused*. The Zs sit no higher than the
top of Knuffel's own box; lifted further, the biggest one runs into the
progress bar, and a Z growing out of a bar is just a broken bar.

### 3.8 Backend polls

Both polls share `_poll_backend()`. The `httpx.AsyncClient` lives for the whole
loop rather than per request: building and tearing one down per poll was
measurably expensive — httpcore runs an import lookup on every close, and with
two loops polling every 5 s that dominated this service's CPU time. Reusing it
also keeps the connection alive.

`ConnectError` and `TimeoutException` are swallowed silently: a backend that is
still starting is the normal case, not an incident.

The intervals differ on purpose. The sleep timer counts down and is drawn to
the minute, so it is polled every 5 s. Repeat and shuffle only change when
somebody presses a button and are drawn as a single icon, so 15 s is enough —
at a measured 12 ms of CPU per request that is worth the difference. The
network status is polled every 20 s.

### 3.9 Shutdown

On `SIGTERM`/`SIGINT`: the API server stops, the MQTT loop and the background
loops are cancelled and awaited, then the panel is blanked and the I2C handle
closed — so nothing stays on screen after `docker compose down`, and nothing
holds the bus the RFID reader shares.

## 4. Public Interfaces

### 4.1 MQTT — subscribed

All topics are prefixed `minabox/<device-id>/`, subscribed at QoS 1 and
registered before the first connect, so the base client replays them on every
reconnect.

| Topic | Effect |
| --- | --- |
| `audio/status` | updates the cached audio state (`state`, `volume`, `min_volume`, `max_volume`, `volume_step`, `muted`, `multiple_output_devices`, `bluetooth_sink_available`), raises the volume overlay on a real change, and clears the error flag |
| `audio/error` | sets the error flag |
| `rfid/unknown-tag` | shows the unknown-figure screen for four seconds. Published by the **backend**, not the RFID service, when a scanned tag is in no database row. Nothing in the payload is read — the topic is the whole message |
| `rfid/tag-blocked` | shows the blocked-figure screen, naming it if the payload carries a `name` |
| `led/usage-denied` | shows the daily-limit screen. Addressed to the LED service; the display listens in rather than asking for a topic of its own |
| `rfid/tag-scanned`, `rfid/tag-removed` | Knuffel waves. On arrival the greeting is usually cut short by playback taking the panel a few hundred milliseconds later; on removal it plays out |
| `system/service-error` | sets the error flag |
| `display/config/reload` | reloads `config/display.json`, applies any hardware change, and redraws immediately |
| `config/general` | applies the log level, handled by `BaseMQTTClient.apply_general_config()` |

### 4.2 MQTT — published

| Topic | When | Payload |
| --- | --- | --- |
| `system/service-started` | at startup, and again after every reconnect | `{"service": "display"}` |

### 4.3 Backend REST — consumed

| Endpoint | Interval | Used for |
| --- | --- | --- |
| `GET /api/v1/audio/sleep-timer` | 5 s | the sleep-timer mark |
| `GET /api/v1/audio/session` | 15 s | the track title, repeat, shuffle |
| `GET /api/v1/system/network-status` | 20 s | the network screen and the barred-globe mark |

### 4.4 REST — served

The API listens on `0.0.0.0:8000` inside the container (`API_PORT`, default
8000) and is published as `127.0.0.1:8006` on the host — reachable for
diagnosis on the box, not from the network.

**`GET /health`**

```json
{
  "status": "healthy",
  "service": "display",
  "version": "0.2.3",
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
blank panel reporting `healthy` is the one thing somebody looking at it would
be asking about. A display switched off in the config stays `healthy`: that is
a choice, not a fault. The HTTP status is 200 either way; the container health
check only asks whether the endpoint answers, and a restart would fix neither a
dead broker nor a missing panel.

**`POST /test`** — draws `Minabox` / `Display OK` for six seconds so the setup
wizard can confirm the panel is wired correctly. Returns `{"tested": true}`, or
404 when no panel is attached or the service is disabled, so the wizard can say
so instead of claiming a successful test. The backend proxies this as
`POST /api/v1/config/display/test`.

## 5. Configuration

### 5.1 Environment

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `MQTT_BROKER`, `MQTT_PORT` | yes | — | broker |
| `MINABOX_DEVICE_ID` | yes | — | topic prefix |
| `LOG_LEVEL` | yes | — | initial log level |
| `BACKEND_URL` | no | `http://backend:8080` | target of the three polls |
| `API_PORT` | no | `8000` | REST port, set from `DISPLAY_API_PORT` in compose |
| `TZ` | no | — | the panel renders container-local time |

Only the environment is read into `AppConfig`. `display.json` belongs to
`ConfigManager`, which is the copy that can be reloaded — a second parse at
startup would go stale the first time the file changed.

### 5.2 `config/display.json`

Mounted **read-only** into the container. The backend owns the file and
publishes `display/config/reload` after every write.

```json
{
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `enabled` | bool | global on/off; when false nothing is drawn |
| `i2c_bus` | int > 0 | bus number, `1` for `/dev/i2c-1` |
| `i2c_address` | int ≥ 0 | device address, `60` = `0x3C` for the SSD1306 |
| `brightness` | object | `day` and `night` contrast (0–255), `night_from` and `night_to` as `HH:MM`, and `off_at_night`. Absent means the defaults: 255, 40, 20:00, 07:00, off |

That is the whole file. What used to be here — `elements`, `area`, `order`,
`font`, `font_size` — configured a layout that no longer exists.

**A file that still has those keys keeps working.** Pydantic ignores unknown
ones, so a box running today starts unchanged and nothing reads them. The
backend's validator accepts them for the same reason: a check stricter than the
schema would leave that box unable to change any of its other settings.

A reload does not only redraw. If `i2c_bus` or `i2c_address` changed, the device
is closed and reopened on the new address; if `enabled` went false the panel is
blanked; if it went true on a box that started with the display off, the device
is opened. Otherwise a changed setting would sit in the file until the next
container restart while the WebUI reported success.

## 6. Dependencies

**Hardware.** An SSD1306 OLED on `/dev/i2c-1`, **shared with the PN532 RFID
reader**. I2C must be enabled on the host (`raspi-config` → Interface Options →
I2C).

**Publishing services.** audio (`audio/status`, `audio/error`), backend
(`system/service-error`, `rfid/unknown-tag`, `rfid/tag-blocked`,
`config/general`, `display/config/reload`), LED (`led/usage-denied`, listened in
on). None is required for startup.

**Backend.** Owns `display.json`, serves the three polled endpoints, and
proxies the display test.

**Python.** `luma.oled` for the SSD1306 protocol, `Pillow` for the 1-bit frame,
`httpx` for the polls, plus FastAPI, uvicorn, pydantic, aiomqtt, structlog and
`minabox-shared` — see [shared-lib](../shared-lib/README.md).

### 6.1 Compose and image

The service runs under the `display` profile, so a box without a panel never
starts it.

| Setting | Value | Why |
| --- | --- | --- |
| `devices` | `/dev/i2c-1` | the only host access this container gets |
| `user` | `${HOST_UID}:${I2C_GID}` | unprivileged; the i2c group grants bus access |
| `volumes` | `config:ro` | the backend writes the file, the service only reads it |
| `ports` | `127.0.0.1:8006:${DISPLAY_API_PORT:-8000}` | unauthenticated, so loopback only. The container port, the published port and the health check all read the same variable |
| `logging` | `json-file`, 10 MB × 3 | the driver default is unlimited growth, and the box runs from an SD card |
| `depends_on` | `mqtt` + `backend` healthy | the polls would otherwise fail for the first minute |
| `environment` | `TZ` | the panel renders container-local time |

The image is a two-stage build on `python:3.13-slim`, 285 MB. Every dependency
resolves to a prebuilt `aarch64` wheel — pip is called with
`--only-binary=:all:` so that stays true — and the builder therefore needs no
compiler. Pillow ships its own copies of freetype, libjpeg and libpng under
`PIL/../pillow.libs`, so the runtime stage adds only `fonts-dejavu-core` and
`curl`.

`curl` is there for the health check, deliberately. Replacing it with a Python
probe, as the LED and button images did, saves 14.5 MB but costs 6 % of a CPU
core: `python:3.13-slim` ships no compiled bytecode for the standard library
and this container runs unprivileged against root-owned directories, so every
probe recompiles `ssl`, `email` and `http.client` from source — 2.13 s of CPU
against 0.052 s, every 30 seconds.

## 7. Errors, Health & Logging

Behaviour on failure:

- **No panel at startup:** logged as a warning, the service keeps running and
  retries every 30 s, and `/health` reports `degraded` with
  `display_available: false` until one answers.
- **Invalid config file at startup:** loading raises and the process exits, so
  the container restarts — and keeps restarting. That is why the backend
  validates a display config against the same rules before writing it
  (`_validate_display_config`). Logging is configured before the config is
  read, so the failure comes out as a JSON log line rather than a bare
  traceback.
- **Failed reload:** the previous configuration stays active and the failure is
  logged; the panel keeps showing what it showed.
- **Broker unreachable:** startup continues; `/health` reports
  `mqtt_connected: false` meanwhile.
- **Backend unreachable:** the polls stay silent and the sleep timer, session
  and network state keep their last known values — except the network status,
  which falls back to "unknown" so a stale hotspot screen cannot outlive the
  hotspot.

Events worth grepping (structlog; console at DEBUG, JSON from INFO up):

| Event | Level | Meaning |
| --- | --- | --- |
| `display_initialized` | info | the panel answered on the configured bus and address |
| `display_init_failed` | warning | no panel there. The render loop keeps retrying every 30 s, at debug level |
| `display_address_changed` | info | a reload changed the bus or address; the device is being reopened |
| `display_shutdown` / `display_shutdown_failed` | info / warning | the device was closed — at shutdown, or before reopening |
| `display_show_failed` / `display_show_image_failed` | warning | a frame could not be pushed; the next tick tries again |
| `display_contrast_set` / `display_contrast_failed` | debug / warning | the night dimming |
| `display_visibility_set` / `display_visibility_failed` | debug / warning | `off_at_night` switching the panel off and on |
| `display_test_pattern_shown` / `display_test_pattern_failed` | info / warning | `POST /test` |
| `notice_shown` | info | an unknown, blocked or over-quota figure took the panel |
| `volume_change_with_state_change_ignored` | debug | the overlay guard from 3.6 |
| `volume_out_of_range_ignored` | debug | a status carried a level outside its own bounds |
| `error_state_expired` | debug | the error mark timed out and came off the panel |
| `audio_status_parse_failed` | warning | an `audio/status` payload was not usable JSON |
| `config_reload_success` / `config_reload_failed` | info / error | result of a `display/config/reload` |
| `font_load_failed` | warning | a face was missing; the built-in font is used |
| `render_loop_error` | warning | the loop caught something and kept going |

## 8. Development & Tests

The whole visual layer is pure PIL and the panel is behind `FakePanel`, so
everything runs without an SSD1306, without I2C and without a broker.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/display-service/tests -q
```

| File | Covers |
| --- | --- |
| `conftest.py`, `display_test_doubles.py` | a service wired to neither panel nor broker; `FakePanel` |
| `test_display_screen_priority.py` | which screen owns the panel, in every combination |
| `test_config_reload.py` | device lifetime across a reload, and the render loop |
| `test_display_partial_update.py` | the byte packing against luma's own formulas, and Knuffel's overhang |
| `test_display_screen_edges.py` | every screen in every mood: nothing may touch the panel edge |
| `test_display_playing.py`, `test_display_playing_screen.py` | what the playing screen says, and where its numbers come from |
| `test_display_volume_hud.py`, `_render.py`, `_view.py` | when the overlay takes the panel, its pixels, its arithmetic |
| `test_display_idle_animation.py` | how Knuffel behaves |
| `test_display_night.py` | dimming, and the window that wraps past midnight |
| `test_display_network_screen.py` | the hotspot and no-network states |
| `test_display_text_wrap.py` | breaking a title across lines |
| `test_display_state_manager.py` | the cache and the counted-on position |
| `test_display_health_endpoint.py`, `test_display_config_schema.py` | health states, config validation |

```bash
.venv/bin/ruff check services/display-service
```

```bash
./scripts/build-local.sh display
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add a screen | a new module under `render/` returning a whole frame | `_current_screen()` in `main.py` (**decide where it ranks**), the priority table in 3.2, `test_display_screen_priority.py`, `test_display_screen_edges.py` |
| change what a screen shows | that screen's module under `render/` | its test; check the fingerprint still changes when the new content does |
| add a shared drawing helper | `render/primitives.py` | keep it pure PIL — nothing under `render/` may touch a device |
| react to a new MQTT topic | the subscription list in `infrastructure/mqtt_client.py` | dispatch in `main.py`, the cache in `core/state_manager.py`, table 4.1 |
| poll another backend endpoint | `_poll_backend()` and a new loop in `main.py` | reuse the shared `httpx.AsyncClient`; pick the interval by how fast the value really changes (3.8), table 4.3 |
| add a config field | `config_schema.py` | `display.json.example`, the backend's `_validate_display_config`, the reload handling in `main.py` if it affects hardware, table 5.2 |
| change the panel protocol | `infrastructure/display_controller.py` | `test_display_partial_update.py` — it pins the packing against luma |
| add a mark to the idle screen | `render/marks.py` and `render/idle.py` | `set_reserved()` so Knuffel keeps out of the strip |
| change Knuffel | `render/knuffel.py` (shape), `core/idle_animation.py` (behaviour) | `next_due()` must still return only deadlines that can happen; `BOUNDS` if the silhouette grows |

### Invariants

- **The I2C budget is the design constraint.** Every new redraw competes with
  the RFID reader. Anything that pushes a frame more often needs a number
  behind it.
- **Nothing under `render/` touches a device.** That is what makes the entire
  visual layer testable without hardware.
- **The fingerprint must change whenever the panel content does.** A field that
  reaches the glass but not the fingerprint produces a screen that never
  updates.
- **`forget_frame()` after any write that bypasses `show_image()`.** Otherwise
  the next diff is taken against a frame that is no longer on the panel.
- **The service starts without a panel, without a broker and without the
  backend.** Each of the three is a `degraded` report, never an exit.
- **`/health` answers 200 in every state.** A restart fixes neither a dead
  broker nor a missing panel.
- **A screen must not touch the panel edge.** PIL crops silently, so the damage
  is invisible except on the glass; `test_display_screen_edges.py` is the guard.
- **`display.json` is read-only to this service,** and unknown keys stay
  tolerated — boxes in the field still carry the old `elements` list.
- **Reaching into luma's internals stays optional.** The probe at init and the
  full-frame fallback are what keep a luma upgrade from breaking the panel.

## 10. Related Documents

- [`services/display-service/README.md`](../../../services/display-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/audio/README.md`](../audio/README.md) — publisher of `audio/status`, including the volume bounds this panel draws
- [`docs/services/backend/README.md`](../backend/README.md) — owner of `display.json`, source of the three polls
- [`docs/services/rfid/README.md`](../rfid/README.md) — the other user of `/dev/i2c-1`
- [`docs/services/shared-lib/README.md`](../shared-lib/README.md) — MQTT base client and config manager
