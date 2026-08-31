# Backend Service

The central orchestration and data hub: the only service that owns the
database, the bridge between the MQTT bus and the WebUI's REST/WebSocket
interface, and the home of every decision that spans more than one service —
which card plays what, when playback ends, whether a child may still listen.

**Full documentation: [docs/services/backend/](../../docs/services/backend/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-backend` |
| Version | see `VERSION` |
| Compose | `backend` (always on), published on `${BACKEND_PORT:-8080}` |
| Interfaces | REST `/api/v1` and WebSocket `/ws`; subscribes `rfid/*`, `audio/status`, `audio/position-report`, `button/+`; publishes `audio/*`, `rfid/cmd/set-mode`, `<service>/config/reload`, retained `config/general`; HTTP to audio, host-helper and media-downloader |
| Config | environment; `/data/general_settings.json` and `auth_settings.json`; the other services' config files under `CONFIG_SERVICES_PATH` |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/backend-service/tests -q
```

No hardware and no other service needed. The suite is a set of regression pins
around what breaks silently: the end-of-content logic, the schema version,
container discovery, the update check, the auth prefixes and the debug export.

## Where to make changes

- `src/backend_service/core/handlers/` — the cross-service workflows.
  `rfid_handler.py` is the central one (scan → lookup → play); `audio_handler.py`
  owns status transitions and statistics, `button_handler.py` next/repeat,
  `timer_handler.py` the sleep timer, loop guard and fade-out.
- `src/backend_service/api/routes_*.py` — one router per resource. Route order
  matters: folder routers before media routers.
- `src/backend_service/core/db_manager.py` — engine, PRAGMAs, and
  **`SCHEMA_VERSION`**: raise it only when a change is not backwards compatible.
- `src/backend_service/models/database.py` — the SQLAlchemy models; every new
  column needs an idempotent `ALTER TABLE` in `db_manager.py`.
- `src/backend_service/app_factory.py` — the wiring: which MQTT topics are
  subscribed and which handler each reaches.
- `src/backend_service/core/api_errors.py` — every error carries a stable
  `code`; the WebUI translates codes, never `detail`.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
