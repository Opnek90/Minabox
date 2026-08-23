# RFID Service – Architecture

## 1. Purpose & Responsibility

The RFID service is solely responsible for talking to RFID reader hardware and
translating tag events into standardised MQTT events. It knows nothing about
playlists or audio details; it only reports tag information and status.

Goals:

- Abstract support for different readers (PN532 today, further models later)
  without hard-wired driver implementations.
- Two operating modes:
  1. **Learning mode** – capture new tags and report them to Backend/WebUI.
  2. **Normal mode** – monitor tags continuously and indirectly trigger playback.

Out of scope: no persistence or database access, no knowledge of playlists,
tracks or user profiles, no direct control of the audio system, no UI logic.
Tag-to-content mapping lives entirely in the Backend service.

---

## 2. File & Folder Structure

Relevant path: `services/rfid-service/src/rfid_service/`

```text
rfid_service/
├── __init__.py                  # Package init, re-exports load_app_config / create_reader / MQTTClient
├── main.py                      # Entry point: config, reader, MQTT, RFIDManager, API server, graceful shutdown
├── config.py                    # Loads environment variables + config/rfid.json
├── config_schema.py             # Pydantic schema for env and RFID config
├── config_manager.py            # JsonConfigManager wrapper for config/rfid.json (currently unused)
├── exceptions.py                # Service-specific exception hierarchy
├── core/
│   ├── __init__.py
│   └── rfid_manager.py          # Scan loop, mode switching, duplicate suppression, presence tracking, event publishing
├── infrastructure/
│   ├── __init__.py
│   ├── mqtt_client.py           # Subscriptions (cmd/set-mode, config/general) and message dispatch
│   └── hardware/
│       ├── __init__.py
│       ├── reader_interface.py  # Abstract RFIDReader interface
│       ├── reader_factory.py    # Factory: reader instance per reader_type (pn532, mock)
│       ├── pn532_reader.py      # PN532 hardware implementation (pn532pi)
│       └── mock_reader.py       # Mock reader for development and tests
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI: GET /health
└── models/
    ├── __init__.py
    ├── events.py                # Backward-compatible re-export of schemas.py (deprecated)
    └── schemas.py               # Pydantic event models for all MQTT payloads
```

Connection handling, reconnect backoff, subscription replay and the
`config/general` log-level handler are **not** implemented here. They come from
`shared_lib.mqtt.BaseMQTTClient`, which every Minabox service inherits from.

---

## 3. Public Interfaces

### 3.1 MQTT

All topics follow the same pattern:

```text
minabox/<device-id>/<domain>/<action>
```

#### Published by the RFID service

