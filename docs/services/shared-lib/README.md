# Shared-Lib

Shared-lib is not a service: it is the Python package every Minabox service
imports. It holds the pieces that must behave identically everywhere —
configuration loading, the self-healing MQTT client, logging setup, version
reporting, health-response shape and the exception base. A change here reaches
all six Python services at once.

| | |
| --- | --- |
| Image | none — installed into every Python service image |
| Source | `services/shared-lib/shared_lib/` |
| Version | `services/shared-lib/VERSION` |
| Distribution name | `minabox-shared`, imported as `shared_lib` |
| Compose service | none |
| Runtime | Python ≥ 3.12 (services run 3.13) |
| Speaks | nothing on its own; provides the MQTT base its subclasses use |
| Needs | `pydantic`, `structlog`, `aiomqtt` |

## 1. Purpose & Responsibility

Shared-lib exists so that cross-cutting behaviour has exactly one
implementation. Everything in it was once copied into every service, and the
copies drifted — the MQTT reconnect logic is the reason the package exists at
all (see `docs/Troubleshooting.md`, "MQTT-Verlust").

What belongs here:

- config loading and validation (environment + JSON + Pydantic)
- the MQTT connection lifecycle: connect, retry, resubscribe, replay
- structlog setup, so every service logs the same shape
- build-time version reporting for `/health`
- the health-response schema
- the exception base

What does **not** belong here:

| Not shared-lib | Where it belongs |
| --- | --- |
| Domain logic of any kind | the service that owns it |
| Concrete MQTT topics or payload models | the publishing service |
| Message dispatch (`on_message` bodies) | the service subclass |
| Anything only one service needs | that service |

The rule of thumb: a thing belongs here once the *second* service needs it and
the two must not diverge. One service needing it is not enough.

## 2. File & Folder Structure

```
services/shared-lib/
├── pyproject.toml               distribution minabox-shared, version from VERSION
├── VERSION                      package version
├── shared_lib/
│   ├── __init__.py              the public surface — everything re-exported here
│   ├── logging.py               setup_structlog(): DEBUG → console, INFO+ → JSON
│   ├── version.py               ** version reporting ** from build args (APP_VERSION,
│   │                            GIT_SHA, BUILD_DATE); 0.0.0-dev when unbuilt
│   ├── schemas.py               BaseHealthResponse, build_health_body()
│   ├── exceptions.py            MinaboxError → ConfigError → ConfigLoadError
│   ├── config/
│   │   ├── env.py               EnvConfigBase, load_env(), COMMON_ENV_KEYS
│   │   ├── loader.py            load_json_config(): read + Pydantic-validate
│   │   ├── manager.py           JsonConfigManager: load, save, reload, callbacks
│   │   └── general_settings.py  load_general_settings(): fault-tolerant dict read
│   └── mqtt/
│       ├── base_client.py       ** the important one ** — BaseMQTTClient, 487 lines
│       │                        of connection lifecycle every service depends on
│       └── topics.py            get_mqtt_topic(device_id, domain, action)
└── tests/test_base_client.py    the MQTT base under connection loss
```

## 3. Runtime Flow

Shared-lib has no process of its own. The one thing with a lifecycle is
`BaseMQTTClient`, and understanding it is understanding every service's
connection to the broker.

`start()` returns as soon as the supervised loop task exists — it never waits
for the broker, so an unreachable broker cannot fail a service's startup. The
loop then runs forever:

1. **connect** — one attempt. Refused, DNS unresolvable (broker container not
   back yet) and mid-iteration disconnects are all the same ordinary case.
2. **replay** — re-apply every subscription, then re-publish every *remembered*
   message. Without this a reconnected service is connected but mute: the
   broker has forgotten the subscriptions, and a broker that restarted lost the
   retained messages with them.
3. **`on_connected()`** — the subclass hook, after replay.
4. **consume** — iterate messages and dispatch to `on_message()`. An exception
   from a handler is logged, never propagated: a bug in one handler must not
   drop the connection.
