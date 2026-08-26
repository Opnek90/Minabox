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
├── tests/                      # 272 tests, no hardware needed
│   ├── display_test_doubles.py # FakePanel
│   ├── conftest.py             # A service wired to neither panel nor broker
│   ├── test_config_reload.py   # Device lifetime and the render loop
│   ├── test_display_config_schema.py
│   ├── test_display_health_endpoint.py
│   ├── test_display_idle_animation.py # How Knuffel behaves
│   ├── test_display_night.py         # Dimming, and the window that wraps
│   ├── test_display_partial_update.py # Sending only what changed
│   ├── test_display_playing.py       # The playing screen: what it says and draws
│   ├── test_display_playing_screen.py # Where its numbers come from
│   ├── test_display_screen_edges.py  # No screen may touch the panel edge
│   ├── test_display_screen_priority.py # Which screen owns the panel
│   ├── test_display_state_manager.py
│   ├── test_display_text_wrap.py     # Breaking a title across lines
│   ├── test_display_volume_hud.py    # When the overlay takes the panel
│   ├── test_display_volume_render.py # Its pixels
│   ├── test_display_volume_view.py   # Its arithmetic
├── config/
│   ├── display.json            # Live config (not in git, seeded from the example)
│   └── display.json.example    # Template used by scripts/setup-folders.sh
└── src/display_service/
    ├── __init__.py
    ├── main.py                 # Entry point, screen priority, render loop, backend polls
    ├── config.py               # Loads the environment into AppConfig
    ├── config_schema.py        # Pydantic: DisplayServiceConfig, EnvConfig
    ├── config_manager.py       # Thin subclass of shared_lib JsonConfigManager (load/reload)
    ├── exceptions.py           # Service-specific exception hierarchy
    ├── api/
    │   ├── __init__.py
    │   └── routes.py           # FastAPI: GET /health, POST /test
    ├── core/
    │   ├── __init__.py
    │   ├── idle_animation.py   # How Knuffel behaves while nothing plays
    │   ├── night.py            # Whether the clock is inside the night window
    │   └── state_manager.py    # In-memory cache: audio, sleep timer, session, error flag
    ├── render/                 # Whole-frame screens: pure PIL, no device
    │   ├── __init__.py
    │   ├── fonts.py            # Weight lookup against the four faces in the image
    │   ├── idle.py             # The idle screen: Knuffel and nothing else
    │   ├── knuffel.py          # The creature, and his moods
    │   ├── marks.py            # Small glyphs: error, sleep timer, barred
    │   ├── quota_over.py       # The daily limit is reached
    │   ├── tag_blocked.py      # A figure the box knows but will not play
    │   ├── playing.py          # PlayingView and the playing screen
    │   ├── primitives.py       # Text measuring and wrapping, glyphs, blocks, bar
    │   ├── unknown_tag.py      # A figure the box does not know
    │   └── volume.py           # VolumeView and the volume overlay
    └── infrastructure/
        ├── __init__.py
        ├── display_controller.py  # Opening the panel, and partial frame pushes
        └── mqtt_client.py         # Subscriptions and message dispatch
