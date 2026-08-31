# LED Service

## 1. Purpose & Responsibility

The LED service is the output stage for the simple, single-colour status LEDs
of the box. It listens to the MQTT events the other services emit, condenses
them into a small set of *logical states* (`audio_playing`, `rfid_scanned`,
`system_error`, …) and renders each state as a *pattern* on whichever LEDs the
user has bound to it.

Goals:

- Drive single-colour LEDs over GPIO behind an abstraction, so that the rest of
  the stack never touches a pin number.
- Keep the mapping "logical state → LED pattern" purely configuration, so the
  number of LEDs and their meaning can differ per box without a code change.
- Fail quietly. A missing binding, an unreachable broker or a GPIO pin that
  cannot be claimed must never take the process down.

Out of scope: no business logic, no database, no writing to other services. The
service only reacts to states that were already decided elsewhere, and its own
configuration is owned by the backend — the LED service reads `config/leds.json`
but is not the authority on its contents.

---

## 2. File & Folder Structure

Relevant path: `services/led-service/`

```text
led-service/
├── Dockerfile               # Two-stage build on python:3.13-slim, liblgpio from source
├── requirements.txt         # FastAPI, uvicorn, pydantic, aiomqtt, structlog, gpiozero, lgpio
├── VERSION                  # Own version number
├── tests/                   # Patterns, schema, state derivation, subscriptions
├── config/
│   ├── leds.json            # Live config (not in git, seeded from the example)
│   └── leds.json.example    # Template used by scripts/setup-folders.sh
└── src/led_service/
    ├── __init__.py
    ├── main.py              # Entry point: config, logging, components, signals, shutdown
    ├── config.py            # Loads env + leds.json into one AppConfig
    ├── config_schema.py     # Pydantic models: LEDPattern, LEDConfig, LEDServiceConfig, EnvConfig
    ├── config_manager.py    # Thin subclass of shared_lib JsonConfigManager (load/reload)
    ├── exceptions.py        # Service-specific exception hierarchy
    ├── api/
    │   ├── __init__.py
    │   └── routes.py        # FastAPI: GET /health, POST /test
    ├── core/
    │   ├── __init__.py
    │   ├── led_controller.py  # LEDController (one pin) and LEDManager (all pins)
    │   ├── led_patterns.py    # The five pattern coroutines
    │   └── state_manager.py   # MQTT topic + payload → logical state
    └── infrastructure/
        ├── __init__.py
        └── mqtt_client.py   # Subscriptions and the MQTT config API
```

The connection lifecycle itself lives in `shared_lib.mqtt.BaseMQTTClient`:
reconnect with exponential backoff, replay of subscriptions after a reconnect,
and a `publish()` that reports failure instead of raising. `mqtt_client.py`
only adds the topics and the dispatch this service needs.

---

## 3. Logical States

A logical state is derived from exactly one MQTT topic. The table below is the
complete set the service knows; it is defined in
`core/state_manager.py::_build_derivation_rules()` and mirrored for the WebUI by
`backend_service/api/routes_config.py::_LED_BINDING_STATES`. All topics are
prefixed with `minabox/<device-id>/`.

| Topic | Logical state | Derived from |
| --- | --- | --- |
| `audio/status` | `audio_playing` / `audio_paused` / `audio_stopped` | JSON field `state`; any unknown value falls back to `audio_stopped` |
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
— malformed JSON, for instance — is logged as an error; the message loop in the
base client swallows it so the broker connection survives.

Every topic in this table has to appear in the subscription list as well. It is
easy to add one and forget the other, and the result is invisible: the WebUI
offers the state, and nothing ever happens. `tests/test_mqtt_subscriptions.py`
compares the two lists.

`rfid/presence` is the recovery path. The RFID service publishes it *retained*,
so the broker re-delivers the current tag state on every subscribe. Without it
a config reload would leave a state-dependent LED (the ring, typically) showing
whatever it happened to show before, until the next physical scan.

---

## 4. Public Interfaces

### 4.1 MQTT – incoming events

The service subscribes to the topics of section 3 plus the config API of
section 4.2 and `config/general`. All subscriptions are registered at
construction time and applied by the base client on every (re)connect, so the
service is never silently mute after a broker restart.

On startup it publishes once:

