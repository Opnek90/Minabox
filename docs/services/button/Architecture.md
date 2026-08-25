# Button Service – Architecture

Reads physical inputs (push buttons, rotary encoders), classifies them into
normalised raw events, maps those to logical actions and publishes the result
over MQTT. It never decides what an action *means* – `play_pause` is a name,
and what happens next is the backend's and the audio service's business.

Status: version 0.1.2. Known weaknesses and what to do about them:
[GoLive-Review.md](GoLive-Review.md).

---

## 1. Files

Path: `services/button-service/src/button_service/`

```text
button_service/
├── main.py                    # Entry point: startup, shutdown, config callbacks
├── config.py                  # Loads env vars + buttons.json into an AppConfig
├── config_schema.py           # Pydantic models: ButtonConfig, EnvConfig, AppConfig
├── config_manager.py          # Thin wrapper around shared_lib.JsonConfigManager
├── exceptions.py              # Service-specific exception hierarchy
├── core/
│   ├── events.py              # RawButtonEvent, EventType
│   ├── state_machine.py       # Turns gpiozero callbacks into raw events
│   ├── gpio_input_manager.py  # Owns the gpiozero devices, one per configured pin
│   └── event_processor.py     # Debounce, mapping, MQTT dispatch
├── infrastructure/
│   └── mqtt_client.py         # Extends shared_lib.BaseMQTTClient
└── api/
    └── routes.py              # FastAPI: GET /health
```

`core/logic.py`, `models/__init__.py` and `models/schemas.py` exist but are
empty and unused.

---

## 2. Runtime flow

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
  test mode has to show feedback for a button the user has switched off, so the
  raw event goes out either way and only the action dispatch is skipped.

---

## 3. Raw events

| Event type | Source | Produced when |
|---|---|---|
| `short_press` | push button | released, and no second press within 400 ms |
| `long_press` | push button | held for 1 s (`hold_time`); suppresses `short_press` |
| `double_press` | push button | second release within 400 ms of the first |
| `rotate_cw` | encoder | one clockwise detent |
| `rotate_ccw` | encoder | one counter-clockwise detent |
| `press` | encoder switch (`sw`) | switch pressed |

Timing constants are compiled in, not configurable:

| Constant | Value | Where |
|---|---|---|
| Double-press window | 400 ms | `state_machine.py:DOUBLE_PRESS_WINDOW_S` |
| Hold time for `long_press` | 1.0 s | `gpio_input_manager.py:push_hold_time_s` |
| Hardware bounce filter | 50 ms | `gpio_input_manager.py:push_bounce_time_s` |
| Action cooldown, push | 300 ms | `event_processor.py:DEBOUNCE_CONFIG` |
| Action cooldown, rotary | 0 ms | `event_processor.py:DEBOUNCE_CONFIG` |

Because a `short_press` is only emitted once the double-press window has
expired, **every short press is delayed by 400 ms** – including on buttons that
have no `double_press` mapping at all. See GoLive-Review 1.5.

The cooldown is keyed on the *entry type*, not on the event type. An encoder's
switch therefore inherits the rotary setting of 0 ms and gets no cooldown at
all. See GoLive-Review 1.6.

---

## 4. MQTT interface

All topics are built through `AppConfig.get_mqtt_topic(domain, action)` and are
prefixed with `minabox/<device-id>/`.

### 4.1 Published

**`button/<action>`** – one topic per mapped action, QoS 1, not retained.
Underscores in the action name become hyphens: `play_pause` →
`button/play-pause`.

