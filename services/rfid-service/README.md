# RFID Service

Hardware layer for the RFID reader: it reads card UIDs and publishes placement
and removal as MQTT events. It does not know what a card means — the backend
owns that.

**Full documentation: [docs/services/rfid/](../../docs/services/rfid/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-rfid` |
| Version | see `VERSION` |
| Compose | `rfid` (profile `rfid`) |
| Interfaces | publishes `rfid/tag-scanned`, `tag-removed`, retained `presence` and `status`; subscribes `rfid/cmd/set-mode`; `GET /health` |
| Config | `config/rfid.json` (read once at startup) |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/rfid-service/tests -q
```

No hardware needed. For running the service itself without a reader, set
`reader_type: "mock"` in `config/rfid.json`.

## Where to make changes

- `src/rfid_service/core/rfid_manager.py` — scan loop, modes, debounce,
  duplicate suppression, every MQTT publish. Almost all behaviour is here.
- `src/rfid_service/infrastructure/hardware/` — reader implementations behind
  the `RFIDReader` interface; add a new reader type in `reader_factory.py`.
- `src/rfid_service/config_schema.py` — every tunable value. Nothing in the
  logic is hard-coded; new timings belong here.
- `src/rfid_service/models/schemas.py` — the MQTT payloads.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
