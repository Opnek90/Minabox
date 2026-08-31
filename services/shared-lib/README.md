# Shared-Lib

The Python package every Minabox service imports: config loading, the
self-healing MQTT client, logging setup, version reporting, health schema and
the exception base. Not a service — it ships inside the other images.

**Full documentation: [docs/services/shared-lib/](../../docs/services/shared-lib/README.md)**

| | |
| --- | --- |
| Image | none — installed into every Python service image |
| Version | see `VERSION` |
| Compose | none |
| Interfaces | import surface only: `shared_lib`, `shared_lib.config`, `shared_lib.mqtt` |
| Config | none of its own |

Install for local work — shared-lib first, then the service from its own
directory so `minabox-shared @ file:../shared-lib` resolves:

```bash
pip install -e services/shared-lib && (cd services/led-service && pip install -e .)
```

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/shared-lib/tests -q
```

## Where to make changes

- `shared_lib/mqtt/base_client.py` — the connection lifecycle every service
  depends on: retry, subscription replay, remembered status, last will.
- `shared_lib/config/` — `env.py` (common environment), `loader.py` and
  `manager.py` (JSON config with reload callbacks).
- `shared_lib/logging.py`, `schemas.py`, `version.py`, `exceptions.py` — one
  concern each.

A change here changes **every** Python service: bump each dependent service's
`VERSION` and rebuild them all. Section 9 of the architecture document lists
the invariants a change must not break.
