# Button Service

Reads the physical inputs — push buttons and rotary encoders — classifies them
into normalised raw events, maps those to logical actions and publishes the
result over MQTT. It never decides what an action *means*: `play_pause` is a
name, and what happens next is the backend's and the audio service's business.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-button` |
| Source | `services/button-service/src/button_service/` |
| Version | `services/button-service/VERSION` |
| Compose service | `button` (profile `button`) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn, gpiozero + lgpio |
| Speaks | MQTT; REST on container port `8000`, host `127.0.0.1:8005` |
| Needs | MQTT broker, `/dev/gpiochip0` + `/dev/gpiomem`, `config/buttons.json` |

## 1. Purpose & Responsibility

Turn GPIO edges into named actions, and nothing more. The classification of
"what the user did" (short, long, double, rotate) belongs here; the meaning of
the result does not.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| What `play_pause` does | backend → audio service |
| Whether playback is even running | audio service |
| Owning `config/buttons.json` | backend — it writes the file through `PUT /api/config/buttons` |
| Checking pins against other services | nobody — see the pin-conflict note in 6 |

## 2. File & Folder Structure

```
services/button-service/
├── Dockerfile                     two-stage build; LG_ALERT_POLL_NS build arg (see 6)
├── config/buttons.json            button definitions, bind-mounted read-write
├── VERSION                        service version, single source
├── src/button_service/
│   ├── main.py                    entry point: startup, shutdown, config callbacks
│   ├── config.py                  loads the environment into an AppConfig
│   ├── config_schema.py           ** the config contract ** — ButtonConfig and its
│   │                              basic/advanced mode validation
│   ├── config_manager.py          thin wrapper around shared_lib.JsonConfigManager
│   ├── exceptions.py              service-specific exception hierarchy
│   ├── core/
│   │   ├── events.py              RawButtonEvent, EventType
│   │   ├── state_machine.py       ** the classification ** — gpiozero callbacks →
│   │   │                          short/long/double press, encoder detents
│   │   ├── gpio_input_manager.py  owns the gpiozero devices, one per configured pin
│   │   └── event_processor.py     ** the mapping ** — debounce, action lookup, dispatch
│   ├── models/schemas.py          HealthState: what /health reports
│   ├── infrastructure/mqtt_client.py  subscriptions and the config API
│   └── api/routes.py              GET /health
└── tests/                         see section 8
```

`core/logic.py` exists but is empty and unused.

## 3. Runtime Flow

```text
GPIO edge
  │  gpiozero callback, runs on a background thread
  ▼
PressClassifier / EncoderRotationEmitter / EncoderSwitchEmitter
  │  loop.call_soon_threadsafe(queue.put_nowait, event)
  ▼
asyncio.Queue[RawButtonEvent]          (unbounded FIFO)
  │
  ▼
run_event_processor()
  ├─ look up the button by source_id in the current config
  ├─ debounce            → drop the event entirely if still in cooldown
  ├─ publish raw-event   → always, even for disabled buttons
  ├─ if disabled         → stop here
  ├─ resolve the action  → basic: `action`, advanced: `actions[event_type]`
  ├─ publish the action  → minabox/<device-id>/button/<action>
  └─ volume_up/down      → additionally straight to the audio service
