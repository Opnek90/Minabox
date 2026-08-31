# RFID Service

The RFID service is the box's hardware layer for RFID cards. It talks to the
reader, turns card placement and removal into MQTT events, and does nothing
else — the backend decides what a card means. It is the first link in the
chain that starts playback when a child puts a card on the box.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-rfid` |
| Source | `services/rfid-service/src/rfid_service/` |
| Version | `services/rfid-service/VERSION` |
| Compose service | `rfid` (profile `rfid`) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn |
| Speaks | MQTT; REST on container port `8000`, host `127.0.0.1:8001` |
| Needs | MQTT broker, `/dev/i2c-1` (I2C reader), healthy backend at start |

## 1. Purpose & Responsibility

The service owns communication with the configured RFID reader and translates
reader state changes into MQTT events. Supported readers are the PN532 (I2C,
SPI or UART) and a deterministic mock reader for development and tests.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Which playlist a card belongs to | backend (`tags` table) |
| Starting, stopping or resuming playback | backend → audio service |
| Storing which cards exist | backend |
| Deciding when learning mode begins | backend, on a WebUI request |
| Any user-facing operation | webui |

The service knows one thing: which UID is on the reader right now. Every
consumer builds its own meaning on top of that. This boundary is what allows
the reader hardware to be swapped without touching playback logic.

Consumers of its events today: backend (`rfid_handler`), LED service (card
feedback and the retained presence) and display service.

## 2. File & Folder Structure

```
services/rfid-service/
├── config/rfid.json                     runtime configuration (see 5.2)
├── Dockerfile                           two-stage python:3.13-slim build
├── requirements.txt / pyproject.toml    dependencies, ruff and mypy settings
├── VERSION                              service version, single source
├── src/rfid_service/
│   ├── main.py                          process lifecycle: startup order,
│   │                                    signal handling, shutdown
│   ├── config.py                        loads env + config/rfid.json
│   ├── config_schema.py                 Pydantic schema of every tunable value
│   ├── exceptions.py                    ReaderNotFoundError, ReaderInitError,
│   │                                    ProtocolError
│   ├── core/
│   │   └── rfid_manager.py              ** the behaviour ** — scan loop, modes,
│   │                                    debounce, duplicate suppression,
│   │                                    reader recovery, all publishing
│   ├── infrastructure/
│   │   ├── mqtt_client.py               subscriptions, set-mode command,
│   │   │                                last will for presence
│   │   └── hardware/
│   │       ├── reader_interface.py      the RFIDReader ABC every reader implements
│   │       ├── reader_factory.py        reader_type → implementation
│   │       ├── pn532_reader.py          PN532 via pn532pi (I2C/SPI/UART)
│   │       └── mock_reader.py           hardware-free reader with a tag rhythm
│   ├── models/schemas.py                the MQTT payloads as Pydantic models
│   └── api/routes.py                    /health
└── tests/                               see section 8
```

Nearly all behaviour lives in `core/rfid_manager.py`. `main.py` only wires
things together, and everything under `infrastructure/hardware/` is
interchangeable by design.

## 3. Runtime Flow

**Startup order is deliberate.** `main.py` starts the MQTT client, publishes
`system/service-started`, creates the `RFIDManager` and its scan task, and only
then starts the HTTP server. The reader is *not* touched here: initialisation
happens inside the scan loop. Missing or miswired hardware therefore produces
an observable error status instead of a process that dies before it can report
anything.

The MQTT client connects in the background and retries forever, so an
unreachable broker does not fail startup either.

**The scan loop** (`RFIDManager.scan_loop`) runs until stopped and handles
every non-cancellation error inside itself — a loop that dies silently would
leave a service that looks healthy but no longer reacts to cards. Reader access
is blocking, so each read runs in an asyncio worker thread
(`asyncio.to_thread`). One pass:

1. No reader yet → try to initialise it, with exponential backoff between
   attempts (`init_retry_delay_ms` doubling up to `init_retry_max_delay_ms`).
   With `init_max_attempts: 0` this retries forever; a positive value stops the
   scan loop at the limit while the process and `/health` stay available.
2. Read the UID. A `HardwareError` reports an error status, waits
   `error_retry_delay_ms` and retries; after `reinit_after_read_errors`
   consecutive failures the reader is released and rebuilt from scratch.
3. A UID was read → see the state transitions below.
4. No UID → count towards the removal debounce.
5. Check the learning-mode timeout, prune the suppression history, sleep
   `scan_interval_ms`.

**State transitions**

| Situation | Result |
| --- | --- |
| New UID appears | `tag-scanned` (or `tag-scanned-learning`) + retained `presence: true` |
| Same UID keeps being read | nothing — presence has not changed |
| Same UID re-appears within `duplicate_suppression_ms` | suppressed |
| Empty reads reach `removal_debounce_reads` | `tag-removed` + retained `presence: false` |
| A different UID appears | treated as a new card, replacing the current one |

The removal debounce exists because RFID hardware drops single reads when a
card shifts slightly. Without it, playback would stop for a card that never
left the reader.

**Once the reader is up**, the service publishes the real-world state once:
a card already lying on the reader at boot is reported, an empty reader clears
the retained presence. The empty case currently emits `tag-removed` with an
empty `tag_id` before `presence: false` — consumers must tolerate this startup
marker.

**Learning mode** is entered only over MQTT. A scan in this mode publishes
`tag-scanned-learning` instead of `tag-scanned`, so assigning a card cannot
start playback at the same time. It falls back to normal after
`learning_timeout_s` without a scan, because a WebUI tab closed abruptly never
sends the "back to normal" command and would leave the box unable to play. The
mode is not persisted: every process start begins in normal mode.

**Shutdown** stops the API server, then the scan loop, then lets the manager
clear the presence and publish `status: idle`, and only then closes MQTT. The
order matters — no card event may race the farewell status, and a retained
`tag_present: true` left behind by a dead process can never be corrected.
Each step is granted `service.shutdown_timeout_s`.

## 4. Public Interfaces

All topics are namespaced `minabox/<device-id>/<domain>/<action>`. Payload
models are in `models/schemas.py`; timestamps are UTC ISO-8601 strings,
`tag_id` is an uppercase hex UID without separators, and `reader_id` is
`<reader_type>_<interface>` (e.g. `pn532_i2c`).

### 4.1 MQTT — published

| Topic | Retained | QoS | Payload |
| --- | --- | --- | --- |
| `.../rfid/tag-scanned` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-scanned-learning` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-removed` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/presence` | **yes** | 1 | `tag_present`, `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/status` | **yes** | 1 | `state`, `reader_id`, `error`, `timestamp` |
| `.../system/service-started` | no | 1 | `service` |