| Topic | Retained | QoS | Payload |
| --- | --- | --- | --- |
| `.../rfid/tag-scanned` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-scanned-learning` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-removed` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/presence` | **yes** | 1 | `tag_present`, `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/status` | **yes** | 1 | `state`, `reader_id`, `error`, `timestamp` |
| `.../system/service-started` | no | 1 | `service` (re-published after every reconnect) |

Field semantics:

- `tag_id` – transponder UID as an uppercase hex string without separators
  (for example `04A224BC19`). `tag-removed` carries the UID of the tag that was
  removed; at service startup with an empty reader it carries an empty string.
- `reader_id` – identifier of the active reader, built as
  `<reader_type>_<interface>` (for example `pn532_i2c`, `mock_i2c`).
- `timestamp` – ISO-8601, UTC.
- `tag_present` – `true` while a tag lies on the reader, otherwise `false`.
  `tag_id` is `null` when no tag is present.

`presence` is the retained single source of truth for the current tag state.
Subscribers that reconnect or re-initialise (Backend, LED service) get the
correct state immediately instead of waiting for the next change event.

#### Subscribed by the RFID service

| Topic | Payload | Effect |
| --- | --- | --- |
| `.../rfid/cmd/set-mode` | `{"mode": "learning"}` or `{"mode": "normal"}` | Switches the operating mode |
| `.../config/general` | `{"log_level": "DEBUG" \| "INFO" \| ...}` | Applies the log level at runtime |

Unknown modes and malformed JSON are logged and ignored; they never change the
current mode.

**No generic config API:** unlike the Button and LED services, the RFID service
does not implement `config/get`, `config/update` and `config/response`. Reader
configuration is read from `config/rfid.json` at startup only. The single
runtime-changeable value is the operating mode.

### 3.2 REST

The service exposes one HTTP endpoint on port 8000 inside the container
(published as `8001` on the host), used for health checks and debugging:

- `GET /health`

```json
{
  "status": "healthy",
  "service": "rfid",
  "version": "0.1.0",
  "device_id": "minabox-01",
  "mqtt_connected": true,
  "mqtt_broker": "mqtt",
  "mqtt_port": 1883
}
```

`status` is `healthy` while the broker connection is live and `degraded` while
it is down; the endpoint always answers with HTTP 200, so a broker outage does
not mark the container unhealthy. All functional operations run over MQTT and
are bundled in the Backend service.

---

## 4. Core Functions / Use Cases

### 4.1 Learning mode (teaching a tag)

1. Backend/WebUI sets the mode over MQTT:
   `.../rfid/cmd/set-mode` → `{"mode": "learning"}`.
2. The service switches to learning mode (`state = learning`) and publishes the
   new status on `.../rfid/status`.
3. When a tag is placed on the reader, its UID is read and published on
   `.../rfid/tag-scanned-learning`. No `tag-scanned` event is emitted in this
   mode, so a tag being taught never starts playback.
4. Backend/WebUI shows the tag and lets the user assign a playlist or track.
5. The Backend stores the tag-to-content mapping in the database.
6. The WebUI switches the mode back to `normal` when the learning dialog closes.

The mode is not persisted: a service restart always comes up in `normal`.

### 4.2 Normal mode (tag → playback)

1. The service runs in normal mode (`state = normal`) and scans continuously.
2. On a newly placed tag it publishes `.../rfid/tag-scanned` plus the retained
   `.../rfid/presence` with `tag_present: true`.
3. The Backend looks up `tag_id`, resolves the content and triggers the Audio
   service.
4. When the reader no longer sees the tag, the service publishes
   `.../rfid/tag-removed` and `presence` with `tag_present: false`. Depending on
   the "stop playback on tag removal" setting the Backend stops playback.

### 4.3 Presence tracking and duplicate suppression

Two mechanisms keep the event stream free of repetitions:

- **Presence tracking** – the manager remembers the UID currently on the reader.
  As long as the same tag stays there, no further `tag-scanned` event is
  emitted, no matter how often the scan loop reads it.
- **Duplicate suppression** – `duplicate_suppression_ms` (default 2000 ms)
  defines a window per tag UID. A tag that reappears within this window after
  having been removed produces no new `tag-scanned` event.

### 4.4 Startup behaviour

`RFIDManager.start()` performs one synchronous read before the scan loop begins
and publishes the result. A box that boots with a tag already on the reader
therefore reports the correct state, and one that boots with an empty reader
publishes `tag-removed` (with an empty `tag_id`) plus `presence: false`.

---

## 5. Dependencies

- **Hardware** – at least one RFID reader (PN532 over I2C, SPI or UART),
  abstracted behind the `RFIDReader` interface. The container gets `/dev/i2c-1`
  passed through and runs with the host's `i2c` group id.
- **MQTT broker** – Mosquitto; host and port come from the root `.env`.
- **Backend service** – consumes `tag-scanned`, `tag-scanned-learning`,
  `tag-removed` and `presence`, performs the tag-to-content mapping and triggers
  the Audio service. The RFID container starts only after the Backend is
  healthy.
- **LED service** – consumes the retained `presence` topic for its tag
  indication.
- **Python libraries** – `pn532pi` (reader driver), `aiomqtt`, `fastapi` /
  `uvicorn`, `pydantic`, `structlog` and the internal `shared-lib`.

### Configuration

Global `.env` (repository root):

- `MINABOX_DEVICE_ID` – box id used in every MQTT topic.
- `MQTT_BROKER`, `MQTT_PORT` – broker address.
- `LOG_LEVEL` – initial log level.

Service configuration `config/rfid.json` (bind-mounted into the container):

| Key | Values | Default | Meaning |
| --- | --- | --- | --- |
| `reader.reader_type` | `pn532`, `mock` | – | Reader implementation |
| `reader.interface` | `i2c`, `spi`, `uart` | – | Hardware interface |
| `reader.scan_interval_ms` | 20–5000 | 200 | Delay between scan attempts |
| `reader.duplicate_suppression_ms` | 0–60000 | 2000 | Suppression window per tag UID |

The file is validated against the Pydantic schema at startup; invalid values
abort the start with a `ConfigError`.

---

## 6. Errors & Status

### 6.1 States

The `state` field of the status payload takes one of:

- `idle` – service stopping; published during shutdown.
- `normal` – normal mode active, scanning continuously.
- `learning` – learning mode active.
- `error` – a hardware fault is preventing normal operation.

### 6.2 Error codes

The `error` field of the status payload carries a code when `state` is `error`:

- `reader_not_found` – reader hardware unreachable (wrong bus, cabling).
- `reader_init_failed` – initialising the reader driver failed.
- `read_timeout` – reading a tag failed repeatedly.
- `protocol_error` – unexpected or invalid response from the reader.

Example status on error:

```json
{
  "state": "error",
  "reader_id": "pn532_i2c",
  "error": "read_timeout",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

A hardware fault during scanning does not stop the service: it publishes the
error status, pauses for five seconds and then retries. A hardware fault while
the reader is being initialised at startup aborts the start, and Docker's
restart policy brings the container back up.

### 6.3 Logging

The service logs structured events via `structlog` (JSON), among them:

- `tag_scanned` with `tag_id`, `mode`
- `tag_removed` with `tag_id`
- `presence_published` with `tag_present`, `tag_id`
- `mode_changed` with `old_mode`, `new_mode`
- `status_published` with `state`, `error`
- `scan_hardware_error` with `error`, `reader_id`

The log level follows the global logging rules of the framework and can be
changed at runtime through `.../config/general`.
