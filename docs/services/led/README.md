# LED Service

The LED service is the output stage for the box's single-colour status LEDs.
It listens to what the other services publish, condenses it into a small set of
*logical states*, and renders each state as a *pattern* on whichever LEDs the
user bound to it. Which LED means what is entirely configuration.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-led` |
| Source | `services/led-service/src/led_service/` |
| Version | `services/led-service/VERSION` |
| Compose service | `led` (profile `led`) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn, gpiozero + lgpio |
| Speaks | MQTT; REST on container port `8000`, host `127.0.0.1:8004` |
| Needs | MQTT broker, `/dev/gpiochip0` + `/dev/gpiomem`, `config/leds.json` written by the backend |

## 1. Purpose & Responsibility

- Drive single-colour LEDs over GPIO behind an abstraction, so nothing else in
  the stack ever touches a pin number.
- Keep "logical state → LED pattern" purely configuration, so the number of
  LEDs and their meaning can differ per box without a code change.
- Fail quietly. A missing binding, an unreachable broker or a pin that cannot
  be claimed must never take the process down.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Deciding *that* something happened (a card is unknown, playback started) | the service that publishes the event |
| Owning `config/leds.json` | backend — it writes the file, this service reads it |
| Any persistence or database | backend |
| Addressable/RGB LEDs | not supported; this is single-colour output only |

The service only reacts to states decided elsewhere. Its config directory is
mounted **read-only**, which is the ownership made physical.

## 2. File & Folder Structure

```
services/led-service/
├── Dockerfile               two-stage build; compiles the lg C library from source
├── requirements.txt         FastAPI, uvicorn, pydantic, aiomqtt, structlog, gpiozero, lgpio
├── VERSION                  service version, single source
├── config/
│   ├── leds.json            live config — not in git, seeded by the installer
│   └── leds.json.example    template used by scripts/setup-folders.sh
├── src/led_service/
│   ├── main.py              entry point: config, logging, components, signals, shutdown
│   ├── config.py            loads env + leds.json into one AppConfig
│   ├── config_schema.py     ** the pattern contract ** — LEDPattern validation and repair
│   ├── config_manager.py    thin subclass of shared_lib JsonConfigManager
│   ├── exceptions.py        service-specific exception hierarchy
│   ├── core/
│   │   ├── led_controller.py  ** the behaviour ** — LEDController (one pin) and
│   │   │                      LEDManager (all pins): claiming, cancelling, locking
│   │   ├── led_patterns.py    the five pattern coroutines
│   │   └── state_manager.py   MQTT topic + payload → logical state
│   ├── infrastructure/
│   │   └── mqtt_client.py     subscription list and the config API
│   └── api/routes.py          GET /health, POST /test
└── tests/                     see section 8
```

The connection lifecycle itself lives in `shared_lib.mqtt.BaseMQTTClient`;
`mqtt_client.py` only adds this service's topics and dispatch.

## 3. Runtime Flow

### 3.1 Logical states

A logical state is derived from exactly one MQTT topic. This is the complete
set, defined in `core/state_manager.py::_build_derivation_rules()` and mirrored
for the WebUI by `backend_service/api/routes_config.py::_LED_BINDING_STATES`.
All topics are prefixed `minabox/<device-id>/`.

| Topic | Logical state | Derived from |
| --- | --- | --- |
| `audio/status` | `audio_playing` / `audio_paused` / `audio_stopped` | JSON field `state`; an unknown value falls back to `audio_stopped` |
| `rfid/tag-scanned` | `rfid_scanned` | topic alone |
| `rfid/tag-removed` | `rfid_removed` | topic alone |
| `rfid/unknown-tag` | `rfid_unknown_tag` | topic alone |
| `rfid/tag-blocked` | `rfid_tag_blocked` | topic alone |
| `rfid/presence` | `rfid_scanned` / `rfid_removed` | JSON field `tag_present` |
| `system/service-started` | `system_online` | topic alone |
| `system/service-error` | `system_error` | topic alone |
| `system/booting` | `system_booting` | topic alone |
| `button/raw-event` | `button_pressed` | topic alone |
| `backend/unreachable` | `backend_unreachable` | topic alone |
| `led/usage-denied` | `usage_denied` | topic alone |

A topic without a rule is ignored and logged at debug level. A rule that raises
— malformed JSON — is logged as an error; the base client's message loop
swallows it so the broker connection survives.

**Every topic in this table must also appear in the subscription list.** It is
easy to add one and forget the other, and the failure is invisible: the WebUI
offers the state and nothing ever happens. `tests/test_mqtt_subscriptions.py`
compares the two lists for exactly this reason.

`rfid/presence` is the recovery path. The RFID service publishes it retained,
so the broker re-delivers the current card state on every subscribe. Without it
a config reload would leave a state-dependent LED showing whatever it happened
to show, until the next physical scan.

### 3.2 Pattern execution

`LEDManager` owns one `LEDController` per configured LED. `initialize_leds()`
sets the gpiozero pin factory to `LGPIOFactory` **once** and then builds the
controllers. `LGPIOFactory` talks to `/dev/gpiochip0` and, unlike
`NativeFactory`, supports software PWM inside a container without a `pigpiod`
daemon.

Per state change:

1. `LEDManager.apply_state(state)` calls `apply_pattern()` on every controller
   concurrently.
2. The controller returns immediately if the LED is disabled, if GPIO was never
   available, or if it has no binding for that state.
3. Otherwise the pattern currently running on that LED is cancelled — cancel
   event first, hard cancel after one second — and the new one starts as its
   own task.
4. `solid`, `off` and `glow` are **persistent**: their task finishing does not
   clear the LED's remembered state, because the light stays as it is. `blink`
   and `pulse` release the state when they finish.

Re-applying the state an LED already shows does nothing. That matters for
`audio/status`, which repeats while a track plays: without the check every one
of those messages restarted the solid pattern and logged a state change, about
once a second.

Every pattern coroutine turns the LED off in its `finally` block, so a
cancelled blink never leaves an LED stuck on. A pattern that raises inside its
task logs `pattern_task_failed` and the controller forgets the state, so the
next attempt is not suppressed as a repeat.

States are applied in broker delivery order: the MQTT client awaits its handler
rather than dispatching each message into its own task. Each controller
additionally holds a lock around "cancel the old pattern, start the new one" —
two states arriving three milliseconds apart (`rfid/presence` and
`rfid/tag-scanned` do exactly that) could otherwise both cancel, both start,
and leave the first pattern running with nothing owning it. `POST /test` takes
the same lock, which is how a real state change preempts a test blink.

### 3.3 Reload and shutdown

A reload re-reads `leds.json`, rebuilds every controller, re-applies
`system_online`, and then re-subscribes to `rfid/presence` and `audio/status`
so the broker re-delivers those retained messages and the LEDs recover their
real state instead of sitting at `system_online`.

The pin factory is set once per process. It used to be re-created on every
reload, and gpiozero never closes the factory it replaces, so each save in the
WebUI leaked an open `/dev/gpiochip0` handle.

On `SIGTERM`/`SIGINT`: the API server stops, the MQTT loop is stopped and
awaited, then every controller turns its LED off, closes the pin and leaves it
as an input with a pull-down — so nothing stays lit after
`docker compose down`.

## 4. Public Interfaces

### 4.1 MQTT — subscribed

The topics of 3.1, plus the config API below, plus `config/general` (global log
level, handled by the shared base client — a level change in the WebUI takes
effect without a restart). All subscriptions are registered at construction
time and applied by the base client on every (re)connect, so the service is
never silently mute after a broker restart.

### 4.2 MQTT — published

| Topic | Retained | Meaning |
| --- | --- | --- |
| `system/service-started` | remembered | `{"service": "led"}`, re-sent after a reconnect |
| `led/config/response` | no | result of a reload |

There is exactly one config path and it is a reload:

| Topic | Direction | Meaning |
| --- | --- | --- |
| `led/config/reload` | backend → service | re-read `leds.json`, rebuild controllers, re-apply `system_online` |
| `led/config/response` | service → backend | result, sent after the reload has actually run |

```json
{ "success": true, "error": null, "timestamp": "2026-02-14T13:30:05Z" }
```

On failure `success` is `false` and `error` carries `reload_failed`. The reload
is awaited before the response goes out, so a config the service could not
apply is never reported as saved.

A `config/update` topic carrying the whole configuration used to exist, but
nothing published it and it could not have worked — it wrote into a read-only
mount. It is gone, along with the `config/get` stub that only ever
acknowledged.

### 4.3 REST

`GET /health`

```json
{
  "status": "healthy | degraded",
  "service": "led",
  "version": "0.2.3",
  "device_id": "box1",
  "leds_configured": 5,
  "leds_available": 5,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`leds_configured` and `leds_available` are reported separately on purpose: they
differ when a pin cannot be claimed — a wrong `GPIO_GID` after an update leaves
every LED dark — and reporting only the configured count made that look
perfectly healthy. `status` is `degraded` when the broker is away, or when LEDs
are configured but none holds a pin.

`POST /test` — body `{"led_id": "led_2"}`. Starts a fixed test blink (500 ms
interval, five blinks) regardless of the LED's bindings and **returns
immediately**: the backend proxies this call with a five second timeout, so
waiting for the blink to finish would race it. Returns 404 if the id is unknown
or the pin was never claimed. The WebUI reaches it through the backend, which
proxies to `http://led:8000/test`.

The Docker health check only asks whether `/health` answers, so a `degraded`
service stays a healthy container on purpose: neither a missing broker nor an
unclaimable pin is fixed by a restart.

## 5. Configuration

### 5.1 Environment

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `MQTT_BROKER`, `MQTT_PORT` | yes | — | broker |
| `MINABOX_DEVICE_ID` | yes | — | topic prefix |
| `LOG_LEVEL` | yes | — | initial log level |
| `DISABLE_GPIO` | no | `false` | skip pin initialisation entirely (development) |
| `GPIOZERO_PIN_FACTORY` | set by compose | `lgpio` | must stay `lgpio` — see 3.2 |

### 5.2 `config/leds.json`

The whole configuration. **Not** in git; the installer seeds it from
`leds.json.example`. The backend owns it: the WebUI writes through
`PUT /api/config/leds`, which writes the file atomically and then publishes
`led/config/reload`. Inside the container the directory is mounted read-only.

```json
{
  "leds": [
    {
      "id": "led_5",
      "name": "Ring",
      "gpio": 16,
      "enabled": true,
      "bindings": {
        "rfid_scanned": { "pattern_type": "solid" },
        "rfid_removed": {
          "pattern_type": "glow",
          "cycle_ms": 2000,
          "min_brightness": 0.0,
          "max_brightness": 1.0,
          "repeat": 0
        }
      }
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | internal identifier assigned by the backend (`led_1`, `led_2`, …); never shown to the user |
| `name` | display name for the WebUI and the logs |
| `gpio` | BCM pin number |
| `enabled` | `false` makes the LED ignore every state change **and** claim no pin, so switching it off in the UI frees the pin. Defaults to `true`, so older configs keep working |
| `bindings` | map of logical state → pattern object |

Several LEDs may bind the same state; a state without a binding leaves that LED
untouched. Two entries on the same pin or with the same `id` are accepted and
logged (`duplicate_led_gpio`, `duplicate_led_id`) — not worth refusing the whole
config over — but the second one loses: it cannot claim the pin, or it
overwrites the first in the controller map.

### 5.3 Pattern object

`pattern_type` is one of `solid`, `blink`, `pulse`, `off`, `glow`.

- **`solid`** — on, and stays on until another pattern takes over.
  `duration_ms` has no meaning here and is stripped at parse time with a
  warning (`solid_pattern_duration_ignored`).
- **`blink`** — on for `interval_ms`, off for `interval_ms`, repeated.
- **`pulse`** — on for `duration_ms`, then off, then a gap of
  `max(100 ms, duration_ms / 3)` before the next pulse. The last pulse has no
  trailing gap.
- **`off`** — switches the LED off immediately without a visible flash. This is
  what frequently repeating states such as `audio_stopped` should use.
- **`glow`** — breathing effect over software PWM: brightness follows a sine
  curve in 50 steps per cycle, `min_brightness` → `max_brightness` → back.

| Field | Applies to | Meaning |
| --- | --- | --- |
| `interval_ms` | `blink` | on-time, and off-time, of one blink. Required |
| `duration_ms` | `pulse` | on-time per pulse. Required; cleared on every other pattern type |
| `repeat` | `blink`, `pulse`, `glow` | complete cycles — one blink is on *and* off again. `0` or omitted runs until another state overrides this LED |
| `cycle_ms` | `glow` | one full dark → bright → dark cycle. Minimum 500, default 2000, sensible range 1000–3000 |
| `min_brightness` | `glow` | 0.0–1.0, default 0.0. Must be smaller than `max_brightness` |
| `max_brightness` | `glow` | 0.0–1.0, default 1.0 |

**The schema repairs a pattern it cannot run rather than rejecting it,** and
logs a warning. A `pulse` without a usable `duration_ms` and a `glow` whose
`min_brightness` is not below its `max_brightness` both used to reach the
pattern coroutine, raise inside its task and leave the LED dark. Refusing the
config instead is worse: an invalid `leds.json` stops the service from starting
at all, and one binding on a default is cheaper than a box with no LEDs.

> **Software PWM:** as soon as one binding of an LED uses `glow`, the
> controller claims that pin as a `gpiozero.PWMLED` instead of a plain `LED`.
> This works on any standard Raspberry Pi GPIO pin and needs no wiring change.
> Very short cycles (< 500 ms) can flicker because of OS scheduling, which is
> why the schema enforces the 500 ms floor; at the usual 1–3 s it is invisible.

## 6. Dependencies

**Hardware.** GPIO pins reached through `/dev/gpiochip0` and `/dev/gpiomem`.
Without them the service still starts; every LED stays inert and `/health`
reports `degraded`.

**Publishing services.** audio (`audio/status`), rfid (`rfid/*`), button
(`button/raw-event`), backend (`system/*`, `backend/unreachable`,
`led/usage-denied`). None of them is required for startup — an absent publisher
simply means that state never occurs.

**Backend.** Owns `leds.json`, triggers `led/config/reload`, and proxies the
LED test to `POST /test`.

**shared-lib.** `BaseMQTTClient`, `JsonConfigManager`, `load_env`,
`setup_structlog`, `get_version` — see [shared-lib](../shared-lib/README.md).

**Python.** FastAPI, uvicorn, pydantic, aiomqtt, structlog, gpiozero, lgpio.
The image is built in two stages: the builder compiles the `lg` C library from
source and installs `lgpio` against it, because PyPI publishes no `lgpio` wheel
for CPython 3.13. The runtime stage keeps only `liblgpio.so` and the installed
site-packages.

### 6.1 Compose

The service runs under the `led` profile, so a box without LEDs never starts it.

| Setting | Value | Why |
| --- | --- | --- |
| `devices` | `/dev/gpiochip0`, `/dev/gpiomem` | the only host access this container gets |
| `user` | `${HOST_UID}:${GPIO_GID}` | unprivileged; the gpio group grants pin access |
| `group_add` | `${GPIO_GID}` | same group again, so lgpio can open the chip |
| `volumes` | `config:ro` | the backend writes the file, the service only reads it |
| `ports` | `127.0.0.1:8004:8000` | `POST /test` is unauthenticated; the backend reaches the service as `http://led:8000` |
| `logging` | `json-file`, 10 MB × 3 | the driver default is unlimited growth, and the box runs from an SD card |
| `depends_on` | `backend` healthy | avoids a burst of `backend_unreachable` at boot |

## 7. Errors, Health & Logging

Behaviour on failure:

- **A reload that fails:** the running configuration is kept and
  `config/response` reports `success: false`.
- **Invalid config at startup:** `load_app_config()` raises and the process
  exits, so the container restarts rather than running with no LEDs at all.
- **Broker unreachable:** startup continues, the base client retries forever,
  `/health` reports `degraded`.
- **A pin that cannot be claimed:** that LED stays inert for the rest of the
  process; the others keep working.

Events worth grepping (structlog; console at DEBUG, JSON from INFO up):

| Event | Level | Meaning |
| --- | --- | --- |
| `led_state_changed` | info | a pattern was started; carries `led_id`, `logical_state`, `pattern_type` |
| `gpio_unavailable_fallback` | warning | a pin could not be claimed; that LED stays dark for the rest of the process |
| `no_leds_available` | warning | LEDs configured but not one holds a pin — check `GPIO_GID` and the device mapping |
| `duplicate_led_gpio` / `duplicate_led_id` | warning | two entries collide; the second loses |
| `pattern_task_failed` | error | a pattern raised while running; that LED is dark until the next state |
| `solid_pattern_duration_ignored` | warning | a `solid` binding still carries `duration_ms` |
| `blink_interval_defaulted` / `pulse_duration_defaulted` / `glow_brightness_range_invalid` | warning | the schema repaired a binding the WebUI produced; fix it there to silence this |
| `config_reload_failed` | error | reload failed; the previous configuration stays active |
| `state_derivation_failed` | error | a payload could not be parsed |
| `led_pin_pulldown_failed` | warning | cleanup could not reset the pin; harmless at shutdown |

## 8. Development & Tests

**Without hardware.** `DISABLE_GPIO=true` skips pin initialisation entirely.
The flag is read once into `EnvConfig` and passed down to `LEDManager`, so
nothing below it reaches for the environment on its own — which is what makes
the controller testable. If GPIO *is* available but a pin cannot be claimed
(wrong group id, pin in use), the controller logs `gpio_unavailable_fallback`
and stays inert instead of failing startup.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/led-service/tests -q
```

| File | Covers |
| --- | --- |
| `test_led_controller.py` | claiming pins, cancelling and replacing patterns, the per-LED lock, persistent vs. releasing patterns, disabled LEDs |
| `test_led_patterns.py` | the five pattern coroutines, including the off-in-`finally` guarantee |
| `test_config_schema.py` | pattern validation **and repair** — the defaulting warnings above |
| `test_led_state_manager.py` | topic + payload → logical state |
| `test_mqtt_subscriptions.py` | that every derivation rule has a subscription (see 3.1) |
| `test_led_health_endpoint.py` | configured vs. available counts, degraded conditions |
| `led_test_doubles.py` | fake MQTT and fake pin objects |

```bash
.venv/bin/ruff check services/led-service
```

```bash
./scripts/build-local.sh led
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add a logical state | `core/state_manager.py` (`_build_derivation_rules`) | **the subscription list** in `infrastructure/mqtt_client.py`, `_LED_BINDING_STATES` in `backend_service/api/routes_config.py` (otherwise the WebUI never offers it), the table in 3.1 |
| add a pattern type | `core/led_patterns.py` | the `pattern_type` literal and its validation in `config_schema.py`, the WebUI pattern editor, tables in 5.3, `test_led_patterns.py` |
| change how a pattern looks | `core/led_patterns.py` only | nothing else — patterns are self-contained coroutines |
| add a field to a pattern | `config_schema.py` (with a repair path, not a rejection) | `led_patterns.py`, the table in 5.3, the WebUI editor |
| change pin claiming or PWM | `core/led_controller.py` (`LEDController._create_led`) | `test_led_controller.py`; keep the `DISABLE_GPIO` path working |
| add a REST endpoint | `api/routes.py` | the backend proxy route if the WebUI needs it, section 4.3 |
| react to a new MQTT topic | `infrastructure/mqtt_client.py` subscription list | a derivation rule in `state_manager.py` — a subscription without a rule does nothing |

### Invariants

- **A derivation rule and a subscription always come in pairs.** Either alone
  is silent failure; `test_mqtt_subscriptions.py` guards it.
- **The state list here, in the backend, and in the WebUI must match.** The
  backend's `_LED_BINDING_STATES` is what the user can choose from; a state
  only this service knows is unreachable.
- **The schema repairs, it does not reject.** An unusable binding must not stop
  the service from starting — one dark LED beats a box with none.
- **Every pattern turns its LED off in `finally`.** A cancelled pattern that
  skips this leaves an LED stuck on with nothing owning it.
- **The pin factory is set once per process.** gpiozero does not close a
  replaced factory; re-creating it on reload leaks `/dev/gpiochip0` handles.
- **The per-controller lock stays around cancel-then-start.** Two states three
  milliseconds apart is the normal case, not an edge case.
- **`config/leds.json` is read-only to this service.** The backend is the
  author; a write path here would create a second source of truth.
- **`/health` keeps answering 200 while degraded.** Neither a missing broker
  nor an unclaimable pin is fixed by a container restart.

## 10. Related Documents

- [`services/led-service/README.md`](../../../services/led-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/rfid/README.md`](../rfid/README.md) — publisher of the card events and the retained presence
- [`docs/services/backend/README.md`](../backend/README.md) — owner of `leds.json`, proxy for the LED test
- [`docs/services/shared-lib/README.md`](../shared-lib/README.md) — MQTT base client and config manager
