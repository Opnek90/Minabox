# TTS Service

Turns a short sentence into a WAV file, locally and offline, so the box can say
things instead of only blinking.

**Full documentation: [docs/services/tts/](../../docs/services/tts/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-tts` |
| Version | see `VERSION` |
| Compose | `tts` (profile `voice`) |
| Interfaces | REST on `:8008` (host `127.0.0.1:8008`), no MQTT |
| Config | environment only |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/tts-service/tests -q
```

## Where to make changes

- `src/tts_service/main.py` — the two endpoints, and the lock that keeps two
  syntheses off the same Raspberry Pi core.
- `src/tts_service/synthesizer.py` — the long-lived Piper process per voice
  (starting one per phrase costs more than the synthesis does), and the rename
  that keeps a half-written clip invisible.
- `src/tts_service/cache.py` — clip naming and least-recently-used pruning.
- `src/tts_service/voices.py` — which voice speaks which language.
- `Dockerfile` — where Piper and the voice models come from.

The phrases themselves are **not** here: what the box says, and when, is
decided in the backend (`core/announcements.py`,
`resources/announcements.json`).
