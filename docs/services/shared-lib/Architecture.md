# Shared-Lib – Architecture

## 1. Zweck & Verantwortung

Die **shared-lib** (Paket **minabox-shared**, Import **shared_lib**) stellt gemeinsame Python-Bausteine für alle Minabox-Services bereit. Sie enthält keine fachliche Business-Logik, sondern Konfigurations-Hilfen, MQTT-Basis, Logging-Setup, Health-Response-Schemas und eine gemeinsame Exception-Basis.

**Ziele:**

- Einheitliche Config-Lade- und Validierungslogik (JSON + Pydantic)
- Gemeinsame MQTT-Client-Basis (Verbindungs-Lifecycle) für service-spezifische Subclasses
- Strukturiertes Logging (structlog) mit einheitlicher Konfiguration
- Health-Response-Schema und Hilfsfunktion für alle Services
- Gemeinsame Exception-Basis (MinaboxError, ConfigError)

**Nicht-Ziele:**

- Keine MQTT-Topic-Definitionen pro Domain (nur Hilfsfunktion `get_mqtt_topic`)
- Keine service-spezifischen Schemas oder Handlers

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/shared-lib/shared_lib/`

```text
shared_lib/
├── __init__.py           # Package-Export: config, mqtt, setup_structlog, exceptions, schemas (BaseHealthResponse, build_health_body)
├── logging.py            # Konfiguration von structlog (setup_structlog): Log-Level, JSON vs. Console-Renderer
├── schemas.py            # BaseHealthResponse (Pydantic), build_health_body() für einheitliche Health-Responses
├── exceptions.py         # MinaboxError, ConfigError, ConfigLoadError – Basis für service-spezifische Exceptions
├── config/
│   ├── __init__.py       # Export: load_env, EnvConfigBase, load_json_config, JsonConfigManager, load_general_settings
│   ├── env.py            # EnvConfigBase (Pydantic), load_env(), COMMON_ENV_KEYS – gemeinsame Env-Variablen
│   ├── loader.py         # load_json_config() – JSON-Datei laden und mit Pydantic-Schema validieren
│   ├── manager.py       # JsonConfigManager – JSON-Config mit Hot-Reload, Save, optionalen Callbacks
│   └── general_settings.py # load_general_settings() – general_settings.json laden (fehlertolerantes Dict)
└── mqtt/
    ├── __init__.py       # Export: BaseMQTTClient, HasMqttConfig, get_mqtt_topic
    ├── base_client.py    # BaseMQTTClient (ABC), HasMqttConfig (Protocol) – Verbindungs-Lifecycle für MQTT-Clients
    └── topics.py        # get_mqtt_topic(device_id, domain, action) – Topic-String bauen (minabox/<device_id>/<domain>/<action>)
```

---

## 3. Öffentliche Schnittstellen

Die shared-lib bietet **keine** REST- oder MQTT-Endpoints. Sie wird von anderen Services per Import genutzt.

**Wichtigste Exporte (aus `shared_lib`):**

- **Config:** `load_env`, `EnvConfigBase`, `load_json_config`, `JsonConfigManager`, `load_general_settings` (über `shared_lib.config`)
- **MQTT:** `BaseMQTTClient`, `HasMqttConfig`, `get_mqtt_topic` (über `shared_lib.mqtt`)
- **Logging:** `setup_structlog(log_level, ...)`
- **Schemas:** `BaseHealthResponse`, `build_health_body(...)`
- **Exceptions:** `MinaboxError`, `ConfigError`, `ConfigLoadError`

---

## 4. Kernkomponenten & Abhängigkeiten

- **config:** Env-Loading und JSON-Config mit Pydantic; General-Settings-Loader für Backend/andere Services.
- **mqtt:** Abstrakte Basis für MQTT-Clients; Topic-Helfer. Services implementieren Subclasses mit eigener Subscription/Handler-Logik.
- **logging:** Einmalig beim Service-Start aufrufen (z. B. aus `main.py`).
- **schemas / exceptions:** Von allen Services für Health-Responses und einheitliche Fehlerhierarchie genutzt.

**Abhängigkeiten (Python):** structlog, pydantic, aiomqtt (für BaseMQTTClient). Keine Datenbank oder REST-Server.

---

## 5. Konfiguration

Die shared-lib selbst hat keine Konfigurationsdatei. Sie liest keine Env-Variablen direkt; die Services rufen `load_env()` oder nutzen `EnvConfigBase` mit ihren eigenen Env-Werten. `load_general_settings(path)` erwartet einen Pfad zur `general_settings.json` (typisch vom Backend/Config-Volumen).

---

## 6. Refactoring-Checkliste

- [ ] **Keine groben Inkonsistenzen:** Verantwortungen sind klar getrennt (config, mqtt, logging, schemas, exceptions).
- [ ] Optional: Weitere gemeinsame Topic-Helfer oder Konstanten (z. B. Domain-Namen) hier zentralisieren, wenn mehrere Services dieselben Strings nutzen.
