# Shared-Lib

## 1. Purpose & responsibility

**shared-lib** (package **minabox-shared**, import **shared_lib**) provides
shared Python building blocks for all Minabox services. It contains no domain
business logic — only configuration helpers, an MQTT base, logging setup,
health-response schemas and a common exception base.

**Goals:**

- Uniform config loading and validation (JSON + Pydantic)
- A shared MQTT client base (connection lifecycle) for service-specific subclasses
- Structured logging (structlog) with a uniform configuration
- A health-response schema and helper for all services
- A common exception base (MinaboxError, ConfigError)

**Non-goals:**

- No per-domain MQTT topic definitions (only the helper `get_mqtt_topic`)
- No service-specific schemas or handlers

---

## 2. File & folder structure

Relevant path: `services/shared-lib/shared_lib/`

```text
shared_lib/
├── __init__.py           # Package exports: config, mqtt, setup_structlog, exceptions, schemas (BaseHealthResponse, build_health_body)
├── logging.py            # structlog configuration (setup_structlog): log level, JSON vs. console renderer
├── schemas.py            # BaseHealthResponse (Pydantic), build_health_body() for uniform health responses
├── exceptions.py         # MinaboxError, ConfigError, ConfigLoadError – base for service-specific exceptions
├── config/
│   ├── __init__.py       # Exports: load_env, EnvConfigBase, load_json_config, JsonConfigManager, load_general_settings
│   ├── env.py            # EnvConfigBase (Pydantic), load_env(), COMMON_ENV_KEYS – shared env variables
│   ├── loader.py         # load_json_config() – load a JSON file and validate it against a Pydantic schema
│   ├── manager.py        # JsonConfigManager – JSON config with hot reload, save, optional callbacks
│   └── general_settings.py # load_general_settings() – load general_settings.json (fault-tolerant dict)
└── mqtt/
    ├── __init__.py       # Exports: BaseMQTTClient, HasMqttConfig, get_mqtt_topic
    ├── base_client.py    # BaseMQTTClient (ABC), HasMqttConfig (Protocol) – connection lifecycle for MQTT clients
    └── topics.py         # get_mqtt_topic(device_id, domain, action) – build a topic string (minabox/<device_id>/<domain>/<action>)
```

---

## 3. Public interfaces

shared-lib exposes **no** REST or MQTT endpoints. Other services use it by
import.

**Main exports (from `shared_lib`):**

- **Config:** `load_env`, `EnvConfigBase`, `load_json_config`, `JsonConfigManager`, `load_general_settings` (via `shared_lib.config`)
- **MQTT:** `BaseMQTTClient`, `HasMqttConfig`, `get_mqtt_topic` (via `shared_lib.mqtt`)
- **Logging:** `setup_structlog(log_level, ...)`
- **Schemas:** `BaseHealthResponse`, `build_health_body(...)`
- **Exceptions:** `MinaboxError`, `ConfigError`, `ConfigLoadError`

---

## 4. Core components & dependencies

- **config:** env loading and JSON config with Pydantic; a general-settings
  loader for the backend and other services.
- **mqtt:** an abstract base for MQTT clients; a topic helper. Services
  implement subclasses with their own subscription/handler logic.
- **logging:** call once at service startup (e.g. from `main.py`).
- **schemas / exceptions:** used by all services for health responses and a
  uniform error hierarchy.

**Dependencies (Python):** structlog, pydantic, aiomqtt (for BaseMQTTClient).
No database or REST server.

---

## 5. Configuration

shared-lib itself has no configuration file. It reads no env variables
directly; the services call `load_env()` or use `EnvConfigBase` with their own
env values. `load_general_settings(path)` expects a path to
`general_settings.json` (typically from the backend/config volume).
