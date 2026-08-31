# Audio Service

The only service that produces sound. It takes playback commands over MQTT,
plays local files and streams through libVLC on a PulseAudio/PipeWire sink of
the host, and reports its state back over MQTT. No playlists, no database —
that is the backend's job.

**Full documentation: [docs/services/audio/](../../docs/services/audio/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-audio` |
| Version | see `VERSION` |
| Compose | `audio` (always on) |
| Interfaces | subscribes `audio/play|pause|stop|set-volume|volume-up|volume-down|mute-toggle|switch-device|config/*`; publishes retained `audio/status`, plus `audio/error` and `audio/position-report`; REST on `8003`: `/health`, `/api/v1/status`, `/devices`, `/switch-device`, `/test-tone`, `/troubleshoot` |
| Config | `config/audio.json`; playback state in `state/audio_state.json` |

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/audio-service/tests -q
```

No libVLC and no sound server needed — the tests are written to run without
them. The service itself is not meaningfully runnable off the box.

## Where to make changes

- `src/audio_service/core/service.py` — the orchestration: command handlers,
  status loop, device switching, config reload.
- `src/audio_service/infrastructure/vlc_backend.py` — the playback engine, the
  pipeline prewarm, and the volume clamp that is the child protection.
- `src/audio_service/core/mqtt_handler.py` — topic → command routing.
- `src/audio_service/infrastructure/pulse_detector.py` — sink discovery.
- `src/audio_service/core/troubleshoot.py` — the sound-repair chain behind the
  WebUI button (its host half lives in host-helper).

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
