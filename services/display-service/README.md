# Display Service

I2C OLED status display (SSD1306, 128×64). It shows what other services have
already decided — audio status over MQTT, sleep timer, session and network
state polled from the backend — as one finished screen at a time.

**Full documentation: [docs/services/display/](../../docs/services/display/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-display` |
| Version | see `VERSION` |
| Compose | `display` (profile `display`) |
| Interfaces | subscribes `audio/status`, `audio/error`, `rfid/*`, `led/usage-denied`, `system/service-error`, `display/config/reload`; polls the backend for sleep timer, session and network status; `GET /health`, `POST /test` |
| Config | `config/display.json` — written by the backend, mounted read-only here |

Needs I2C enabled on the host (`raspi-config` → Interface Options → I2C). The
panel shares `/dev/i2c-1` with the RFID reader, which is why the render loop
pushes only what actually changed.

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/display-service/tests -q
```

No hardware needed — the whole visual layer is pure PIL and the panel is behind
a `FakePanel`.

## Where to make changes

- `src/display_service/render/` — one module per screen, each drawing a whole
  128×64 frame. Pure PIL, no device: that is what keeps them testable.
- `src/display_service/main.py` — `_current_screen()` decides which screen owns
  the panel; the render loop, the fingerprint and the backend polls live here.
- `src/display_service/infrastructure/display_controller.py` — opening the
  panel and the partial frame pushes.
- `src/display_service/core/` — the state cache, Knuffel's behaviour, the night
  window.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