5. **on failure** — log, call `on_disconnected(exc)`, sleep the backoff, retry.

Backoff is exponential from 1 s to 60 s with ±25 % jitter, so a whole fleet of
services does not hammer the broker in lockstep after a broker restart.

`is_connected` reflects the *live* socket state — it flips to False the moment
message iteration fails, which is what lets `/health` report
`mqtt_connected: false` while the broker is away.

`publish()` **never raises** because of a broken connection; it returns `False`
and drops the message. A status publish must not be able to kill the caller's
task.

## 4. Public Interfaces

No REST, no MQTT topics of its own. The interface is the import surface.

### 4.1 Exports from `shared_lib`

| Export | Purpose |
| --- | --- |
| `setup_structlog(log_level, *, silence_loggers, extra_processors)` | call once in `main.py` |
| `get_version()`, `get_git_sha()`, `version_info()` | build-time identity for `/health` |
| `BaseHealthResponse`, `build_health_body(...)` | uniform health body |
| `MinaboxError`, `ConfigError`, `ConfigLoadError` | exception base |
| `config`, `mqtt` | the two subpackages |

### 4.2 `shared_lib.config`

| Export | Purpose |
| --- | --- |
| `EnvConfigBase` | Pydantic base with the four common env fields |
| `load_env(required_keys, optional_defaults)` | env → dict with lowercased keys and coerced values; raises `ConfigError` when a required key is missing |
| `COMMON_ENV_KEYS` | `MQTT_BROKER`, `MQTT_PORT`, `MINABOX_DEVICE_ID`, `LOG_LEVEL` |
| `load_json_config(path, schema, *, create_if_missing, default_factory)` | read + validate; raises `ConfigError` on missing file, bad JSON or failed validation |
| `JsonConfigManager(path, schema, ...)` | the same plus `update_config()` (writes to disk), `reload_config()` and reload callbacks |
| `load_general_settings(path)` | fault-tolerant read of `general_settings.json`; returns `{}` on any problem instead of raising |

### 4.3 `shared_lib.mqtt`

`get_mqtt_topic(device_id, domain, action)` → `minabox/<device_id>/<domain>/<action>`.

`BaseMQTTClient` — the methods a service actually uses:

| Method | Notes |
| --- | --- |
| `start()` | starts the supervised loop, returns the task; does not wait for the broker |
| `stop()` / `disconnect()` | shutdown, tolerating an already-dead socket |
| `subscribe(topic, qos)` | safe before the first connection — recorded and applied on connect |
| `resubscribe(topic, qos)` | unsubscribe/subscribe cycle; the only way to make the broker re-deliver a retained message on a live connection |
| `publish(topic, payload, qos, retain, *, remember)` | returns `bool`, never raises; dicts and lists are JSON-encoded |
| `set_will(topic, payload, qos, retain)` | must be called **before** `start()` — the will takes effect on the next connect |
| `apply_general_config(payload)` | the shared `config/general` handler; applies `log_level` |
| `is_connected`, `is_running` | live socket state, loop state |

Subclass hooks: `on_message(topic, payload)` (the one that matters),
`on_connected()`, `on_disconnected(exc)`.

`remember=True` is the mechanism behind every retained status in the system:
the client keeps the payload and re-publishes it after each reconnect.

## 5. Configuration

Shared-lib has no configuration file and reads no environment variable
directly for itself — with one exception: `version.py` reads `APP_VERSION`,
`GIT_SHA` and `BUILD_DATE`, which the Dockerfiles set from build args. A local
build without those args reports `0.0.0-dev`, deliberately, so an unversioned
image is recognisable as such.

Everything else is passed in by the calling service.

## 6. Dependencies

`pydantic` (≥ 2), `structlog` (≥ 24), `aiomqtt` (≥ 2). No database, no HTTP
server, no hardware.

Consumers: backend, audio, rfid, button, led, display and host-helper. Every
service `Dockerfile` installs `./shared-lib` before its own requirements, and
every `pyproject.toml` declares `minabox-shared @ file:../shared-lib`.

