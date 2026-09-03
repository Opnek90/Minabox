# TTS Service

The voice of the box. Takes a sentence and hands back the path to a WAV file
that says it, synthesised locally with [Piper](https://github.com/rhasspy/piper)
and cached on disk. It is the optional `voice` component: a box without it
behaves exactly as it always did.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-tts` |
| Source | `services/tts-service/src/tts_service/` |
| Version | `services/tts-service/VERSION` |
| Compose service | `tts` (profile `voice`) |
| Runtime | Python 3.13, FastAPI, plus the Piper binary |
| Speaks | REST on `:8008` (host `127.0.0.1:8008`) |
| Needs | nothing at runtime — no broker, no backend, no network |

## 1. Purpose & Responsibility

**Responsible for:** turning text into an audio file, and not making the same
file twice.

**Not responsible for**, and this is the whole boundary:

- **What the box says, and when.** That is the backend
  (`core/announcements.py`): it decides an event is worth a sentence, applies
  the parent's switches, picks the wording out of
  `resources/announcements.json` and substitutes the card name.
- **Playing anything.** The audio service does that, through its `announce`
  command. This service has no sound output and no PulseAudio access at all.
- **Knowing what is playing.** It never subscribes to MQTT and is told nothing
  about the box's state. A request is a sentence and a language, and that is
  the entire contract.

The reason it is a container of its own is written down in
[docs/services/README.md](../README.md#what-earns-a-container-of-its-own):
Piper is a heavy dependency — a binary with a bundled ONNX runtime, plus a
voice model per language — and it has no business sitting in the backend image
of every box, including all the ones that never switch announcements on.

## 2. File & Folder Structure

```
services/tts-service/
├── Dockerfile              # three stages: wheels, Piper + voices, runtime
├── VERSION
├── requirements.txt        # FastAPI, uvicorn, pydantic, structlog. No Piper.
├── README.md               # signpost
├── src/tts_service/
│   ├── main.py             # ← the endpoints, and the synthesis lock
│   ├── synthesizer.py      # ← the long-lived Piper processes, and the atomic rename
│   ├── cache.py            # ← clip naming, LRU pruning
│   ├── voices.py           # ← language → voice file, and the fallback
│   ├── models.py           # request/response schemas
│   └── config.py           # environment parsing
└── tests/
    ├── test_speak_api.py   # the endpoint against a shell-script "Piper"
    ├── test_synthesizer.py # the process surviving, failure, hang, empty output
    ├── test_cache.py       # naming and what pruning throws away
    ├── test_voices.py      # unknown language, missing voice file
    └── test_tts_config.py
```

The four marked files carry the behaviour; the rest is plumbing.

## 3. Runtime Flow

Startup creates the cache directory and logs which languages it can actually
speak. A box whose voice files failed to arrive is **not** taken down for it:
the container stays up and `/health` reports `degraded`, which is a far better
diagnosis than a restart loop.

A `POST /speak` then goes:

1. Refuse empty text, and text longer than `TTS_MAX_TEXT_LENGTH`. The API has
   no authentication, so the cap is enforced here and not only in the backend.
2. Normalise the language (`de-DE` → `de`, anything unknown → German).
3. Look for the clip. The name is `sha256(voice + "\n" + text)`, truncated —
   which is both the equality check and the reason a card name can be used as
   a file name at all.
4. On a hit: touch the file (so pruning takes the phrases nobody asks for) and
   answer. This is the normal case — a box says the same dozen sentences over
   and over.
5. On a miss: take the synthesis lock, check once more under it, and hand the
   phrase to the **running** Piper for that voice — one line of JSON on its
   stdin, never on a command line, because a card name is arbitrary user text.
   The process is started on first use and kept; see 3.1 for why.
6. Piper writes to a temporary name next to the target, which is then renamed
   into place. The cache directory is shared with the audio service, and the
   rename is what stops it from ever opening a half-written clip — a truncated
   announcement sounds like a fault in the box.
7. Prune the cache down to its limits, in a thread.

The lock is deliberate: Piper saturates a Raspberry Pi core, and two card scans
at once would otherwise make both syntheses slower than either alone.

A Piper that fails, hangs or dies is killed and dropped rather than reused: a
phrase that timed out may still be on its way down the pipe, and a stream that
might hand back a stale answer is worse than a cold start.

### 3.1 What a phrase costs

Measured end to end on a Raspberry Pi 4 with the bundled "low" voice:

| | |
| --- | --- |
| A phrase already in the cache | ~70 ms |
| A new phrase, Piper already running | 1.5 – 2.3 s |
| The first phrase after the container started | ~7 s |
| A new phrase, if Piper were started per phrase | 4 – 5 s |

Two things follow, and both are load-bearing:

**Piper is kept running.** The last row is what this service did first: the
63 MB model was read into the process on every phrase, and that cost more than
the synthesis itself. One long-lived process per voice pays it once per
container.

**The cache is not an optimisation.** It is the difference between an
announcement and a two-second pause with an announcement at the end of it. A
box says the same dozen sentences — the cards in the basket, "I do not know this
card" — so after the first play of each card it is in the first row for good.

The remaining seconds are why the backend never waits for an announcement on a
path where something else is (see
[its section 3.9](../backend/README.md#39-spoken-announcements)).

## 4. Public Interfaces

### 4.1 MQTT

None. This service is not on the broker — it is called by the backend over
HTTP and speaks to nobody else.

### 4.2 REST

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| `GET` | `/health` | – | `status` (`healthy`/`degraded`), `service`, `version`, `uptime_seconds`, `languages`, `piper_available` |
| `GET` | `/voices` | – | `voices: [{language, voice}]` — the languages installed right now |
| `POST` | `/speak` | `{text, language?}` | `{path, language, voice, cached, bytes}` |

`POST /speak` status codes:

| Code | Meaning |
| --- | --- |
| `200` | The clip is at `path`, freshly made or from the cache. |
| `422` | Empty text, or longer than the cap. |
| `503` | No voice installed for that language, or Piper failed or hung. |

`path` is a path, not audio. Both containers mount the clip volume at
`/announcements`, so the string in the answer is a string the audio service can
open — which saves moving a WAV file through two HTTP hops on every card scan.

## 5. Configuration

### 5.1 Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG` switches to readable console output. |
| `TTS_CACHE_DIR` | `/announcements` | Where the clips go. Must be the path the audio service mounts. |
| `TTS_CACHE_MAX_FILES` | `500` | Prune target, by count. |
| `TTS_CACHE_MAX_BYTES` | `67108864` | Prune target, by size (64 MB). |
| `TTS_TIMEOUT_SEC` | `10` | Deadlock guard around Piper, not a budget. |
| `TTS_MAX_TEXT_LENGTH` | `280` | An announcement is a sentence, not a chapter. |
| `PIPER_BINARY` | `/opt/piper/piper` | The bundled executable. |
| `PIPER_ESPEAK_DATA` | `/opt/piper/espeak-ng-data` | Phoneme data from the same tarball. |
| `PIPER_VOICES_DIR` | `/opt/piper/voices` | Where the `.onnx` models live. |
| `TTS_VOICE_DE` / `TTS_VOICE_EN` | see `voices.py` | Override the model file for a language, without a new image. |

### 5.2 Config file

None. The service holds no user decision — every one of them lives in the
backend's `general_settings.json` and travels with the request.

## 6. Dependencies

- **Piper**, from its GitHub release as a self-contained Linux tarball
  (executable, ONNX runtime, espeak data). Deliberately not the `piper-tts` pip
  package: that pulls in `onnxruntime` and `piper-phonemize`, whose wheels have
  to exist for exactly this Python version on arm64 — and a box that cannot be
  built is worse than one that speaks a little later.
- **Voice models**, one per language, downloaded at build time from
  `rhasspy/piper-voices`. Bundled rather than fetched at first start, so
  switching the component on is not a second chance to fail.
- **Nothing at runtime.** No broker, no backend, no internet. A box in a
  children's room keeps talking with the router unplugged.

## 7. Errors, Health & Logging

| `/health` `status` | When |
| --- | --- |
| `healthy` | At least one voice file is readable. |
| `degraded` | None is — the service is up and answering, but every `/speak` will be a 503. |

Worth grepping for:

| Event | Meaning |
| --- | --- |
| `no_voice_available` | Startup found no model. Check `PIPER_VOICES_DIR` in the image. |
| `synthesis_failed` | Piper returned non-zero, hung, or wrote nothing. The message carries its stderr. |
| `clip_created` / `clip_cache_hit` | One announcement, made or reused. |
| `cache_pruned` | How many clips were dropped, and what is left. |

Every failure here is a 503, never a 500: the backend treats a missing clip as
"no announcement this time" and carries on, so nothing about a card scan
depends on this service answering.

## 8. Development & Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/tts-service/tests -q
.venv/bin/ruff check services/tts-service
```

The tests need neither Piper nor a voice model: `synthesizer` and the endpoint
are exercised against a shell script standing in for the binary, which is what
lets the failure cases — non-zero exit, a hang, a zero-byte WAV — be tested at
all.

To build and run it on a box:

```bash
./scripts/build-local.sh tts
MINABOX_TTS_TAG=local docker compose --profile voice up -d tts
```

```bash
curl -s -X POST localhost:8008/speak -H 'content-type: application/json' \
  -d '{"text":"Die Sendung mit der Maus","language":"de"}'
```

## 9. Extending the Service

| I want to ... | Start in | Also touch |
| --- | --- | --- |
| add a language | `src/tts_service/voices.py` (`DEFAULT_VOICES`) | `Dockerfile` (download the model), `backend .../resources/announcements.json`, `admin.json` locales |
| swap the voice for a language | `Dockerfile` (`VOICE_DE`/`VOICE_EN` build args) | nothing — or set `TTS_VOICE_DE` on a running box |
| change a wording | `backend .../resources/announcements.json` | nothing here |
| add a new announcement | `backend core/announcements.py` | `resources/announcements.json`, the settings form |
| make the cache bigger | `src/tts_service/config.py` | `docker-compose.yml` if it should be settable per box |

**Invariants**

- **The clip is written under a temporary name and renamed.** The directory is
  shared with a reader that has no idea a synthesis is in progress; without the
  rename it would eventually play half a file.
- **Piper stays running between phrases.** Starting one per phrase costs more
  than the synthesis does (3.1). Whatever replaces it has to keep that
  property.
- **A Piper that misbehaved is killed, not reused.** Its stdout may still be
  carrying the answer to the phrase that timed out.
- **Piper's stderr is drained continuously.** It logs a few lines per phrase;
  nobody reading them fills the pipe buffer and wedges the process mid-sentence.
- **The text goes to Piper on stdin.** It contains card names, which are
  arbitrary user text.
- **The file name is a hash.** Same reason, plus it is what makes the cache a
  cache.
- **A failure is a 503, never a crash.** Nothing upstream may be made to wait,
  fail or retry because a phrase could not be made.
- **The cache path is the same string in both containers.** The answer of
  `/speak` is handed to the audio service unchanged; a different mount point on
  either side and every announcement is a file-not-found.

## 10. Related Documents

- [services/tts-service/README.md](../../../services/tts-service/README.md) — the signpost next to the code
- [docs/services/audio/README.md](../audio/README.md) — the `announce` command and the ducking
- [docs/services/backend/README.md](../backend/README.md) — where the phrases and the switches live
- [docs/services/README.md](../README.md) — the optional components, and what earns a container
- [docs/Framework.md](../../Framework.md) — profiles and the update matrix
