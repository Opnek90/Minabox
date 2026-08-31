# LED Service

GPIO output stage for the box's single-colour status LEDs. It turns MQTT events
from the other services into logical states, and renders each state as a
pattern on whichever LEDs the user bound to it.

**Full documentation: [docs/services/led/](../../docs/services/led/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-led` |
| Version | see `VERSION` |
| Compose | `led` (profile `led`) |
| Interfaces | subscribes `audio/status`, `rfid/*`, `button/raw-event`, `system/*`, `led/usage-denied`, `led/config/reload`; publishes `led/config/response`; `GET /health`, `POST /test` |
| Config | `config/leds.json` — written by the backend, mounted read-only here |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/led-service/tests -q
```

No hardware needed. `DISABLE_GPIO=true` also lets the service itself run
without pins.

## Where to make changes

- `src/led_service/core/state_manager.py` — MQTT topic + payload → logical
  state. A new state needs a rule here **and** a subscription in
  `infrastructure/mqtt_client.py`; either alone fails silently.
- `src/led_service/core/led_patterns.py` — the five pattern coroutines.
- `src/led_service/core/led_controller.py` — pin claiming, pattern cancelling,
  the per-LED lock.
- `src/led_service/config_schema.py` — pattern validation, which repairs an
  unusable binding rather than rejecting the file.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
