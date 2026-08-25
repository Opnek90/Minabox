# Display Service – Go-Live Review

Line-by-line review of `services/display-service/` ahead of going live, in the
same shape as the [LED](../led/GoLive-Review.md) and
[button](../button/GoLive-Review.md) reviews.

**Scope:** 1,691 lines of Python across 17 files, the Dockerfile, the shipped
config, and everything the service touches on either side — the backend routes
that write its config, the WebUI that calls them, and `shared_lib`.

**Starting position:** the service works. It has run for 46 hours without a
restart, the panel shows what it should, and the frame-skip optimisation already
in place does its job. Nothing below is a fix for something that is visibly
broken today; it is the list of things that will bite once the box is in
somebody else's hands.

**Measurements** were taken on the running box (Raspberry Pi, 4 cores,
`ghcr.io/opnek90/minabox-display:0.1.1`). Where a number appears, it was
measured rather than estimated, and the command is given so it can be repeated.

**Status:** 19 of 21 items are done, 2 partly, and 4 are deliberately left open
(1.7, 2.1, 2.2, 2.3). See *Result* below.

Legend: `[ ]` open · `[~]` partly · `[x]` done · **[H]** high · **[M]** medium ·
**[N]** low

---

## Summary

The one item that could not have shipped as it was is **1.1**: the WebUI could
save a display configuration that the display service refuses to load, and the
next container start then failed permanently. Both halves are reproduced below.
It is the same defect that was fixed for the button service in
[#126](https://github.com/Opnek90/Minabox/pull/126), and the fix has the same
shape.

After that came four medium items that all share a theme — the service was
honest with its logs but not with its interfaces. A dead panel reported
`healthy`, a panel that was not ready at boot was never picked up again, a
changed I2C address needed a container restart, and a one-off error could leave
the error icon on screen indefinitely.

On the Docker side there was a clean **≈ 42 MB** to take out of a 327 MB image at
low risk. There is also a **warning**: the `curl` → Python health-check swap that
saved 14.5 MB in the LED and button images costs **6 % of a CPU core, per
service, permanently**. That is measured, it is the largest single consumer in
both of those containers, and the display service does not copy it. Details in
section 5 — it is the most useful thing this review found, and it applies to two
services other than this one.

---

## Result

Everything in section 1 is fixed, plus the whole of section 4. What was measured
afterwards, on the box:

| | Before | After |
| --- | --- | --- |
| Image | 327 MB | **285 MB** |
| Container CPU, idle | 2.26 % | **1.99 %** |
| ...of which the service | 1.47 % | **1.22 %** |
| ruff findings | 51 | **0** |
| Unformatted files | 7 of 17 | **0 of 24** |
| Tests, display service | 9 | **135** |
| Tests, backend display config | 0 | **62** |

The fixes were verified against the real panel with a locally built image, which
is the only way to check the ones that touch device lifetime:

* a reload with no change redraws and leaves the device alone,
* `enabled: false` blanks the panel, `true` brings it back,
* changing `i2c_address` to 61 logs `display_address_changed`, closes the device,
  fails to open the new address, and `/health` turns `degraded` —
  putting it back to 60 reopens the panel and returns `healthy`,
* `POST /test` shows the pattern, and a reload during those six seconds no
  longer wipes it.

The box was returned to the published image afterwards; nothing was rolled out.

The tests were checked by breaking each fix on purpose and confirming the suite
caught it. The first pass found a gap that way: mutating the `/health` change
produced no failure, because there was no test for the endpoint at all. That is
what `test_display_health_endpoint.py` is.

### Deliberately still open

* **1.7 (character-count truncation)** — it is a layout question, and a visual
  redesign of the panel is being considered. Fixing the truncation against
  measured pixel width now would be work done twice.
* **2.1 (the frame blocks the event loop)** — real, but it changes the
  concurrency model around the device and needs an `asyncio.Lock` plus testing
  on hardware under load. It does not belong in the same change as everything
  above, and it is the natural companion to a redesign that touches the render
  path anyway.
* **2.2 (port 8006 on all interfaces)** — tracked fleet-wide as
  [Offene-Punkte 1.1](../Offene-Punkte.md); moving only this service to
  `127.0.0.1:` would leave the fleet half-converted.
* **2.3 (no last will)** — nothing subscribes to a display liveness topic, so it
  would be a topic added on spec.

### Not this service

The health-check measurement in section 5 became
[Offene-Punkte 1.4](../Offene-Punkte.md). It affects `button` and `led`, where it
costs 6 % of a core each, and it explains
[Offene-Punkte 2.6](../Offene-Punkte.md), which was recorded there as
unexplained.

---

## 1. Functional defects

### [x] [H] 1.1 An invalid `display.json` puts the container into a restart loop — and the backend hands one out

Two halves, both reproduced.

**Half one — the backend accepts a config the display service cannot load.**
`PUT /api/v1/config/display` runs `_validate_config_shape("display", body)`,
which checks exactly one thing: that `elements` is a list. The contents are not
looked at.

```
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -c "
from backend_service.api.routes_config import _validate_config_shape
_validate_config_shape('display', {'elements': [
    {'id': 'x', 'type': 'gibt_es_nicht', 'enabled': True, 'order': 0, 'area': 9}]})
print('accepted')"
```

→ `accepted`. The body is written to disk and the WebUI is told the save
succeeded.

Compare `buttons`, which since #126 has a real `_validate_buttons_config()` that
mirrors the button service's schema and rejects the same kind of body with 422.
`display` never got that treatment.

**Half two — the display service exits on it.** `main()` calls
`load_app_config()` before anything else. A `ValidationError` there propagates
out of `asyncio.run()` and the process exits 1. With `restart: unless-stopped`
that is a permanent restart loop.

```
docker run --name t -e MQTT_BROKER=mqtt -e MQTT_PORT=1883 \
  -e MINABOX_DEVICE_ID=box1 -e LOG_LEVEL=INFO \
  -v /tmp/badcfg:/app/config:ro ghcr.io/opnek90/minabox-display:0.1.1
```

→ `pydantic_core._pydantic_core.ValidationError: 2 validation errors for
DisplayServiceConfig`, exit code 1.

The running container survives, because `_handle_config_reload()` catches the
exception and keeps the old config. So the box looks fine — until the next
reboot, and then the display service never comes back. That is the worst
possible shape for this bug: the person who changed the setting and the person
who finds the broken box are separated by a reboot.

**Fix, in the order I would do it:**

1. `_validate_display_config()` in `routes_config.py`, mirroring
   `config_schema.py` the way `_validate_buttons_config()` mirrors the button
   schema — valid `type`, `area` in 0–2, non-empty `id`, `order` ≥ 0 — plus a
   test holding both ends together, like `test_button_config_validation.py`.
2. Optionally, make the service survive a bad file anyway: log it loudly and
   fall back to `DisplayServiceConfig()` defaults instead of exiting. The LED
   service deliberately exits in this situation (documented in its
   `Architecture.md`), so this is a decision to take consciously for the whole
   fleet rather than for this service alone. A blank panel that can be fixed
   from the WebUI beats a service that cannot start to serve the WebUI's
   reload — but consistency has a value too.

**Risk:** none for step 1. It only rejects bodies that are already fatal.

---

### [x] [M] 1.2 `/health` reports `healthy` when there is no panel

`routes.py` derives `status` from the broker connection alone:

```python
status="healthy" if mqtt_client.is_connected else "degraded",
```

`display_available` is in the body, but nothing reads it. If `display_init()`
failed — I2C not enabled, wrong address, ribbon cable off — the service reports
`healthy` forever while the panel stays dark.

The LED service fixed exactly this and the wording is worth copying: *configured
is not the same as usable*.

**Fix:** `degraded` when `display_enabled and not display_available`. A panel
that is switched off in the config must stay `healthy` — that is a choice, not a
fault.

**Risk:** low, but note that `degraded` does not currently reach the WebUI at
all — see [Offene-Punkte 1.2](../Offene-Punkte.md). The field would be correct
and still invisible until that is addressed. Worth doing anyway; it is what
`curl` on the box shows, and it is what the debug export captures.

---

### [x] [M] 1.3 A panel that is not ready at boot is never picked up again

`display_init()` is called once, in `start()`. If it fails, the warning is
logged and nothing ever retries. `is_available()` can never become true again
for the life of the process.

This matters because of what the panel shares the bus with. `/dev/i2c-1` also
carries the PN532 RFID reader, and the display container has `depends_on: mqtt`
and `backend` — so on a cold boot it starts while the rest of the stack is still
settling. One unlucky start and the panel is dark until somebody restarts the
container by hand.

The render loop already has the machinery for the other direction:

```python
if not was_available:
    # Display (re-)appeared - the panel content is unknown, redraw.
```

— but nothing can ever make that branch fire, because `init()` is never called
a second time.

**Fix:** in the render loop, while `cfg.enabled and not is_available()`, retry
`display_init()` on a throttle (every 30 s is plenty). `init()` already returns
early when a renderer exists, so the call is safe.

**Risk:** low. The retry only runs in a state where the service currently does
nothing at all.

---

### [x] [M] 1.4 Changing the I2C address, or switching the display off, needs a container restart

`_handle_config_reload()` reloads the file and redraws. It does not look at what
changed. Three consequences:

- **`i2c_bus` / `i2c_address` changed** → the renderer keeps talking to the old
  address. The WebUI reports success, the panel does not change, and nothing is
  logged.
- **`enabled` true → false** → the render loop stops drawing, but the last frame
  stays on the panel. From the user's side: "I switched the display off and it
  still shows the old picture."
- **`enabled` false → true**, on a box that started with it off → the panel was
  never initialised, so nothing happens.

**Fix:** compare the new config against the old one in the reload handler. On a
changed bus or address, tear the renderer down and re-init. On `enabled` going
false, `clear()`. On `enabled` going true, init if needed. This needs a
`shutdown()` in `display_controller.py` — there is currently no way to release
the device, `_renderer` is only ever assigned.

**Risk:** medium, and the only item in section 1 I would want tested on the real
panel before merging. It is the one change that touches device lifetime rather
than what gets drawn.

---

### [x] [M] 1.5 The error icon can stay on the panel indefinitely

The error flag is set by `audio/error` and `system/service-error`. It is cleared
in exactly one place:

```python
def update_audio(self, topic, payload):
    if not topic.endswith("/audio/status"):
        return
    self._has_error = False
```

So only an incoming `audio/status` clears it. And the audio service publishes
that **only when the status actually changed** (`_publish_status(force=False)`
against a fingerprint).

The reachable case: the backend's temperature logger publishes
`system/service-error` on overheating. The box cools down. Nothing about the
audio state has changed, so no `audio/status` is published, and the error icon
stays on the panel — until somebody presses play, or the MQTT connection drops
and the retained status is replayed.

**Fix:** either clear the flag on a timeout (the icon means "something went
wrong recently", which is what an OLED corner can honestly express), or have the
error state carry its own clear. A timeout is the smaller change and does not
need a new topic.

**Risk:** low.

---

### [x] [N] 1.6 A config reload can wipe the test pattern

`show_test_pattern()` sets `_test_pattern_until` before drawing, and the render
loop honours it. `_handle_config_reload()` does not — it calls `show_areas()`
directly. Saving display settings in the WebUI while the six-second test pattern
is up replaces it immediately.

**Fix:** the same deadline check in the reload handler.

**Risk:** none.

---

### [ ] [N] 1.7 Text is truncated by character count, not by width

`_render_text()` cuts at 10 characters and `show_lines()` at 20. Both are
character counts against a proportional font in a slot measured in pixels. With
six header items the zone is 21 px wide, which `100%` in DejaVu Sans at 14 px
does not fit — the text is drawn anyway and runs into its neighbour.

`_measure_text()` already exists and returns the real width. Nothing uses it to
decide truncation.

**Fix:** truncate against the measured width instead of a character count.

**Risk:** low. Worth doing together with 1.4, not on its own.

---

## 2. Robustness and operation

### [ ] [M] 2.1 Every frame blocks the event loop

`show_areas()` is a synchronous call made directly from the render loop
coroutine. Inside it: a PIL frame is drawn, `ssd1306.display()` walks all 8,192
pixels **in pure Python** to build the page buffer, and the result goes over I2C
at the kernel default of 100 kHz.

Measured in the container, the CPU part alone:

```
PIL draw:                ~6.0 ms
ssd1306 pixel loop:       6.4 ms
```

plus the transfer itself — 1,024 bytes at 100 kHz is roughly another 90 ms of
wall time. For that whole window the event loop is stopped: no MQTT messages are
consumed, no HTTP request is answered, the other loops do not tick.

Today this is survivable because the fingerprint check means it only happens
when content changes. During a volume turn on the rotary encoder, that is once a
second.

**Fix:** `await asyncio.to_thread(show_areas, ...)`. The renderer is only ever
called from the render loop, the reload handler and the test endpoint, so
serialising it behind one thread is straightforward — but those three callers
must not be allowed to overlap, so it needs an `asyncio.Lock` at the same time.

**Risk:** medium. It changes the concurrency model around the device. Worth
doing, but not on the same day as go-live.

---

### [ ] [N] 2.2 Port 8006 is unauthenticated on every interface

`ports: "8006:8000"` with no bind address, and `POST /test` needs no
authentication — anyone on the LAN can make the panel flash. The backend reaches
the service as `http://display:8000` over the compose network and does not need
the host port.

Already tracked fleet-wide as [Offene-Punkte 1.1](../Offene-Punkte.md), where
`audio` and `led` have already been moved to `127.0.0.1:`. Listed here only so
the display entry is not forgotten when that branch is done.

---

### [ ] [N] 2.3 No last will

The service publishes `system/service-started` but declares no last will, so a
container that dies leaves no trace on the broker. `rfid` and `audio` both call
`set_will()`; `display`, `led` and `button` do not.

Low value on its own — nothing currently subscribes to a display liveness topic
— but it is the cheap half of making the fleet's MQTT state trustworthy.

---

### [x] [N] 2.4 Two poll loops, 34,560 backend requests a day

`sleep-timer` and `session` are each polled every 5 s. Measured cost of one
request in the container: **12 ms CPU**, 16 ms wall. Two loops at 5 s is
**0.48 % of a core**, about a third of everything this service spends.

Neither value is available over MQTT today, so removing the polls means adding
backend publishes — a change in another service, for a service that is not
short of CPU.

**What is cheap:** `repeat_mode` and `shuffle` change when the user presses a
button, which the box already knows about. Raising the session poll to 15 s
would take a third off this number for a latency nobody can perceive on a
128×64 panel.

**Risk:** none for the interval change.

---

### [x] [N] 2.5 The health check port is hardcoded

`API_PORT` is configurable and validated (1024–65535), but `EXPOSE` and the
Dockerfile `HEALTHCHECK` both hardcode 8000, as does the compose health check.
Setting `API_PORT` would leave the container permanently unhealthy.

Nothing sets it today. Either wire it through or drop the setting; a knob that
breaks the container when turned is worse than no knob.

---

## 3. Code quality

### [x] [M] 3.1 51 ruff findings, 7 of 17 files unformatted

```
.venv/bin/ruff check services/display-service/ --statistics
```

```
21  E501   line-too-long
17  UP006  non-pep585-annotation      (typing.Dict/List/Tuple → dict/list/tuple)
 6  UP035  deprecated-import
 3  I001   unsorted-imports
 2  UP045  non-pep604-annotation-optional  (Optional[X] → X | None)
 1  F401   unused-import
 1  UP037  quoted-annotation
```

26 are auto-fixable. `ruff format --check` wants to reformat
`main.py`, `display_controller.py`, `config_schema.py`, `state_manager.py`,
`generate_icon_assets.py` and the two `__init__.py` files.

Almost all of it is `display_controller.py` still using `Dict`/`List`/`Optional`
from `typing` while the rest of the service is on the modern syntax.

**Note on `ruff format`:** `display_controller.py` and `main.py` use aligned
columns deliberately in several places — the `_ELEMENT_RENDERERS` table, the
`body_left`/`body_right` block, the `sx`/`cy` assignments. `ruff format` will
collapse that alignment. It is more readable as it stands, and the alignment is
what makes the renderer table scannable. I would either accept the loss or add
`# fmt: off` around those three blocks, but I would decide it on purpose rather
than discover it in the diff.

---

### [x] [N] 3.2 Dead code

| What | Where | Note |
| --- | --- | --- |
| `_CONDITIONAL_TYPES` | `main.py:51` | Defined, never read. The information now lives in each renderer returning `None`. |
| `AppConfig.display` | `config_schema.py` | `load_app_config()` parses `display.json` into it at startup — and nothing ever reads it. `DisplayService` parses the same file a second time through `ConfigManager`, which is the copy that actually gets used and reloaded. Two parses, and the unread one goes stale on the first reload. |
| `tenacity` | `requirements.txt`, `pyproject.toml` | Not imported anywhere in the service. |
| 8 PNG files | `src/display_service/assets/icons/` | 40 KB shipped in the image. Nothing loads them — icons have been vector-drawn by `IconRenderer` for some time. |
| `scripts/generate_icon_assets.py` | 111 lines | Generates the PNGs above. |

Removing `AppConfig.display` is the one with substance: it removes a second
source of truth for the same file. The rest is housekeeping.

---

### [x] [N] 3.3 German comments in an otherwise English codebase

`main.py:45`, `183`, `419–420`, `450–451`; `routes.py:18`; and the version block
in the `Dockerfile` (the last is tracked fleet-wide as
[Offene-Punkte 2.2](../Offene-Punkte.md), where `host-helper` and `led` already
have the English wording to copy).

Everything else in the service — docstrings, log events, the substantial
comments in the render loop — is already English. These are the leftovers.

---

### [~] [N] 3.4 Three version numbers for one service

`VERSION` says `0.1.1`, `pyproject.toml` says `0.1.0`, and `routes.py` passes
`version="0.1.0"` to `FastAPI(...)` — which is what OpenAPI reports, while
`/health` reports the build arg. Fleet-wide item, see
[Offene-Punkte 2.3](../Offene-Punkte.md). The `FastAPI(version=...)` literal is
specific to this service and should use `get_version()`.

---

### [x] [M] 3.5 Nine tests, all on one static method

`test_render_fingerprint.py` is good — it pins the redraw decision from both
sides and it caught the right things. But it is the only test, and
`_render_fingerprint` is 3 lines of the 1,509.

Untested, in the order I would add them (none of these need hardware):

1. **`_build_areas()`** — ordering within an area, `enabled: false` skipped,
   conditional renderers returning `None`, the per-area cap dropping the
   surplus, an unknown type logging instead of raising.
2. **`config_schema.py`** — that the example config validates, and that the
   bodies from 1.1 are rejected. This is the test that would have caught 1.1.
3. **`StateManager`** — the error flag lifecycle from 1.5, and a malformed
   `audio/status` payload not corrupting the cached state.
4. **The element renderers** — nine small functions with a clear contract;
   `sleep_timer` rounding up is worth a case of its own.

The LED service went from zero to a real suite in this review round and the
button service to 22 tests; this is the same job.

---

### [x] [N] 3.6 The README describes a rendering path that no longer exists

`services/display-service/README.md`:

> **Icons**: PNGs in `src/display_service/assets/icons/` […] Replace 16×16
> images to customize.

Icons are drawn by `IconRenderer`; replacing those PNGs changes nothing. The
README also omits `POST /test`, the `repeat`/`shuffle`/`bluetooth` element types
and six of the eight font families, and points at the dead script from 3.2.

`Architecture.md` in this folder has been rewritten against the code and can
serve as the source for a shorter README.

---

### [~] [N] 3.7 Small things

- `DisplayRenderer.render()` re-imports PIL on every frame and `clear()` /
  `show_lines()` re-import `luma.core.render` on every call. `sys.modules` makes
  it a dict lookup, so the cost is negligible — but the imports were pushed into
  the functions to keep the module importable without hardware, and that is now
  handled by the fact that nothing instantiates a renderer without a device.
- `Theme` is `frozen=True`, but `font_sizes` and `font_paths` are plain dicts
  and stay mutable. `MappingProxyType` or a tuple of pairs would make the
  guarantee real.
- `_measure_text()` returns the bounding-box height, which excludes the ascent
  offset, so text and icons in the same slot are centred against slightly
  different baselines. Visible if you look for it.
- `show_lines()` ignores the configured font entirely and hardcodes 14 px line
  spacing, so the setup wizard's test pattern renders in PIL's built-in bitmap
  font no matter what the box is configured for.
- `_poll_backend()` sleeps *before* its first request, so both values are 5 s
  stale at startup.
- `main()` calls `load_app_config()` before `setup_structlog()`, so the one
  error that matters most — 1.1 — is reported by an unconfigured logger and does
  not come out as JSON.

---

## 4. Docker image

`ghcr.io/opnek90/minabox-display:0.1.1` is **327 MB**. For comparison, `led` and
`button` are 229 MB after their reviews; the difference is mostly Pillow and its
bundled libraries, which this service genuinely needs.

Layer breakdown:

```
109 MB   debian trixie base
 43.7 MB python build layer (base image)
 76 MB   COPY site-packages          ← 4.1, 4.2
 19.7 MB apt: curl, fonts, libjpeg, zlib, freetype  ← 4.4, and see section 5
  5 MB   ca-certificates, netbase, tzdata
```

### [x] [M] 4.1 `uvicorn[standard]` → `uvicorn` (≈ 27 MB)

Measured inside the container:

```
uvloop       17 MB
yaml          4 MB
websockets    2 MB
watchfiles    2 MB
httptools     2 MB
```

None of it is used. The service has no WebSocket endpoint, no YAML config
(`log_config=None` is passed explicitly), and no reloader. uvloop never even
activates: `main.py` starts the server inside a loop it created itself, so
uvicorn's `setup_event_loop()` is never called.

This is the same change as `led` 4.1 and `button` 4.1, and the requirements
comment from `button-service/requirements.txt` transfers verbatim.

**Risk:** low, and it is the change with the most precedent — two services have
been running on plain `uvicorn` since their reviews.

### [x] [M] 4.2 Do not copy `pip` into the runtime image (≈ 12 MB)

The runtime image keeps the `pip` that `python:3.13-slim` ships in its own base
layer either way. But `COPY --from=builder … site-packages` lays a **second**
pip over the first, which measures 12 MB.

`led` and `button` solve it with an `rm -rf` at the end of the builder's pip
step; the comment there explains exactly this.

While there: `COPY --from=builder /usr/local/bin /usr/local/bin` (49 kB) can go
too. The entrypoint is `python -m`, and the console scripts in there belong to
packages this service never invokes.

**Risk:** low. Nothing in the container installs packages at runtime.

### [x] [N] 4.3 `tenacity` is an unused dependency (≈ 1 MB)

See 3.2. Same finding as `button` 4.5.

### [x] [N] 4.4 `libjpeg62-turbo` and `libfreetype6` are not used (≈ 2 MB)

Pillow's `aarch64` wheel bundles its own copies. Verified with `ldd`:

```
libfreetype-d42f3e9c.so.6.20.2 => .../PIL/../pillow.libs/libfreetype-…
libjpeg-fb280f2c.so.62.4.0     => .../PIL/../pillow.libs/libjpeg-…
libpng16-ff0529da.so.16.49.0   => .../PIL/../pillow.libs/libpng16-…
```

Nothing in `PIL/*.so` resolves to a system copy. `zlib1g` is in the base image
already, so listing it is a no-op. The runtime apt line reduces to
`fonts-dejavu-core`, which **is** needed — the shipped config uses `font: sans`.

**Risk:** low, but this is the one item in section 4 I would confirm with a
`POST /test` on the real panel rather than trust to `ldd`, because the failure
mode is "text renders as blank".

### [x] [N] 4.5 The builder installs a toolchain it never uses

`gcc`, `libjpeg-dev`, `zlib1g-dev`, `libfreetype6-dev` — every single dependency
resolves to a prebuilt wheel. Checked across all 31 installed packages:

```
docker exec minabox-display sh -c \
  'for w in /usr/local/lib/python3.13/site-packages/*.dist-info/WHEEL; do \
     echo "$(basename $(dirname $w)): $(grep -h ^Tag: $w | tr "\n" " ")"; done'
```

Every result is either `py3-none-any` or `cp313-cp313-manylinux…aarch64`.
Nothing is compiled.

This does not shrink the published image — the builder stage is discarded — but
it removes an apt install from every CI build and a compiler from the stage that
runs as root.

**Risk:** low, with one caveat worth writing into the Dockerfile: add
`--only-binary=:all:` to the pip invocation at the same time. Otherwise a future
Pillow release that drops the `aarch64` wheel would silently start building from
source and fail on the missing toolchain — which is a much better failure than
succeeding slowly, but only if the error message says so.

### [x] [N] 4.6 Small things in the Dockerfile

- `RUN useradd` and `RUN chown` are two layers for one operation.
- `USER 1000:988` hardcodes the numeric i2c group. `led` and `button` use
  `USER minabox` and let compose supply the group. The compose file already
  passes `${I2C_GID:-988}`, so the Dockerfile value is only a fallback for a
  `docker run` — but it is a fallback that is wrong on any box where the i2c
  group is not 988.
- `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` are set in `led` and
  `button` and missing here.
- The German comment in the version block, see 3.3.

### Result

| Item | Saving | Risk |
| --- | --- | --- |
| 4.1 `uvicorn[standard]` → `uvicorn` | ≈ 27 MB | low |
| 4.2 `pip` and `/usr/local/bin` not copied | ≈ 12 MB | low |
| 4.3 `tenacity` removed | ≈ 1 MB | low |
| 4.4 `libjpeg62-turbo`, `libfreetype6` removed | ≈ 2 MB | low, test the panel |
| 3.2 PNG assets removed | 40 kB | none |
| **Total** | **≈ 42 MB** | |

**327 MB → ≈ 285 MB.** All four are changes that two other services in this repo
have already made and have been running on since.

What is deliberately **not** on this list is `curl` — see below.

---

## 5. Runtime cost — and a warning about the health check

Measured over 120 s from the cgroup accounting, split between the service
process and everything else in the container:

```
read_cg() { id=$(docker inspect -f '{{.Id}}' "$1");
            awk '/^usage_usec/{print $2}' /sys/fs/cgroup/system.slice/docker-$id.scope/cpu.stat; }
read_p1() { docker exec "$1" awk '{print $14+$15}' /proc/1/stat; }
```

| Service | Container total | The service itself | The health check |
| --- | --- | --- | --- |
| `display` (curl) | 2.26 % | 1.47 % | **0.80 %** |
| `button` (Python) | 9.81 % | 3.74 % | **6.06 %** |

Percentages are of one core.

### What the display service itself spends

1.47 % of a core, and it accounts for cleanly:

| | |
| --- | --- |
| Two backend polls, 12 ms CPU each, every 5 s | 0.48 % |
| A frame when content changed: 6.0 ms PIL + 6.4 ms `ssd1306.display()` | up to 1.2 % while something is moving, ~0 % at idle |
| Render tick: `_build_areas()` + 69 µs fingerprint | 0.04 % |

The frame-skip optimisation is doing its job — at idle the clock changes once a
minute and the loop pushes nothing in between. The only easy win left is 2.4,
the session poll interval.

### The warning: do not copy the Python health check

The LED and button reviews replaced `curl -f http://…/health` with

```
python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(…).status==200 else 1)"
```

to save 14.5 MB of apt. Measured cost of one probe, inside these containers:

| Probe | CPU per run |
| --- | --- |
| `curl -sf …/health` | **0.052 s** |
| `python -c "import urllib.request…"` | **2.13 s** |

At `interval: 30s` that is 2.13 s every 30 s = **7 % of a core, permanently**,
which matches the 6.06 % measured above almost exactly. It is the single largest
CPU consumer in both the button and the LED container — larger than the services
themselves.

**Why it is so expensive.** The official `python:3.13-slim` image ships **no
compiled bytecode for the standard library**:

```
docker exec minabox-display sh -c \
  'find /usr/local/lib/python3.13 -name "*.pyc" -not -path "*/site-packages/*" | wc -l'
→ 0
```

And the containers run as a non-root user against root-owned directories, so
Python can never write `__pycache__` either. Every probe re-compiles `ssl`,
`email`, `http.client` and `urllib.parse` from source. `python -X importtime`
attributes 1.90 s of the 2.13 s to the `urllib.request` import tree alone.

Verified by removing the cause in a throwaway container: with the stdlib
precompiled, the same import drops from 2.13 s to **0.47 s** — 4.5× faster —
at the cost of 13 MB (the stdlib grows from 104 MB to 117 MB).

**What I would do:**

- **For the display service: keep `curl`.** 15 MB of image for 0.80 % of a core
  is the right side of that trade on a Pi that also decodes audio. That is why
  `curl` is not in the section 4 list.
- **For `button` and `led`: this is worth its own branch.** Either put `curl`
  back, or add `RUN python -m compileall -q /usr/local/lib/python3.13` to the
  runtime stage (+13 MB, −5 % of a core each), or move the probe to a raw socket
  so it only imports `socket` (measured 0.86 s — better, still 16× `curl`).
  Raising `interval` to 60 s halves it regardless of which is chosen.
- **`compileall` is worth considering for every image anyway.** It also removes
  the same one-off compile from service startup, which is why the display
  service takes ~2 s longer to reach its first frame than it needs to.

This one belongs in [Offene-Punkte.md](../Offene-Punkte.md), because it affects
three services and undoes a decision two reviews already took. It is also the
likely explanation for
[Offene-Punkte 2.6](../Offene-Punkte.md) — "button service, 10 % CPU at idle" —
which is still recorded there as unexplained.

---

## 6. What I would not touch

- **The frame-skip logic.** It is the most valuable thing in this service, it is
  the only part with tests, and the comment explaining *why* names the real
  reason (bus contention with the PN532). Leave it alone.
- **The `Theme` dataclass and the slot arithmetic.** `3 × 13 + 2 × 2 = 43` is
  the body height exactly. Anyone who changes `slot_h` or `icon_size` without
  re-deriving that will produce a panel that looks almost right, and it will not
  be obvious from the diff. It works, it is documented, it should stay.
- **Vector icons instead of image files.** Drawing them costs nothing after the
  first frame — they are cached per name — and it keeps the icon set inside the
  code review. Reintroducing PNGs would be a step backwards.
- **The module-level `_renderer` singleton.** It is not the structure I would
  choose, and it makes `display_controller.py` hard to test without hardware.
  But 1.4 is the only reason to touch it, and I would make that one change
  (add a `shutdown()`) rather than restructure the module.
- **Splitting `main.py`.** The previous version of this document carried a
  refactoring checklist proposing `core/display_runner.py` and
  `core/area_builder.py`. 520 lines with a flat renderer table is not a problem
  worth solving before go-live, and moving code around is exactly the kind of
  change that breaks a service that currently works. Removed.

---

## 7. Suggested order

**Before go-live:**

1. **1.1** — backend validation for the display config, plus the test. This is
   the only item that can leave a box permanently broken.
2. **4.1–4.4** — 42 MB, all of it precedent from `led` and `button`, one rebuild.
3. **3.3** — the German comments, since the Dockerfile is being touched anyway.

**Shortly after, in one branch:**

4. **1.2, 1.3, 1.5, 1.6** — the honesty items. Small, independent, all in
   `main.py` and `routes.py`.
5. **3.1** — ruff, after 3.2 has removed the files that would otherwise be
   reformatted for nothing. Decide the `# fmt: off` question first.
6. **3.5** — the tests, starting with the schema test that covers 1.1.

**Its own branch, own testing:**

7. **1.4 + 2.1** — device lifetime and the threading of the write. Both need the
   real panel.

**Fleet-wide, not this service:**

8. The health-check measurement in section 5, into
   [Offene-Punkte.md](../Offene-Punkte.md).
9. **2.2** (port binding), **3.4** (versions) — already tracked there.