- `minabox/<device-id>/system/service-started` with `{"service": "led"}`,
  remembered so it is re-sent after a reconnect.

`config/general` carries the global log level and is handled by the shared base
client — a level change in the WebUI takes effect without a restart.

### 4.2 MQTT – config API

| Topic | Direction | Meaning |
| --- | --- | --- |
| `led/config/reload` | backend → service | Re-read `config/leds.json` from disk, rebuild every controller and re-apply `system_online`. |
| `led/config/response` | service → backend | Result of the reload, sent after it has actually run. |

There is one config path and it is a reload. The backend owns the file: it
writes `leds.json` atomically through `PUT /api/config/leds` and then asks the
service to pick it up. A `config/update` topic carrying the whole configuration
used to exist as well, but nothing ever published it, and it could not have
worked — it wrote into a directory that is mounted read-only. It is gone, along
with the `config/get` stub that only ever acknowledged.

After a reload the service re-subscribes to `rfid/presence` and `audio/status`
so the broker re-delivers those retained messages and the LEDs recover their
real state instead of sitting at `system_online`.

Response payload:

```json
{
  "success": true,
  "error": null,
  "timestamp": "2026-02-14T13:30:05Z"
}
```

On failure `success` is `false` and `error` carries `reload_failed`. The reload
is awaited before the response goes out, so a config the service could not
apply is never reported as saved.

### 4.3 REST

The service runs a small FastAPI app on port 8000 inside the container
(published as 8004 on the host).

- `GET /health` – returns `status`, the service version from the image build
  args, the device id, the broker host/port, and two separate counts:
  `leds_configured` and `leds_available`. They differ when a pin cannot be
  claimed — a wrong `GPIO_GID` after an update leaves every LED dark — and
  reporting only the configured count made that look perfectly healthy.
  `status` is `degraded` when the broker is away, or when LEDs are configured
  but none of them holds a pin.

  The Docker healthcheck only checks that the endpoint answers, so a `degraded`
  service stays a healthy container on purpose: neither a missing broker nor an
  unclaimable pin is fixed by a restart.
- `POST /test` – body `{"led_id": "led_2"}`. Starts a fixed test blink
  (500 ms interval, five blinks, 5 s) regardless of the LED's bindings and
  returns immediately — the backend proxies this call with a five second
  timeout, so waiting for the blink to finish would race it. A real state
  change arriving during a test takes the LED over.
  Returns 404 if the id is unknown or the pin was never claimed. The WebUI
  reaches this through the backend, which proxies to `http://led:8000/test`.

---

## 5. Configuration Model

`config/leds.json` holds the whole configuration. The file is *not* in git; the
installer seeds it from `leds.json.example`. The backend owns it: the WebUI
writes through `PUT /api/config/leds`, which writes the file atomically and
then publishes `led/config/reload`.

Inside the LED container the directory is mounted **read-only**, which matches
that ownership — the service reads the file and never needs to write it.

### 5.1 Structure

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
| `id` | Internal identifier assigned by the backend (`led_1`, `led_2`, …). Never shown to the user. |
| `name` | Display name for the WebUI and the logs. |
| `gpio` | BCM pin number the LED is wired to. |
| `enabled` | `false` makes the LED ignore every state change *and* claim no GPIO pin at all, so switching it off in the UI frees the pin. Defaults to `true` so older configs keep working. |
| `bindings` | Map of logical state → pattern object. |

Several LEDs may bind the same state; a state without a binding leaves that LED
untouched.

Two entries on the same pin or with the same `id` are both accepted and both
logged as a warning (`duplicate_led_gpio`, `duplicate_led_id`). Neither is worth
refusing the whole config over, but the second entry loses in each case: it
cannot claim the pin, or it overwrites the first in the controller map.

### 5.2 Pattern object

`pattern_type` is one of `solid`, `blink`, `pulse`, `off`, `glow`.

- **`solid`** – on, and stays on until another pattern takes over. `duration_ms`
  has no meaning here and is stripped at parse time with a warning
  (`solid_pattern_duration_ignored`); leave it out of new configurations.
- **`blink`** – on for `interval_ms`, off for `interval_ms`, repeated.
- **`pulse`** – on for `duration_ms`, then off, then a gap of
  `max(100 ms, duration_ms / 3)` before the next pulse. The last pulse has no
  trailing gap.