Installing for local work — shared-lib first, then the service from its own
directory so the relative path resolves:

```bash
pip install -e services/shared-lib && (cd services/led-service && pip install -e .)
```

## 7. Errors, Health & Logging

**Exception hierarchy.** `MinaboxError` is the root. Services define their own
base under it (`MinaboxRFIDError(MinaboxError)`) and derive domain exceptions
from that, so a caller can catch one service's failures without catching
everything.

**Health.** `build_health_body()` produces the common fields (`status`,
`service`, `device_id`, `mqtt_connected`, `mqtt_broker`, `mqtt_port`); extras
are merged in, and `None` values dropped. `BaseHealthResponse` sets
`extra: allow`, so services add their own fields freely. Status vocabulary is
`healthy | degraded | unhealthy`.

**Logging.** `setup_structlog` switches renderer by level: DEBUG gives
human-readable console output, INFO and above give JSON for log aggregation.
`extra_processors` run after level and timestamp are attached but before
rendering — the backend uses that to keep its last warnings in memory for the
debug export.

MQTT events worth grepping: `mqtt_connection_lost`, `mqtt_reconnect_scheduled`,
`mqtt_resubscribe_failed`, `mqtt_status_republished`,
`mqtt_publish_skipped_disconnected`, `mqtt_message_handler_error`.

## 8. Development & Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/shared-lib/tests -q
```

`tests/test_base_client.py` drives the base client through connection loss,
reconnect, subscription replay, remembered-status replay and publish-while-down
using a fake client injected through the `client_factory` argument — no broker
involved. That constructor argument exists for exactly this reason.

Shared-lib is not built as an image. Changing it means rebuilding **every**
Python service that uses it; `./scripts/build-local.sh <service>` picks up the
local sources because the Dockerfiles copy `shared-lib` from the build context.

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| change reconnect/backoff behaviour | `mqtt/base_client.py` (`run`, `_next_delay`) | `tests/test_base_client.py`; verify no service relies on the old timing |
| add a hook for subclasses | `mqtt/base_client.py` (the "Subclass hooks" block) | document it in 4.3; a hook must have a no-op default |
| add a handler every service shares | `mqtt/base_client.py` (like `apply_general_config`) | remove the per-service copies in the same change |
| add a common env variable | `config/env.py` (`EnvConfigBase`, `COMMON_ENV_KEYS`) | `.env.example`, `docker-compose.yml` for every service, each service's env table |
| add a health field for all services | `schemas.py` (`build_health_body`) | the `/health` route of each service, and the health tables in their documents |
| change log format or processors | `logging.py` | the backend's `extra_processors` usage for the debug export |
| add a config helper | `config/loader.py` or `config/manager.py` | export it in `config/__init__.py` and in 4.2 |
| add anything at all | first ask: does a second service need it? | if not, it belongs in the one service that does |

### Invariants

- **`publish()` never raises on a broken connection.** Callers publish status
  from inside loops and shutdown paths; an exception there would take the
  service down for the sake of a status message.
- **`start()` never waits for the broker.** Startup that depends on the broker
  is precisely the bug this package was created to fix.
- **Subscriptions and remembered publishes are replayed on every connect.**
  Drop the replay and every reconnected service goes silently mute.
- **A handler exception is logged, not propagated.** One buggy `on_message`
  must not cost every other subscription its connection.
- **`is_connected` stays the live socket state,** not "we called connect once".
  Six `/health` endpoints report it as the truth.
- **No domain logic enters this package.** It is imported by everything; a
  domain concept here couples services that should not know about each other.
- **A change here is a change to every service.** Per `CLAUDE.md`, touching
  `services/shared-lib/**` bumps the version of every dependent service and
  requires rebuilding all of them.

## 10. Related Documents

- [`services/shared-lib/README.md`](../../../services/shared-lib/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/Framework.md`](../../Framework.md) — the conventions services follow
- [`docs/Troubleshooting.md`](../../Troubleshooting.md) — "MQTT-Verlust", the failure this package was built to end