```json
{
  "source": "btn_1",
  "event_type": "short_press",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

Actions the backend understands (`backend_service/core/handlers/button_handler.py`):
`play-pause`, `next`, `prev`, `volume-up`, `volume-down`, `mute` / `mute-toggle`,
`sleep-timer-toggle`, `repeat-cycle`, `shuffle-toggle`, `next-output-device`.
Any other action name is published but ignored by every subscriber.

**`button/raw-event`** – every accepted hardware event, before mapping, QoS 1,
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

This topic is **not** debug-only. The LED service derives its `button_pressed`
state from it, and the backend forwards it to the WebUI over WebSocket for the
hardware test mode.

**`audio/volume-up`, `audio/volume-down`** – published directly, QoS 0, in
addition to the `button/...` topic. This bypasses the backend to keep volume
changes responsive; the backend's handler deliberately does nothing for these
two actions.

**`system/service-started`** – once on startup, with `remember=True`, so it is
republished after every reconnect. There is no matching last will.

**`button/config/response`** – result of a config operation. No service
subscribes to this topic today.

```json
{ "success": false, "error": "invalid_config", "timestamp": "..." }
```

### 4.2 Subscribed

| Topic | Effect |
|---|---|
| `button/config/reload` | Re-read `config/buttons.json`, rebuild all GPIO devices |
| `button/config/update` | Validate the payload, write it to disk, rebuild devices |
| `button/config/get` | Answers `config/response` – **without the config** |
| `config/general` | Apply a new log level (handled by `BaseMQTTClient`) |

Only `config/reload` is in use. The backend writes `buttons.json` itself
through `PUT /api/config/buttons` and then publishes the reload. Nothing in the
repository ever publishes `config/update` or `config/get`.

---

## 5. Configuration

### 5.1 Environment

| Variable | Required | Note |
|---|---|---|
| `MQTT_BROKER` | yes | |
| `MQTT_PORT` | yes | |
| `MINABOX_DEVICE_ID` | yes | topic prefix |
| `LOG_LEVEL` | yes | overridable at runtime via `config/general` |
| `DISABLE_GPIO` | no | `true` starts the service without any hardware |

`EnvConfig` declares an `api_port` field, but `load_env()` is called without
optional defaults, so no environment variable ever reaches it. The API port is
always 8000.

### 5.2 `config/buttons.json`

Bind-mounted read-write from `services/button-service/config/`. Loaded at
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
      "clk": null,
      "dt": null,
      "sw": null,
      "action": "play_pause",
      "actions": null,
      "enabled": true
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Internal identifier, also the `source` of every published event |
| `name` | Display name for the WebUI and for `raw-event` |
| `mode` | `basic` → one `action` for every event type; `advanced` → per-event `actions` |
| `type` | `push` → needs `gpio`; `rotary` → needs `clk`, `dt`, `sw` (BCM numbering) |
| `action` | Only in `basic` mode; `actions` must be absent |
| `actions` | Only in `advanced` mode; `action` must be absent |
| `enabled` | `false` still publishes `raw-event`, but dispatches no action |

`ButtonConfig._validate_mode_and_type()` enforces these rules. Violating any of
them makes the whole file unloadable.

Behaviour worth knowing:

- **No mapping for an event type → nothing happens.** In `basic` mode every
  event type resolves to the same action, so a long press on a `play_pause`
  button also triggers `play_pause`.
- **Duplicate actions are allowed.** Two buttons may carry the same action; the
  service does not enforce uniqueness.
- **Pins are not checked against other services.** A GPIO that also appears in
  the LED service's `leds.json` will be claimed by whichever service starts
  first, and the other one fails – see below.

### 5.3 Failure behaviour

| Situation | What happens today |
|---|---|
| File missing or invalid **at startup** | `ConfigError` propagates, the process exits, Docker restarts it – a restart loop |
| File invalid on `config/reload` | The previous config stays active, `config/response` reports the failure (nobody listens) |
| One GPIO pin unavailable | **All** buttons are dropped, and the pins already claimed stay claimed |
| MQTT broker unreachable | Startup succeeds, `BaseMQTTClient` retries with backoff, publishes are dropped |

The GPIO row is the dangerous one: the service logs a warning, sets its device
manager to `None` without closing it, keeps holding the pins, and still reports
`healthy`. Only a container restart recovers. See GoLive-Review 1.1 and 1.2.

---

## 6. REST API

`GET /health` on port 8000 (exposed as `8005` on the host). Used by the Docker
health check, which only checks that the endpoint answers at all.

```json
{
  "status": "healthy",
  "service": "button",
  "version": "0.1.2",
  "device_id": "box1",
  "buttons_configured": 3,
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`status` is `degraded` only when the MQTT connection is down. `buttons_configured`
counts entries in the JSON file, not devices that actually hold a pin – a
service with no working GPIO at all still reports `healthy`.

---

## 7. Dependencies

- **Hardware:** `/dev/gpiochip0`, plus membership in the `gpio` group
  (`GPIO_GID` in `.env`). The pin factory is `lgpio`, set both by
  `GPIOZERO_PIN_FACTORY` and explicitly in `gpio_input_manager.py`.
  `RPi.GPIO` is listed in `requirements.txt` but never imported.
- **MQTT broker:** Mosquitto, host and port from the root `.env`.
- **Backend:** owns the button configuration and triggers `config/reload`;
  consumes `button/+` and `button/raw-event`.
- **LED service:** consumes `button/raw-event` for its `button_pressed` state.
- **Audio service:** receives `volume-up` / `volume-down` directly.
- **shared-lib:** `BaseMQTTClient`, `JsonConfigManager`, `load_env`,
  `setup_structlog`, `get_version`.

---

## 8. Logging

structlog, JSON, level from `LOG_LEVEL` and changeable at runtime via
`config/general`. The events worth grepping for:

| Event | Level | Meaning |
|---|---|---|
| `gpio_input_init_failed` | error | A pin could not be claimed – **all** buttons are then dropped |
| `gpio_init_skipped` | warning | Running without button hardware |
| `button_debounced` | debug | Event dropped by the cooldown |
| `action_triggered` | debug | Action resolved and published |
| `event_no_mapping` | debug | Event had no action for this event type |
| `event_processor_unknown_source` | warning | Event for a `source_id` that is not in the current config |
| `config_reload_failed` | error | New config rejected, previous one kept |