```

Three properties of this pipeline are deliberate:

- **The hardware layer never touches MQTT.** Callbacks arrive on gpiozero's own
  threads and are handed to the event loop through `call_soon_threadsafe()`.
- **The queue makes rapid input deterministic.** Events are processed strictly
  in order, one at a time.
- **The raw event is published before the `enabled` check.** The WebUI hardware
  test mode has to show feedback for a button the user switched off, so the raw
  event goes out either way and only the action dispatch is skipped.

### 3.1 Raw events

| Event type | Source | Produced when |
| --- | --- | --- |
| `short_press` | push button | released, and no second press within 400 ms |
| `long_press` | push button | held for 1 s (`hold_time`); suppresses `short_press` |
| `double_press` | push button | second release within 400 ms of the first |
| `rotate_cw` | encoder | one clockwise detent |
| `rotate_ccw` | encoder | one counter-clockwise detent |
| `press` | encoder switch (`sw`) | switch pressed |

Timing constants are compiled in, **not** configurable:

| Constant | Value | Where |
| --- | --- | --- |
| Double-press window | 400 ms | `state_machine.py:DOUBLE_PRESS_WINDOW_S` |
| Hold time for `long_press` | 1.0 s | `gpio_input_manager.py:push_hold_time_s` |
| Hardware bounce filter | 50 ms | `gpio_input_manager.py:push_bounce_time_s` |
| Action cooldown, push | 300 ms | `event_processor.py:DEBOUNCE_CONFIG` |
| Action cooldown, rotary | 0 ms | `event_processor.py:DEBOUNCE_CONFIG` |

Because a `short_press` is only emitted once the double-press window has
expired, **every short press is delayed by 400 ms** — including on buttons that
have no `double_press` mapping at all.

The cooldown is keyed on the *entry type*, not on the event type. An encoder's
switch therefore inherits the rotary setting of 0 ms and gets no cooldown.

## 4. Public Interfaces

All topics are built through `AppConfig.get_mqtt_topic(domain, action)` and
prefixed `minabox/<device-id>/`.

### 4.1 MQTT — published

**`button/<action>`** — one topic per mapped action, QoS 1, not retained.
Underscores in the action name become hyphens: `play_pause` →
`button/play-pause`.

```json
{ "source": "btn_1", "event_type": "short_press", "timestamp": "2026-02-14T13:30:00Z" }
```

Actions the backend understands
(`backend_service/core/handlers/button_handler.py`): `play-pause`, `next`,
`prev`, `volume-up`, `volume-down`, `mute` / `mute-toggle`,
`sleep-timer-toggle`, `repeat-cycle`, `shuffle-toggle`, `next-output-device`.
Any other action name is published but ignored by every subscriber.

**`button/raw-event`** — every accepted hardware event, before mapping, QoS 1,
not retained.

```json
{
  "button_id": "btn_1",
  "name": "Volume",
  "type": "rotary",
  "event_type": "rotate_cw",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

This topic is **not** debug-only: the LED service derives its `button_pressed`
state from it, and the backend forwards it to the WebUI over WebSocket for the
hardware test mode.

**`audio/volume-up`, `audio/volume-down`** — published directly, QoS 0, in
addition to the `button/...` topic. This bypasses the backend to keep volume
changes responsive; the backend's handler deliberately does nothing for these
two actions.

**`system/service-started`** — once on startup, with `remember=True`, so it is
republished after every reconnect. There is no matching last will.

**`button/config/response`** — result of a config operation. No service
subscribes to this topic today.

```json
{ "success": false, "error": "invalid_config", "timestamp": "..." }
```

### 4.2 MQTT — subscribed

| Topic | Effect |
| --- | --- |
| `button/config/reload` | re-read `config/buttons.json`, rebuild all GPIO devices |
| `button/config/update` | validate the payload, write it to disk, rebuild devices |
| `button/config/get` | answers `config/response` — **without the config** |
| `config/general` | apply a new log level (handled by `BaseMQTTClient`) |

Only `config/reload` is in use. The backend writes `buttons.json` itself
through `PUT /api/config/buttons` and then publishes the reload. Nothing in the
repository ever publishes `config/update` or `config/get`.

### 4.3 REST

`GET /health` on container port 8000, host `127.0.0.1:8005` — reachable for
diagnosis on the box but not from the network. The Docker health check only
asks whether the endpoint answers at all.

```json
{
  "status": "healthy",
  "service": "button",
  "version": "0.2.3",
  "device_id": "box1",
  "buttons_configured": 3,
  "buttons_available": 3,
  "gpio_enabled": true,
  "config_error": null,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`status` is `degraded` when the MQTT connection is down, when
`buttons_available` is below `buttons_configured` (a pin could not be claimed,
usually because another service owns it), or when `config_error` is set.

`gpio_enabled: false` (`DISABLE_GPIO=true`) is a setting, not a fault, and does
not make the service `degraded`.

## 5. Configuration

### 5.1 Environment

| Variable | Required | Note |
| --- | --- | --- |
| `MQTT_BROKER` | yes | |
| `MQTT_PORT` | yes | |
| `MINABOX_DEVICE_ID` | yes | topic prefix |
| `LOG_LEVEL` | yes | overridable at runtime via `config/general` |
| `DISABLE_GPIO` | no | `true` starts the service without any hardware |
| `API_PORT` | no | defaults to 8000 |
| `GPIOZERO_PIN_FACTORY` | set by compose | `lgpio`; also set explicitly in `gpio_input_manager.py` |

`EXPOSE` and the container health check are fixed at 8000, so changing
`API_PORT` also means changing the port mapping in `docker-compose.yml`.

### 5.2 `config/buttons.json`

Bind-mounted **read-write** from `services/button-service/config/`. Loaded at
startup and on every `config/reload`.

```json
{
  "buttons": [
    {
      "id": "btn_1",
      "name": "Volume",
      "mode": "advanced",
      "type": "rotary",
      "gpio": null,
      "clk": 24,
      "dt": 23,
      "sw": 25,
      "actions": {
        "rotate_cw": "volume_up",
        "rotate_ccw": "volume_down",
        "press": "mute_toggle"
      },
      "enabled": true
    },
    {
      "id": "btn_2",
      "name": "Play",
      "mode": "basic",
      "type": "push",
      "gpio": 13,
      "clk": null, "dt": null, "sw": null,
      "action": "play_pause",
      "actions": null,
      "enabled": true
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | internal identifier, also the `source` of every published event |
| `name` | display name for the WebUI and for `raw-event` |
| `mode` | `basic` → one `action` for every event type; `advanced` → per-event `actions` |
| `type` | `push` → needs `gpio`; `rotary` → needs `clk`, `dt`, `sw` (BCM numbering) |
| `action` | only in `basic` mode; `actions` must be absent |
| `actions` | only in `advanced` mode; `action` must be absent |
| `enabled` | `false` still publishes `raw-event`, but dispatches no action |

`ButtonConfig._validate_mode_and_type()` enforces these rules. Violating any of
them makes the whole file unloadable.

Behaviour worth knowing:

- **No mapping for an event type → nothing happens.** In `basic` mode every
  event type resolves to the same action, so a long press on a `play_pause`
  button also triggers `play_pause`.
- **Duplicate actions are allowed.** Two buttons may carry the same action; the
  service does not enforce uniqueness.
- **Pins are not checked against other services.** See 6.

## 6. Dependencies

**Hardware.** `/dev/gpiochip0` and `/dev/gpiomem`, plus membership in the
`gpio` group (`GPIO_GID` in `.env`); compose runs the container as
`${HOST_UID}:${GPIO_GID}` with `group_add`. The pin factory is `lgpio`.

- **Push button:** one leg to GPIO, the other to GND (internal pull-up); BCM
  number in `gpio`.
- **Rotary encoder:** CLK/DT on two GPIOs, SW on a third; BCM numbers in `clk`,
  `dt`, `sw`.

**CPU.** lgpio's alert thread polls, so every claimed pin costs CPU even when
nothing happens. The build pins that poll interval through the
`LG_ALERT_POLL_NS` build arg in the Dockerfile (2 ms, against upstream's
0.5 ms) — measured at roughly 3 % of one core instead of 8 % on a Pi 4.

**Pin conflicts.** No GPIO pin may appear in both `config/leds.json` and
`config/buttons.json`. Nothing validates this across services: whichever
service starts first claims the pin, the other logs `gpio_input_init_failed`
and leaves that button inactive while the rest keep working. `/health` then
reports `degraded` with `buttons_available` below `buttons_configured`. The
example config here only uses pins the default `leds.json` does not.

**Other services.** The backend owns the configuration and triggers
`config/reload`, and consumes `button/+` and `button/raw-event`. The LED
service consumes `button/raw-event`. The audio service receives `volume-up` /
`volume-down` directly. None is needed for startup.

**shared-lib.** `BaseMQTTClient`, `JsonConfigManager`, `load_env`,
`setup_structlog`, `get_version` — see [shared-lib](../shared-lib/README.md).

## 7. Errors, Health & Logging

| Situation | What happens |
| --- | --- |
| File missing or invalid **at startup** | logged as `config_load_failed`; the service starts with zero buttons and reports `config_error` on `/health` |
| File invalid on `config/reload` | the previous config stays active; `/health` reports `config_error`, because `config/response` has no subscriber |
| One GPIO pin unavailable | that button is skipped, the others keep working; `buttons_available` drops below `buttons_configured` |
| lgpio pin factory unusable | no hardware at all, but MQTT and the API stay up |
| MQTT broker unreachable | startup succeeds, `BaseMQTTClient` retries with backoff, publishes are dropped |

**Nothing in this table takes the process down.** That is deliberate: the WebUI
is the only way to repair a bad configuration, and it needs the service to
answer. Every one of these states is visible on `/health` instead.

Events worth grepping:

| Event | Level | Meaning |
| --- | --- | --- |
| `gpio_input_init_failed` | error | a pin could not be claimed; that button stays inactive — usually a pin that also appears in `leds.json` |
| `no_buttons_available` | warning | not one configured pin could be claimed — check `GPIO_GID` and `/dev/gpiochip0` |
| `gpio_init_skipped` | warning | running without button hardware at all |
| `config_load_failed` | error | `buttons.json` does not load; started with zero buttons |
| `button_debounced` | debug | event dropped by the cooldown |
| `action_triggered` | debug | action resolved and published |
| `event_no_mapping` | debug | event had no action for this event type |
| `event_processor_unknown_source` | warning | event for a `source_id` that is not in the current config |
| `config_reload_failed` | error | new config rejected, previous one kept |

## 8. Development & Tests

**Without hardware.** `DISABLE_GPIO=true` starts the service with no GPIO at
all; MQTT and `/health` stay up, so the mapping side can be exercised.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/button-service/tests -q
```

| File | Covers |
| --- | --- |
| `test_gpio_input_manager.py` | device construction per button type, a pin that cannot be claimed, `DISABLE_GPIO` |
| `test_health_and_startup.py` | startup with a broken config, configured vs. available counts, the degraded conditions |
| `button_test_doubles.py` | fake gpiozero devices and a recording MQTT client |

```bash
.venv/bin/ruff check services/button-service
```

```bash
./scripts/build-local.sh button
```

The build context is `./services`, not the service directory — the Dockerfile
copies `shared-lib` as well, so `docker build .` from inside
`services/button-service` cannot work. A plain `docker compose build` cannot
read the VERSION file and reports `0.0.0-dev`; `build-local.sh` passes the
build args properly and tags `:local`.

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add an action name | nothing here — actions are free-form strings in `buttons.json` | `button_handler.py` in the backend (otherwise it is published and ignored), the WebUI action list |
| add a raw event type | `core/events.py` (`EventType`) and `core/state_machine.py` | `DEBOUNCE_CONFIG` in `event_processor.py`, the `actions` keys in `config_schema.py`, the WebUI editor, the table in 3.1 |
| support a new input device | `core/gpio_input_manager.py` (device construction) and a classifier in `state_machine.py` | `type` literal and validation in `config_schema.py`, `test_gpio_input_manager.py` |
| change a timing constant | the constant named in the table in 3.1 | that table; consider whether it should become configuration instead |
| make a timing configurable | `config_schema.py` | `state_machine.py` / `gpio_input_manager.py`, the backend's config endpoint, the WebUI |
| add a field to a button | `config_schema.py` (with the mode/type validation) | `event_processor.py` if it affects dispatch, the backend's `PUT /api/config/buttons`, the WebUI editor, the table in 5.2 |
| publish an event elsewhere | `core/event_processor.py` (the dispatch tail) | the consumer, and section 4.1 |

### Invariants

- **The hardware layer never touches MQTT.** gpiozero callbacks run on their
  own threads; everything crosses into the event loop through
  `call_soon_threadsafe`.
- **`raw-event` is published before the `enabled` check.** The WebUI hardware
  test depends on seeing events from a disabled button.
- **A bad configuration must not stop the service.** The WebUI is the only
  repair path and it needs the service to answer; report through `/health`
  instead.
- **One pin claimed by another service degrades one button, not the service.**
- **Volume goes straight to audio as well as through `button/`.** Routing it
  only through the backend was noticeably slower; the backend's handler ignores
  those two actions on purpose.
- **Events are processed one at a time, in order.** The queue is what makes a
  fast double-press deterministic.
- **`config/buttons.json` is the backend's to write.** The `config/update`
  topic exists but is unused; do not build new writers on it without deciding
  who owns the file.

## 10. Related Documents

- [`services/button-service/README.md`](../../../services/button-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/backend/README.md`](../backend/README.md) — consumer of the actions, owner of the configuration
- [`docs/services/led/README.md`](../led/README.md) — consumer of `raw-event`, and the other claimant of GPIO pins
- [`docs/services/audio/README.md`](../audio/README.md) — direct recipient of the volume commands
