# Media Downloader Service

Standalone microservice for local media import: it takes a media URL, reads the
audio track, converts it to MP3 (192 kbps by default) and stores it in the
shared audio volume. REST only — no MQTT, no database, no shared-lib, so it
stays extractable as a standalone package. The backend is its only caller.

**Full documentation: [docs/services/media-downloader/](../../docs/services/media-downloader/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-media-downloader` |
| Version | see `VERSION` |
| Compose | `media-downloader` (profile `media`) |
| Interfaces | REST on `8007`: `GET /health`, `GET /info`, `POST /download`, `GET /download/progress/{job_id}` |
| Config | environment only — `AUDIO_TRACKS_DIR`, `AUDIO_BASE_DIR`, `AUDIO_QUALITY`, `MAX_FILESIZE_MB`, `LOG_LEVEL` |

## Lawful media import

Import is only permitted if you hold the necessary usage and reproduction
rights or a statutory exception applies — your own recordings, public domain
works, or content with the explicit permission or licence of the rights holder.
Responsibility rests with you as the user: neither this service nor the backend
can assess the rights situation of a given URL, and the domain allow-list is a
technical safeguard against arbitrary fetch targets, not a legal assessment.
The project is not intended to circumvent technical protection measures or
access restrictions, and offers no parameters for cookies, credentials, tokens
or decryption keys.

*Deutsch:* Der Import ist nur zulaessig, wenn du die erforderlichen Nutzungs-
und Vervielfaeltigungsrechte besitzt oder eine gesetzliche Erlaubnis greift.
Die Verantwortung liegt bei dir; weder dieser Service noch das Backend koennen
die Rechtslage einer konkreten URL bewerten. Das Projekt ist nicht dafuer
bestimmt, technische Schutzmassnahmen oder Zugangsbeschraenkungen zu umgehen.

Questions or notes about rights to importable content:
[GitHub Issues](https://github.com/Opnek90/Minabox/issues).

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/media-downloader-service/tests -q
```

No network and no ffmpeg needed — yt-dlp is stubbed.

## Where to make changes

- `src/media_downloader_service/downloader.py` — the yt-dlp option dict,
  progress hooks, the thumbnail embed fallback. The option dict is built from
  scratch on every call and must stay closed to outside input.
- `src/media_downloader_service/main.py` — the four routes, the
  one-download-at-a-time semaphore, the job-progress registry.
- `src/media_downloader_service/config.py` — the five environment variables.

The domain allow-list and the retry logic are **not** here — they live in the
backend. Section 9 of the architecture document maps common changes to files
and lists the invariants a change must not break.
