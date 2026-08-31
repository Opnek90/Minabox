# RFID Service Architecture

## Purpose

The RFID service owns communication with the configured RFID reader and turns
reader state changes into MQTT events. It does not store tag assignments, know
about playlists, control audio playback, or expose user-interface operations.
The Backend owns the tag-to-content mapping and consumes the events published
by this service.

Supported readers are the PN532 (I2C, SPI, or UART) and a deterministic mock
reader for development and tests. The service runs as a non-root user and the
Compose configuration grants it access only to `/dev/i2c-1`.

## Runtime Model

At startup the service starts the self-healing MQTT client, publishes a
`system/service-started` announcement, creates the RFID manager and its scan
task, and then starts the HTTP server. Reader initialization happens in the
scan task and never blocks the HTTP server or MQTT event loop. This keeps
diagnostics available when the reader is absent or miswired.

Reader access is blocking and therefore runs in an asyncio worker thread. A
successful read drives one of these state transitions:

- A newly observed tag publishes a mode-specific scan event and retained
  `presence: true`.
- Repeated reads of the same present tag produce no further scan events.
- Consecutive empty reads equal to `removal_debounce_reads` publish
  `tag-removed` and retained `presence: false`.
- Repeated hardware read failures publish an error status. After
  `reinit_after_read_errors` failures, the reader is released and initialized
  again.

The service retries reader initialization with exponential backoff. With
`init_max_attempts: 0` it retries indefinitely; a positive value stops the scan
task once the limit is reached while the process and diagnostic endpoint remain
available.

Learning mode is selected through MQTT. A scan in this mode publishes only
`tag-scanned-learning`, preventing it from triggering normal playback. It
automatically returns to normal mode after `learning_timeout_s` without a scan.
The mode is not persisted, so every process start begins in normal mode.

## MQTT Contract

All topics are namespaced as `minabox/<device-id>/<domain>/<action>`.

### Published topics

| Topic | Retained | QoS | Payload |
| --- | --- | --- | --- |
| `.../rfid/tag-scanned` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-scanned-learning` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/tag-removed` | no | 1 | `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/presence` | yes | 1 | `tag_present`, `tag_id`, `reader_id`, `timestamp` |
| `.../rfid/status` | yes | 1 | `state`, `reader_id`, `error`, `timestamp` |
| `.../system/service-started` | no | 1 | `service` |

`presence` is the authoritative current-reader state. Both `presence` and
`status` are remembered by the MQTT client and republished after reconnecting.
The service registers an MQTT last will that publishes retained
`presence: false` if its connection ends unexpectedly. Consumers must use
`tag_present`, not the will timestamp, because MQTT fixes a will payload when
the connection opens.

`tag_id` is an uppercase hexadecimal UID without separators. `reader_id` is
normally `<reader_type>_<interface>`, for example `pn532_i2c`. Timestamps are
UTC ISO-8601 strings. On an empty-reader startup, the current implementation
also emits `tag-removed` with an empty `tag_id` before publishing
`presence: false`; consumers must tolerate this startup marker.

### Subscribed topics

| Topic | Payload | Effect |
| --- | --- | --- |
| `.../rfid/cmd/set-mode` | `{"mode":"normal"}` or `{"mode":"learning"}` | Switches the operating mode |
| `.../config/general` | A general configuration payload with `log_level` | Updates log level at runtime |

Malformed commands and unsupported modes are logged and ignored. Reader
configuration is loaded only at process startup from `config/rfid.json`.

## HTTP Interface and Diagnostics

`GET /health` listens on port 8000 in the container and is published only as
`127.0.0.1:8001` on the host. It always responds with HTTP 200 so that a
missing reader or broker remains diagnosable instead of causing a restart loop.
Its JSON `status` is `healthy` only if MQTT is connected, the reader is ready,
and the scan loop is alive; otherwise it is `degraded`.

The `reader` object includes `reader_id`, readiness, scan-loop state, current
mode, presence, tag ID, age of the last successful read, and the last error
code. The possible status states are `idle`, `normal`, `learning`, and `error`.
The currently emitted error codes are `reader_not_found`,
`reader_init_failed`, and `read_timeout`.

## Configuration

The service validates `config/rfid.json` with Pydantic during startup. Invalid
configuration prevents startup. Environment variables `MQTT_BROKER`,
`MQTT_PORT`, `MINABOX_DEVICE_ID`, and `LOG_LEVEL` are required through the
shared environment configuration; `API_PORT` defaults to `8000`.

| Key | Default | Meaning |
| --- | --- | --- |
| `reader.reader_type` | required | `pn532` or `mock` |
| `reader.interface` | required | `i2c`, `spi`, or `uart` |
| `reader.scan_interval_ms` | 200 | Delay between scan attempts |
| `reader.duplicate_suppression_ms` | 2000 | Per-UID interval suppressing a rapid re-placement |
| `reader.removal_debounce_reads` | 3 | Consecutive empty reads required for removal |
| `reader.error_retry_delay_ms` | 5000 | Delay after a reader error |
| `reader.init_retry_delay_ms` | 2000 | First initialization retry delay |
| `reader.init_retry_max_delay_ms` | 60000 | Maximum initialization retry delay |
| `reader.init_max_attempts` | 0 | Initialization attempts; zero means unlimited |
| `reader.reinit_after_read_errors` | 5 | Consecutive read errors before rebuilding the reader; zero disables this |
| `reader.pn532.i2c_bus` | 1 | I2C bus for PN532 I2C mode |
| `reader.pn532.spi_device` | 0 | SPI device for PN532 SPI mode |
| `reader.pn532.uart_port` | `/dev/ttyS0` | Serial device for PN532 UART mode |
| `reader.pn532.passive_activation_retries` | 2 | PN532 passive-target activation retries per read |
| `reader.mock.tags` | two sample UIDs | Sequence used by the mock reader |
| `reader.mock.hold_reads` | 10 | Reads for which a mock tag remains present |
| `reader.mock.gap_reads` | 10 | Empty reads between mock tags |
| `modes.learning_timeout_s` | 300 | Idle time before learning mode returns to normal; zero disables it |
| `service.shutdown_timeout_s` | 5.0 | Maximum wait per background task during shutdown |

## Container Operation

The image is a two-stage `python:3.13-slim` build. Build-only compiler and I2C
headers stay in the builder stage. The runtime image contains the application,
its installed Python packages, and `curl` for the health check. Build-only
Python packaging tools and unused console scripts are excluded from the runtime
image. It runs as user `minabox`; Compose overrides its group with the host I2C
group.

Compose bind-mounts the configuration directory read-write, exposes the
unauthenticated health endpoint only on loopback, uses `unless-stopped`, and
limits JSON logs to three files of 10 MB. The Dockerfile health check and the
Compose health check both call `curl -f http://localhost:8000/health`; because
the endpoint intentionally always returns 200, container health represents
HTTP-server liveness rather than RFID readiness.

## Tests

The RFID test suite covers the manager state machine, debounce and duplicate
suppression behavior, reader initialization and recovery, retained MQTT
messages, command validation, health responses, and mock-reader behavior.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/rfid-service/tests -q
```
