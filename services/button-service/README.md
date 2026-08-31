# Button Service

Reads push buttons and rotary encoders, classifies them into raw events
(short/long/double press, encoder detents), maps those to named actions and
publishes them over MQTT. What an action *means* is decided elsewhere.

**Full documentation: [docs/services/button/](../../docs/services/button/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-button` |
| Version | see `VERSION` |
| Compose | `button` (profile `button`) |
| Interfaces | publishes `button/<action>`, `button/raw-event`, `audio/volume-up|down`; subscribes `button/config/reload`; `GET /health` |
| Config | `config/buttons.json` — written by the backend, reloaded on request |

Wiring: push button one leg to GPIO, the other to GND (internal pull-up).
Rotary encoder CLK/DT on two GPIOs, SW on a third. BCM numbering. **No pin may
appear in `leds.json` as well** — whichever service starts first claims it.

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/button-service/tests -q
```

No hardware needed. `DISABLE_GPIO=true` also lets the service itself run
without pins.

## Where to make changes

- `src/button_service/core/state_machine.py` — GPIO callbacks → raw events;
  the short/long/double classification and its timing constants.
- `src/button_service/core/event_processor.py` — debounce, action lookup, MQTT
  dispatch.
- `src/button_service/core/gpio_input_manager.py` — the gpiozero devices, one
  per configured pin.
- `src/button_service/config_schema.py` — the basic/advanced mode rules.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
