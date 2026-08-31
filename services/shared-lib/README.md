# Shared-Lib for Minabox services

Shared building blocks for all Minabox Python services (LED, RFID, Audio,
Button, Display, Backend). The package is called **minabox-shared** and is
installed under the namespace **shared_lib**.

## Contents

| Module | Contents | Use in services |
|-------|--------|-------------------------|
| **shared_lib.exceptions** | `MinaboxError`, `ConfigError`, `ConfigLoadError` | service base inherits from MinaboxError; ConfigError for config errors |
| **shared_lib.config** | `EnvConfigBase`, `load_env()`, `load_json_config()`, `JsonConfigManager` | env loading, JSON config loading, a generic config manager with hot reload/callbacks |
| **shared_lib.mqtt** | `BaseMQTTClient`, `HasMqttConfig` | an optional base for MQTT clients |

## Installation

- **As a package (recommended):** in the repo, install shared-lib first, then
  the service (from the service directory, so the path dependency is resolved):

  ```bash
  pip install -e /path/to/services/shared-lib
  cd services/led-service && pip install -e .
  ```

  Every service declares the dependency in `pyproject.toml`:

  ```toml
  dependencies = [..., "minabox-shared @ file:../shared-lib"]
  ```

  With `pip install -e .` **from the service folder** (e.g. `services/led-service`),
  `../shared-lib` is resolved relative to that folder.

## Use in services

- **Exceptions:**
  `from shared_lib.exceptions import MinaboxError, ConfigError`
  service base: `class MinaboxLEDError(MinaboxError): ...`

- **Config schema:**
  `from shared_lib.config import EnvConfigBase`
  `class EnvConfig(EnvConfigBase):` with service-specific fields.

- **Load config:**
  `from shared_lib.config import load_env, load_json_config`
  env: `EnvConfig(**load_env())` or with `optional_defaults`.
  JSON: `load_json_config(path, SchemaClass, create_if_missing=..., default_factory=...)`

- **Config manager:**
  `from shared_lib.config import JsonConfigManager`
  a service uses either a thin subclass (default path + schema) or its own
  manager (e.g. audio with ALSA migration).

## Structure

```
shared-lib/
  pyproject.toml
  README.md
  shared_lib/
    __init__.py
    exceptions.py
    config/
      __init__.py
      env.py
      loader.py
      manager.py
    mqtt/
      __init__.py
      base_client.py
```

## Summary

| Topic | Shared-Lib | Service |
|-------|------------|---------|
| **Exceptions** | `MinaboxError`, `ConfigError`, `ConfigLoadError` | own base (e.g. `MinaboxLEDError(MinaboxError)`) + domain exceptions |
| **Env config** | `EnvConfigBase`, `load_env()` | `EnvConfig(EnvConfigBase)` + optional fields; `load_app_config()` orchestrates |
| **JSON config** | `load_json_config()`, `JsonConfigManager` | paths, `load_app_config()`; ConfigManager = subclass or wrapper |
