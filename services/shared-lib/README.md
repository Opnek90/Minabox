# Shared-Lib für Minabox-Services

Gemeinsame Bausteine für alle Minabox-Python-Services (LED, RFID, Audio, Button, Display, Backend). Das Paket heißt **minabox-shared** und wird unter dem Namensraum **shared_lib** installiert.

## Inhalt

| Modul | Inhalt | Verwendung in Services |
|-------|--------|-------------------------|
| **shared_lib.exceptions** | `MinaboxError`, `ConfigError`, `ConfigLoadError` | Service-Basis von MinaboxError erben; ConfigError für Config-Fehler |
| **shared_lib.config** | `EnvConfigBase`, `load_env()`, `load_json_config()`, `JsonConfigManager` | Env-Laden, JSON-Config laden, generischer Config-Manager mit Hot-Reload/Callbacks |
| **shared_lib.mqtt** | `BaseMQTTClient`, `HasMqttConfig` | Optionale Basis für MQTT-Clients |

## Installation

- **Als Paket (empfohlen):** Im Repo zuerst shared-lib, dann den Service installieren (aus dem Service-Verzeichnis, damit die Pfad-Abhängigkeit aufgelöst wird):

  ```bash
  pip install -e /path/to/services/shared-lib
  cd services/led-service && pip install -e .
  ```

  Jeder Service deklariert die Abhängigkeit in `pyproject.toml`:

  ```toml
  dependencies = [..., "minabox-shared @ file:../shared-lib"]
  ```

  Beim `pip install -e .` **aus dem Service-Ordner** (z. B. `services/led-service`) wird `../shared-lib` relativ zu diesem Ordner aufgelöst.

## Verwendung in Services

- **Exceptions:**  
  `from shared_lib.exceptions import MinaboxError, ConfigError`  
  Service-Basis: `class MinaboxLEDError(MinaboxError): ...`

- **Config-Schema:**  
  `from shared_lib.config import EnvConfigBase`  
  `class EnvConfig(EnvConfigBase):` mit service-spezifischen Feldern.

- **Config laden:**  
  `from shared_lib.config import load_env, load_json_config`  
  Env: `EnvConfig(**load_env())` bzw. mit `optional_defaults`.  
  JSON: `load_json_config(path, SchemaClass, create_if_missing=..., default_factory=...)`

- **Config-Manager:**  
  `from shared_lib.config import JsonConfigManager`  
  Service nutzt entweder eine dünne Subclass (Default-Pfad + Schema) oder einen eigenen Manager (z. B. Audio mit ALSA-Migration).

## Struktur

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

## Zusammenfassung

| Thema | Shared-Lib | Service |
|-------|------------|---------|
| **Exceptions** | `MinaboxError`, `ConfigError`, `ConfigLoadError` | Eigene Basis (z. B. `MinaboxLEDError(MinaboxError)`) + Domain-Exceptions |
| **Env-Config** | `EnvConfigBase`, `load_env()` | `EnvConfig(EnvConfigBase)` + optionale Felder; `load_app_config()` orchestriert |
| **JSON-Config** | `load_json_config()`, `JsonConfigManager` | Pfade, `load_app_config()`; ConfigManager = Subclass oder Wrapper |