- **`off`** – switches the LED off immediately, without any visible flash. This
  is what frequently repeating states such as `audio_stopped` should use.
- **`glow`** – a breathing effect over software PWM. Brightness follows a sine
  curve in 50 steps per cycle, from `min_brightness` up to `max_brightness` and
  back.

| Field | Applies to | Meaning |
| --- | --- | --- |
| `interval_ms` | `blink` | On-time, and off-time, of one blink. Required. |
| `duration_ms` | `pulse` | On-time per pulse. Required. Cleared on every other pattern type. |
| `repeat` | `blink`, `pulse`, `glow` | Number of complete cycles — one blink is on *and* off again. `0` or omitted means run until another state overrides this LED. |
| `cycle_ms` | `glow` | One full dark → bright → dark cycle. Minimum 500, default 2000, sensible range 1000–3000. |
| `min_brightness` | `glow` | 0.0–1.0, default 0.0. Must be smaller than `max_brightness`. |
| `max_brightness` | `glow` | 0.0–1.0, default 1.0. |

The schema repairs a pattern it cannot run rather than rejecting it, and logs
a warning saying so. A `pulse` without a usable `duration_ms` and a `glow` whose
`min_brightness` is not below its `max_brightness` both used to reach the
pattern coroutine, raise inside its task and leave the LED dark. Refusing the
config instead is worse: an invalid `leds.json` stops the service from starting
at all, and one binding on a default is cheaper than a box with no LEDs.

> **Software PWM:** as soon as one binding of an LED uses `glow`, the controller
> claims that pin as a `gpiozero.PWMLED` instead of a plain `LED`. This works on
> any standard Raspberry Pi GPIO pin and needs no wiring change. Very short
> cycles (< 500 ms) can flicker because of OS scheduling, which is why the
> schema enforces the 500 ms floor; at the usual 1–3 s it is invisible.

---

## 6. Pattern Execution

`LEDManager` owns one `LEDController` per configured LED. On
`initialize_leds()` it sets the gpiozero pin factory to `LGPIOFactory` once and
then builds the controllers. `LGPIOFactory` talks to `/dev/gpiochip0` and, unlike
`NativeFactory`, supports software PWM inside a container without a `pigpiod`
daemon.

Per state change:

1. `LEDManager.apply_state(logical_state)` calls `apply_pattern()` on every
   controller concurrently.
2. The controller returns immediately if the LED is disabled, if GPIO was never
   available, or if it has no binding for that state.
3. Otherwise the pattern currently running on that LED is cancelled — via a
   cancel event first, and hard-cancelled after one second if it does not stop —
   and the new one is started as its own task.
4. `solid`, `off` and `glow` are treated as *persistent*: their task finishing
   does not clear the LED's remembered state, because the light stays as it is.
   `blink` and `pulse` release the state when they finish.

Re-applying the state an LED is already showing does nothing. That matters for
`audio/status`, which repeats while a track plays: without the check every one
of those messages restarted the solid pattern and logged a state change, about
once a second.

Every pattern coroutine turns the LED off in its `finally` block, so a cancelled
blink or pulse never leaves the LED stuck on. If a pattern raises inside its
task, the controller logs `pattern_task_failed` and forgets the state, so the
next attempt is not suppressed as a repeat.

States are applied in the order the broker delivers them. The MQTT client
awaits its message handler instead of dispatching each message into its own
task, so the receive loop hands over one message at a time.

Each controller additionally holds a lock around "cancel the old pattern, start
the new one". Two states arriving three milliseconds apart — `rfid/presence`
and `rfid/tag-scanned` do exactly that — could otherwise both cancel, both
start, and leave the first pattern running with nothing owning it. `POST /test`
takes the same lock, which is how a real state change preempts a test blink.

The gpiozero pin factory is set once per process. It used to be re-created on
every reload, and gpiozero never closes the factory it replaces, so each save in
the WebUI leaked an open `/dev/gpiochip0` handle.

### Development without hardware

`DISABLE_GPIO=true` skips pin initialisation entirely. The flag is read once
into `EnvConfig` and passed down to `LEDManager`, so nothing below it reaches
for the environment on its own. If GPIO is available but a pin cannot be
claimed — wrong group id, pin already in use — the controller logs
`gpio_unavailable_fallback` and stays inert instead of failing startup.