`presence` is the authoritative current state of the reader. It and `status`
are published with `remember=True`, so the client republishes them after a
reconnect — a broker that restarted would otherwise lose the retained message
and nobody would ever refresh it.

The service registers an MQTT **last will** that publishes retained
`presence: false` if the connection ends unexpectedly. MQTT fixes the will
payload when the session opens, so its `timestamp` is the connection time, not
the time of death: consumers must read `tag_present` and ignore the age.

`status.state` is one of `idle`, `normal`, `learning`, `error`.

### 4.2 MQTT — subscribed

| Topic | Payload | Effect |
| --- | --- | --- |
| `.../rfid/cmd/set-mode` | `{"mode": "normal"}` or `{"mode": "learning"}` | switches the operating mode |
| `.../config/general` | general config payload containing `log_level` | changes the log level at runtime |

Malformed JSON and unknown modes are logged and ignored. Valid mode values are
derived from the `Mode` type, so the literal and the validation cannot drift
apart. Reader configuration is **not** subscribable — it is read once at
process start.

The backend publishes `cmd/set-mode` on behalf of the WebUI via
`POST /api/v1/rfid/learning-mode` (`backend_service/api/routes_rfid.py`).

### 4.3 REST

`GET /health` — container port `8000`, published on the host only as
`127.0.0.1:8001` because the endpoint is unauthenticated.

It **always** answers HTTP 200 and expresses trouble in the body: a container
merely waiting for the broker or for hardware should be visible, not killed by
the health check into a restart loop.

```json
{
  "status": "healthy | degraded",
  "service": "rfid",
  "version": "0.2.4",
  "device_id": "box1",
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883,
  "reader": {
    "reader_id": "pn532_i2c",
    "reader_ready": true,
    "scan_loop_alive": true,
    "mode": "normal",
    "tag_present": false,
    "tag_id": null,
    "last_scan_age_s": 0.204,
    "last_error": null
  }
}
```

`status` is `healthy` only when MQTT is connected **and** the reader is ready
**and** the scan loop is alive; otherwise `degraded`.

## 5. Configuration

### 5.1 Environment

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `MQTT_BROKER` | yes | — | broker hostname |
| `MQTT_PORT` | yes | — | broker port |
| `MINABOX_DEVICE_ID` | yes | — | first segment of every topic |
| `LOG_LEVEL` | yes | — | initial log level |
| `API_PORT` | no | `8000` | REST port; also the Dockerfile `EXPOSE` and health-check port |