```

The connection lifecycle itself lives in `shared_lib.mqtt.BaseMQTTClient`:
reconnect with exponential backoff, replay of subscriptions after a reconnect,
and a `publish()` that reports failure instead of raising. `mqtt_client.py` only
adds the topics and the dispatch this service needs.

---

## 3. Screens, not a layout

There is no layout to configure. Every state of the box has a screen of its
own, each drawn as a whole 128x64 frame by a module under `render/`, and each
picking its own sizes for what it has to say.

| Screen | When | What carries it |
| --- | --- | --- |
| idle | nothing playing | Knuffel, wandering |
| playing | playing or paused | title, progress bar, remaining time |
| volume | the knob was turned, or mute | blocks, one per detent |
| notice | an unknown, blocked or over-quota figure | a picture and a few words |
| test pattern | `POST /test` | two lines of text |

What replaced the grid, and why, is in [Redesign.md](Redesign.md). The short
version: 128x64 lets you show *one* thing large or nine things unreadably, and
the grid chose nine.

### Fonts

The image installs `fonts-dejavu-core` and nothing else, so exactly four faces
exist: Sans and Serif, each regular and bold. `render/fonts.py` therefore asks
for a **weight**, not a font name - anything outside that list would silently
fall back to PIL's 11 px bitmap default, which is how a display ends up
unreadable without anything appearing to be wrong.

Sizes are not configured either. Each screen picks its own, and the one place
it is decided at runtime is the playing screen's title, where `fit_lines()`
takes the largest size in which the title fits both the width and its band.

### Drawing

`render/primitives.py` holds what the screens share: measuring and wrapping
text against real pixel widths, the speaker glyph, the block row, the bar.
`render/knuffel.py` holds the creature and his moods, `render/marks.py` the
small glyphs for an error and a running sleep timer.

Everything there is pure PIL and touches no device, which is what lets the
whole visual layer be tested without an SSD1306 attached - including
`tests/test_display_screen_edges.py`, which renders every screen in every mood
and asserts that nothing reaches the edge of the panel. PIL crops silently, so
an overflowing glyph is not an error; it is simply missing a piece, and only on
the glass.


## 4. Runtime Flow

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

### Which screen owns the panel

Every state of the box now has a screen of its own, and the order between them
is one method, `_current_screen()`, rather than a chain of early returns in the
render loop. What beats what is the only thing that decides what a person
actually sees, so it is written down in one place:

| Screen | Wins because |
| --- | --- |
| `test_pattern` | it was asked for, and answering a different question is useless |
| `volume` | it reports a gesture with a hand still on the knob |
| `notice` | a figure was put on and the box is not going to play it |
| `playing` | something is playing |
| `idle` | nothing else applies |

A **notice** is one of three: an unknown figure, a blocked one, or the daily
limit. They share a screen slot because they share a shape - something was put
on the reader and the box stayed quiet - and that is the shape a picture is
good for. Each has its own words, because "Wer bist du?" is a lie for a figure
the box recognises perfectly well.

**The widget grid is gone.** It was a layout - nine element types, three areas,
an order and a font - and every state of the box having a screen of its own
left it unreachable. Removed with it: `_build_areas()` and the element
renderers, `show_areas()` and the whole `Theme`/`IconRenderer` layer under it,
the backend's `_DISPLAY_ELEMENT_TYPES` and `GET /display/element-types`, and
the WebUI's layout editor.

`display.json` keeps whatever it has. Pydantic ignores unknown keys, so a box
running today starts with its old `elements` list still in the file and nothing
reads it - which is also why the backend still *accepts* those keys: rejecting
them would leave that box unable to change any of its other settings.

### Sending only what changed

A whole frame is 1024 bytes, and at the 100 kHz this bus runs at that is 92 ms
during which the RFID reader cannot get a word in. The SSD1306 accepts a
rectangle instead - `COLUMNADDR` and `PAGEADDR` together - so a 32x16 sprite
costs 64 bytes, or 5.8 ms.

`show_image()` works out the rectangle itself, by diffing against the last
frame it sent, so every screen benefits without knowing about it. Past
`MAX_PARTIAL_BYTES` it hands back to luma's own full-frame path, which is both
faster and better tested at that size.

The risk is that this reaches past luma's public API for `_const`, `_colstart`
and `_pages`. They are probed once at init and the renderer falls back to whole
frames if a luma upgrade renames any of them - a slower panel rather than a
broken one. `tests/test_display_partial_update.py` holds the byte packing
against luma's own offset and mask formulas, so the two cannot drift apart
unnoticed.

Anything that writes to the panel behind `show_image()`'s back - `clear()`,
`show_lines()`, a failed push - calls `forget_frame()`, or the next diff is
taken against a frame that is no longer there.

### The idle screen

Knuffel, and nothing else. No clock and no text: the audience standing in front
of an idle box cannot read, and a permanent element in permanent pixels burns
into an OLED - a creature that wanders spreads the wear by itself.

`core/idle_animation.py` holds the behaviour, `render/knuffel.py` the shape.
Pure random movement reads as broken, so what he does is mostly stillness with
the eyes working: he breathes a pixel up and down, blinks every few seconds,
waves now and then, and every twenty to sixty seconds picks a spot and walks
there two pixels at a time. Waving and walking exclude each other - one thing
at a time reads better - and whichever falls due during the other is pushed
back rather than skipped, because its deadline feeds `next_due()`.

Waving makes him **wider than his own box**: an arm tucked inside the body
outline is swallowed by it, so the hand reaches past the sprite. PIL clips
silently, so `BOUNDS` reserves `knuffel.wave_overhang()` on the right and
`tests/test_display_partial_update.py` checks that a waving Knuffel at the far
edge has exactly as many lit pixels as one in the middle.

The cost, at 38 px:

| | on the bus |
| --- | --- |
| breathing and blinking | **1.8 %** |
| while walking | 18 % |
| average over a minute | about 4 % |

`next_due()` is what keeps that true: the loop sleeps until Knuffel's next
breath rather than polling him. Each concern contributes exactly one deadline,
and only the one that can still happen - leaving the deadline for *starting* a
walk in the list after one had started handed the loop a time in the past, and
it spun at full speed for as long as the walk lasted.

`set_asleep()` stops everything for the night. A bright thing wandering around
a dark child's bedroom is the opposite of what a night mode is for, and a still
panel is also the cheapest thing this service can do.

### Marks on the idle screen

The widget grid used to carry the error flag and the sleep timer in a corner,
and both went with it. They come back as small glyphs top right - drawn only
when there is something to say, so the ordinary idle screen is still Knuffel
and nothing else.

An error is worth a mark and not a screen. `audio/error` and
`system/service-error` fire on failures that have usually recovered by the time
anyone looks, a full screen would displace Knuffel for minutes, and the flag
expires by itself precisely because nothing tells this service whether the
thing is still wrong - a screen would claim more certainty than there is. The
one error that would deserve a screen is a box that cannot make sound at all
([Offene-Punkte 1.5](../Offene-Punkte.md)), and nothing publishes that yet.

Knuffel keeps out of the strip rather than walking under it: on a one-bit panel
two lit shapes simply merge. `set_reserved()` narrows his range and walks him
out if the strip appears while he is standing there - and it takes the clock as
an argument, because starting a walk without setting its step deadline leaves
the one from the previous walk, a time already past.

### Brightness and the night

This device stands in a child's bedroom, and at full contrast at eight in the
evening it is a light source. `device.contrast()` is one command and two bytes,
so doing something about it costs nothing.

Dimming alone is not enough for a dark room - luma says so itself, that a low
level "will not necessarily dim the display to nearly off" - which is what
`off_at_night` is for. It switches the panel off outright, **and only while the
idle screen is showing**: something playing, a hand on the knob or a figure on
the reader takes it back, because a dark panel in those moments reads as a
broken box rather than a considerate one. Knuffel sleeps for the night either
way, since a bright thing wandering about a dark room is the opposite of what
the setting is for.

The interesting part is not the dimming but the window. Every useful night runs
past midnight, and `20:00`–`07:00` compared as a plain interval is never true.
`core/night.py` is a pure function of two strings and a clock reading for that
reason, and equal ends mean *no* night rather than a permanent one - reading it
the other way would darken a box for a setting that looks like it does nothing.

### The unknown figure

Knuffel again, puzzled, held for `UNKNOWN_TAG_SECONDS` and then gone - it
reports an event, not a state. One character across every screen reads as one
box rather than as a pile of screens.

A blocked figure and the daily limit share the same slot and the same four
seconds; see the priority table above.

### The volume overlay

A volume or mute change takes the whole panel for `HUD_SECONDS` (1.5 s) and then
hands it back. It is the first screen built the way
[Redesign.md](Redesign.md) describes: `render/volume.py` produces a finished
128x64 frame and `show_image()` pushes it, bypassing the widget grid entirely.

Three details make it behave:

- **It waits for a change, not for a message.** `audio/status` is retained and
  republished for reasons that have nothing to do with volume, so the trigger
  compares the level, the bounds and mute against the last values seen. The
  first status after a connect is state, not a change - otherwise every restart
  would flash the overlay.
- **A level that moves with the play state is not a gesture.** The overlay
  means "somebody just turned the knob", so a message that also changes the
  play state is ignored. The audio service used to report 0 once `stop()` had
  released the media, and lifting a figure off the reader therefore raised a
  full-screen "Leise". That is fixed at the source, and this is the guard that
  keeps the panel quiet if anything like it comes back.
- **The loop can be woken.** A one-second tick is far too slow for a knob, so
  `_wait_for_work()` waits on an `asyncio.Event` that the message handler sets,
  and shortens its own timeout to the overlay's deadline so the panel comes back
  on time rather than up to a tick late.
- **Frames have a floor.** `MIN_REDRAW_INTERVAL` (0.15 s) caps how fast frames
  can follow one another. A turn of the knob arrives as a burst of one status
  per detent, and each full frame holds the I2C bus - shared with the RFID
  reader - for 92 ms. At the normal tick the floor costs nothing.

Priority: the test pattern outranks the overlay. Asking for it clears any
overlay standing, so it cannot reappear on top of what the user asked to see.

### The playing screen

While a track is playing or paused, `render/playing.py` draws the whole frame
and the widget grid stands down; when playback stops the grid comes back. The
screen carries the title, a progress bar and the remaining time - one element
for each of the two readers, because a four-year-old can read the bar and
nothing else on this panel.

**The title's size follows its length.** `fit_lines()` picks the largest size in
which the title fits *both* the width and the title band, so a short title is
set large and "Das Lied von der Raupe Nimmersatt" is still complete on two
lines at 12 px. Checking only the width picks a size whose second line then
does not fit the band, and that line silently disappears - as it did.

**The remaining time is counted here, not asked for.** `position_ms` is
excluded from the audio service's status fingerprint on purpose, so a playing
track publishes nothing. The state manager keeps the position from the last
message together with the clock reading when it arrived and counts on from
there. Every event that moves the position out of band - a seek, a resume, the
next track - reaches us as a play command, which publishes unconditionally and
re-anchors the count. Its clock is injectable so tests can move time; patching
`time.monotonic` is not an option, because asyncio reads its event loop clock
from there and a frozen one stops every await in the process.

**The title comes from the backend, and its poll can be woken.** Fifteen
seconds is fine for repeat and shuffle but not for a title, so a changed
`track_id` pulls the next session poll forward instead of leaving the previous
title on the panel for most of a minute.

**The bar is quantised.** `PROGRESS_QUANTUM_PX` (3) decides when the frame is
worth pushing: a bar advancing pixel by pixel would ask for a full frame - 92 ms
of the shared I2C bus - every few seconds on a short track.

While muted, the screen draws a small crossed speaker top right and the title
gives up the width for it. Without that, replacing the grid would take the
grid's permanent mute icon away exactly when it matters.

The overlay shows position within `[min_volume, max_volume]`, not the raw
volume: `max_volume` is a hard clamp, so a box configured to 40 reports
`volume: 40` at the stop and printing that would claim "40 %" at full volume.
The bounds and `volume_step` arrive with `audio/status`.

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

## 5. Public Interfaces

### 5.1 MQTT — subscribed

All topics are prefixed `minabox/<device-id>/`. All are subscribed at QoS 1 and
registered before the first connect, so the base client replays them on every
reconnect.

| Topic | Effect |
| --- | --- |
| `audio/status` | Updates the cached audio state (`state`, `volume`, `min_volume`, `max_volume`, `volume_step`, `muted`, `multiple_output_devices`, `bluetooth_sink_available`), raises the volume overlay on a real change, and clears the error flag. |
| `audio/error` | Sets the error flag. |
| `rfid/unknown-tag` | Shows the unknown-figure screen for four seconds. Published by the **backend**, not the RFID service, when a scanned tag is in no database row. Nothing in the payload is read - the topic is the whole message. |
| `rfid/tag-blocked` | Shows the blocked-figure screen, naming it if the payload carries a `name`. |
| `led/usage-denied` | Shows the daily-limit screen. Addressed to the LED service; the display listens in rather than asking for a topic of its own. |
| `rfid/tag-scanned`, `rfid/tag-removed` | Knuffel waves. On arrival the greeting is usually cut short by playback taking the panel a few hundred milliseconds later; on removal it plays out. |
| `system/service-error` | Sets the error flag. |
| `display/config/reload` | Reloads `config/display.json`, applies any hardware change, and redraws immediately. |
| `config/general` | Applies the log level, handled by `BaseMQTTClient.apply_general_config()`. |

### 5.2 MQTT — published

| Topic | When | Payload |
| --- | --- | --- |
| `system/service-started` | at startup, and again after every reconnect | `{"service": "display"}` |

### 5.3 REST

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

## 6. Configuration

**File:** `config/display.json`, mounted read-only into the container. The
backend owns the file and publishes `display/config/reload` after every write.

```json
{
  "enabled": true,
  "i2c_bus": 1,
  "i2c_address": 60
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `enabled` | bool | Global on/off. When false, nothing is drawn. |
| `i2c_bus` | int > 0 | Bus number, `1` for `/dev/i2c-1`. |
| `i2c_address` | int ≥ 0 | Device address, `60` = `0x3C` for the SSD1306. |
| `brightness` | object | `day` and `night` contrast (0–255), `night_from` and `night_to` as `HH:MM`, and `off_at_night`. Absent means the defaults: 255, 40, 20:00, 07:00, off. |

That is the whole file. What used to be here - `elements`, `area`, `order`,
`font`, `font_size` - configured a layout that no longer exists.

**A file that still has those keys keeps working.** Pydantic ignores unknown
ones, so a box running today starts unchanged and nothing reads them. The
backend's validator accepts them for the same reason: a check stricter than the
schema would leave that box unable to change any of its other settings, which
is worse than the stale keys sitting there.

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

---

## 7. Dependencies

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

## 8. Deployment

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

## 9. Errors & Logging

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