---

## 7. Dependencies

- **Hardware:** GPIO pins on the Raspberry Pi, reached through
  `/dev/gpiochip0` and `/dev/gpiomem`.
- **MQTT broker:** Mosquitto, host and port from the root `.env`.
- **Publishing services:** audio (`audio/status`), RFID (`rfid/*`), button
  (`button/raw-event`), backend (`system/*`, `backend/unreachable`,
  `led/usage-denied`).
- **Backend:** owns `leds.json`, triggers `led/config/reload`, proxies the LED
  test to `POST /test`.
- **WebUI:** the admin panel where states, patterns and pins are assigned.
- **shared-lib:** `BaseMQTTClient`, `JsonConfigManager`, `load_env`,
  `setup_structlog`, `get_version`.

---

## 8. Deployment

The service runs as the compose service `led` under the `led` profile, so a box
without LEDs simply never starts it.

| Setting | Value | Why |
| --- | --- | --- |
| `devices` | `/dev/gpiochip0`, `/dev/gpiomem` | The only host access this container gets. |
| `user` | `${HOST_UID}:${GPIO_GID}` | Runs unprivileged; the gpio group is what grants pin access. |
| `group_add` | `${GPIO_GID}` | Same group again, so lgpio can open the chip. |
| `volumes` | `config:ro` | The backend writes the file, the service only reads it. |
| `ports` | `127.0.0.1:8004:8000` | Health and test endpoint, bound to localhost: `POST /test` is unauthenticated, and the backend reaches the service over the compose network as `http://led:8000`. Diagnosis with `curl` on the box stays possible. |
| `logging` | `json-file`, 10 MB × 3 | The driver default is unlimited growth, and the box runs from an SD card. |
| `depends_on` | `backend` healthy | Avoids a burst of `backend_unreachable` at boot. |

Environment: `MQTT_BROKER`, `MQTT_PORT`, `MINABOX_DEVICE_ID`, `LOG_LEVEL`,
`DISABLE_GPIO`, `GPIOZERO_PIN_FACTORY=lgpio`.

The image is built in two stages. The builder compiles the `lg` C library from
source and installs `lgpio` against it, because PyPI publishes no `lgpio` wheel
for CPython 3.13; the runtime stage keeps only `liblgpio.so` and the installed
site-packages.

Shutdown is handled on `SIGTERM`/`SIGINT`: the API server stops, the MQTT loop
is stopped and awaited, then every controller turns its LED off, closes the pin
and leaves it as an input with a pull-down — so nothing stays lit after
`docker compose down`.

---

## 9. Errors & Logging

Logging is structlog through `shared_lib.logging.setup_structlog`: human
readable at `DEBUG`, JSON from `INFO` upwards.

The events worth grepping for:

| Event | Level | Meaning |
| --- | --- | --- |
| `led_state_changed` | info | A pattern was started; carries `led_id`, `logical_state`, `pattern_type`. |
| `gpio_unavailable_fallback` | warning | A pin could not be claimed; that LED stays dark for the rest of the process. |
| `no_leds_available` | warning | LEDs are configured but not one of them holds a pin — check `GPIO_GID` and the device mapping. |
| `duplicate_led_gpio` / `duplicate_led_id` | warning | Two entries collide; the second one loses. |
| `pattern_task_failed` | error | A pattern raised while running; that LED is dark until the next state. |
| `solid_pattern_duration_ignored` | warning | A `solid` binding still carries `duration_ms`. |
| `blink_interval_defaulted` / `pulse_duration_defaulted` / `glow_brightness_range_invalid` | warning | The schema repaired a binding the WebUI produced; fix it there to silence this. |
| `config_reload_failed` | error | The reload failed; the previous configuration stays active and `config/response` reports it. |
| `state_derivation_failed` | error | A payload could not be parsed. |
| `led_pin_pulldown_failed` | warning | Cleanup could not reset the pin; harmless at shutdown. |

Behaviour on failure:

- **A reload that fails:** the running configuration is kept and
  `config/response` reports `success: false`.
- **Invalid config file at startup:** `load_app_config()` raises and the process
  exits, so the container restarts rather than running with no LEDs at all.
- **Broker unreachable:** startup continues. The base client retries forever and
  `/health` reports `degraded` in the meantime.