Compose also passes `DISABLE_GPIO`; this service does not read it (it has no
GPIO — use `reader_type: mock` instead).

### 5.2 `config/rfid.json`

Validated with Pydantic at startup; invalid configuration prevents startup.
Bind-mounted from `services/rfid-service/config/`. It is read **once**, so
every change here needs a container restart. Nothing in the business logic is
hard-coded — a box is re-tuned by editing this file.

| Key | Default | Bounds | Meaning |
| --- | --- | --- | --- |
| `reader.reader_type` | required | `pn532`, `mock` | reader implementation |
| `reader.interface` | required | `i2c`, `spi`, `uart` | hardware interface |
| `reader.scan_interval_ms` | 200 | 20–5000 | delay between scan attempts |
| `reader.duplicate_suppression_ms` | 2000 | 0–60000 | window suppressing a rapid remove/re-place of the same UID |
| `reader.removal_debounce_reads` | 3 | 1–50 | consecutive empty reads before removal counts; `1` disables the debounce |
| `reader.error_retry_delay_ms` | 5000 | 100–300000 | pause after a read error |
| `reader.init_retry_delay_ms` | 2000 | 100–300000 | first initialisation retry delay |
| `reader.init_retry_max_delay_ms` | 60000 | 100–3600000 | upper bound of the backoff |
| `reader.init_max_attempts` | 0 | ≥ 0 | initialisation attempts; `0` = forever |
| `reader.reinit_after_read_errors` | 5 | ≥ 0 | consecutive read errors before the reader is rebuilt; `0` disables it |
| `reader.pn532.i2c_bus` | 1 | 0–1 | I2C bus (Raspberry Pi: 1) |
| `reader.pn532.spi_device` | 0 | 0–1 | SPI chip-select line |
| `reader.pn532.uart_port` | `/dev/ttyS0` | — | serial device |
| `reader.pn532.passive_activation_retries` | 2 | 0–255 | PN532 retries per read; keep low, the call blocks for the whole attempt and stalls the scan loop |
| `reader.mock.tags` | `["04A224BC19", "DEADBEEF01"]` | — | UIDs the mock reader reports, in order |
| `reader.mock.hold_reads` | 10 | ≥ 1 | reads a mock card stays on the reader |
| `reader.mock.gap_reads` | 10 | ≥ 0 | empty reads between two mock cards |
| `modes.learning_timeout_s` | 300 | 0–86400 | idle seconds before learning mode reverts; `0` disables |
| `service.shutdown_timeout_s` | 5.0 | 0–120 | time granted to each background task on shutdown |

## 6. Dependencies

**Hardware.** A PN532 reader on I2C, SPI or UART. Compose passes only
`/dev/i2c-1` into the container and runs it as `${HOST_UID}:${I2C_GID}`, so
the process may open the bus without being root. SPI or UART operation needs
the matching device added to the compose entry. The display service shares
`/dev/i2c-1`.

**Python.** `fastapi` + `uvicorn` (health endpoint), `pydantic` (config and
payload validation), `aiomqtt` via `shared_lib.mqtt.BaseMQTTClient`,
`structlog`, and `pn532pi` for the reader. `pn532pi` is imported lazily inside
the factory, so a machine without the library can still run the service with
`reader_type: mock`.

**Services.** The MQTT broker is required, but its absence only degrades the
service — it keeps scanning and reconnects on its own. Compose declares
`depends_on: backend (service_healthy)` for ordering; at runtime the backend
is a consumer, not a dependency.

**Shared-lib** supplies the environment loader, the JSON config loader, the
self-healing MQTT base client (subscriptions, reconnect, status replay, general
config) and structlog setup. A change there affects every service — see
[shared-lib](../shared-lib/README.md).

## 7. Errors, Health & Logging

**Error codes** in `status.error` and `/health`'s `last_error`:

| Code | Raised when |
| --- | --- |
| `reader_not_found` | the reader hardware was not detected (`ReaderNotFoundError`) |
| `reader_init_failed` | initialisation failed for any other reason |
| `read_timeout` | a read failed; counts towards `reinit_after_read_errors` |

**The container health check is not a readiness check.** Both the Dockerfile
and compose call `curl -f .../health`, and the endpoint always returns 200 —
so container health means "the HTTP server is listening", not "the reader
works". Judge the reader by the JSON `status` field or by the retained
`rfid/status` topic, never by `docker ps`.

**Log events worth grepping** (structlog, JSON in production):
`reader_ready`, `reader_init_failed`, `reader_init_giving_up`,
`reader_reinit_triggered`, `scan_hardware_error`, `tag_scanned`,
`tag_removed`, `mode_changed`, `learning_mode_timeout`. Suppressed scans and
pending removals are logged at DEBUG (`tag_scan_suppressed`,
`tag_removal_pending`) — that pair is the first thing to look at when cards
behave erratically.

## 8. Development & Tests

**Without hardware.** Set `reader_type: "mock"` in `config/rfid.json`. The
mock reader reports each configured UID for `hold_reads` reads, then
`gap_reads` empty reads — a realistic rhythm rather than a new card on every
read, which is what makes debounce and suppression testable.

**Tests** need no hardware and no broker:

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/rfid-service/tests -q
```

| File | Covers |
| --- | --- |
| `test_rfid_manager.py` | the state machine: placement, resting card, debounce, duplicate suppression, learning mode and its timeout, reader recovery, boot state, retained flags |
| `test_mqtt_client.py` | subscription list, set-mode validation, the presence last will |
| `test_health_endpoint.py` | health before the manager exists, degraded and healthy cases, 200 without a broker |
| `test_mock_reader.py` | the mock's hold/gap rhythm and edge cases |
| `rfid_test_doubles.py` | `FakeMQTT` (records publishes) and `ScriptedReader` (a reader driven by a list of reads) |

`ScriptedReader` is the reason the manager takes a *reader factory* rather than
a reader instance: tests script hardware faults and recovery without any
hardware.

**Lint and build:**

```bash
.venv/bin/ruff check services/rfid-service
```

```bash
./scripts/build-local.sh rfid
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add a reader type (RC522, …) | new `infrastructure/hardware/<name>_reader.py` implementing `RFIDReader` | branch in `reader_factory.py`, the `Literal` in `config_schema.ReaderConfig.reader_type`, a config sub-model like `PN532Config`, `config/rfid.json`, a test |
| change scan/debounce/suppression behaviour | `core/rfid_manager.py` (`_handle_tag_detected`, `_handle_no_tag`) | `config_schema.py` if a new tunable appears — never hard-code a timing |
| add a tunable value | `config_schema.py` (with `Field` bounds and a description) | `config/rfid.json`, the table in 5.2, the place that reads it |
| add or change an MQTT event | `models/schemas.py`, then the `_publish_*` method in `rfid_manager.py` | table in 4.1, and every consumer (backend `rfid_handler`, LED `state_manager`, display `main.py`) |
| accept a new MQTT command | `_build_subscription_topics` and `on_message` in `infrastructure/mqtt_client.py` | a handler on `RFIDManager`, the callback wiring in `main.py`, table in 4.2 |
| add an operating mode | the `Mode` literal in `core/rfid_manager.py` | `set_mode`, the `state` literal in `RFIDStatusEvent`, the backend endpoint that triggers it |
| expose more diagnostics | `RFIDManager.status_snapshot()` | `api/routes.py`, section 4.3 |
| change reader hardware wiring | `config/rfid.json` (`interface`, `pn532.*`) | the `devices:` and `user:` entries of the `rfid` service in `docker-compose.yml` |

### Invariants

- **The service never learns what a card means.** No playlist, track or user
  concept may enter this codebase; if a change seems to need one, it belongs
  in the backend.
- **`presence` stays retained and stays published with `remember=True`.**
  It is how the LED service recovers its state after a config reload without
  waiting for the next card event, and how subscribers survive a broker
  restart.
- **The last will and the explicit clear on shutdown both stay.** A retained
  `tag_present: true` from a dead process can never be corrected by anyone.
- **Reader initialisation stays inside the scan loop.** Moving it into startup
  would make missing hardware fatal and destroy the ability to diagnose it.
- **`/health` keeps returning 200 in every state.** A non-200 turns a
  diagnosable box into a restart loop.
- **The scan loop swallows every non-cancellation exception.** A dying loop is
  invisible; an error status is not.
- **Timings come from config, never from a literal in the logic.** The whole
  point of `config_schema.py` is that a box can be re-tuned without a rebuild.
- **`tag-scanned` and `tag-removed` stay non-retained.** They are events, not
  state; retaining them would replay a card scan at every subscriber restart.

## 10. Related Documents

- [`services/rfid-service/README.md`](../../../services/rfid-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/backend/README.md`](../backend/README.md) — the consumer of the card events
- [`docs/services/led/README.md`](../led/README.md) — consumer of `presence`
- [`docs/services/shared-lib/README.md`](../shared-lib/README.md) — MQTT base client and config loading
