# Backend Service

The central orchestration and data hub. It is the only component that owns the
database, it translates between the internal MQTT bus and the outward-facing
REST/WebSocket interface of the WebUI, and it holds every decision that spans
more than one service — which card plays what, when playback ends, whether a
child is still allowed to listen.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-backend` |
| Source | `services/backend-service/src/backend_service/` |
| Version | `services/backend-service/VERSION` |
| Compose service | `backend` (no profile — always on) |
| Runtime | Python 3.13, asyncio, FastAPI/uvicorn, SQLAlchemy + SQLite |
| Speaks | REST `/api/v1` and WebSocket `/ws` on port `8080`; MQTT; HTTP to audio, host-helper, media-downloader and tts |
| Needs | `/data` (database, settings, static files), `/mnt/audio`, the other services' config directories, the Docker socket (read-only) |

## 1. Purpose & Responsibility

- Sole owner of the SQLite database (tag mappings, playlists, tracks, streams,
  podcasts, statistics).
- MQTT ↔ WebSocket bridge, so the WebUI sees hardware events in real time.
- REST API for synchronous queries and commands.
- Cross-service workflows: tag scan → content lookup → audio command.
- Configuration management on behalf of the button, LED, RFID, audio and
  display services.
- Media management: uploads, metadata and cover art, asynchronous URL import.
- Parental controls: allowed time windows, daily listening limit, blocked tags.
- Diagnosis: system alerts, temperature history, update check, debug export.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Any direct hardware access (GPIO, I2C, SPI) | rfid, button, led, display |
| Audio decoding or playback | audio service |
| Button debouncing, LED patterns, screen layout | the respective device service |
| Anything needing host privileges (reboot, network, USB, backup, OS update) | host-helper — the backend validates and proxies |
| The media download itself | media-downloader |
| Synthesising a spoken phrase | tts |
| Multi-tenancy | not supported: one box is one backend instance |

Web authentication exists but is optional: without a configured password every
API path is open on the local network. See 4.5.

## 2. File & Folder Structure

```
services/backend-service/src/backend_service/
├── main.py                     runtime entry point: config, logging, signals
├── app_factory.py              ** the wiring ** — BackendService orchestration
│                               and the FastAPI app factory
├── config.py                   load_app_config(): env + general_settings.json + backend.json
├── config_manager.py           thin wrapper around shared_lib JsonConfigManager
├── config_schema.py            EnvConfig, BackendServiceConfig, AppConfig
├── exceptions.py               MinaboxBackendError and friends
├── api/                        one router per resource, all mounted under /api/v1
│   ├── routes_audio.py         playback control, sleep timer, session, audio proxy
│   ├── routes_auth.py          web login/logout, password, protected areas
│   ├── routes_config.py        the other services' config files, general settings, logo
│   ├── routes_debug.py         debug export: build, preview, download, options
│   ├── routes_host.py          host-helper proxy (power, network, WiFi, USB, BT, backup)
│   ├── routes_tags.py          RFID tag mapping CRUD
│   ├── routes_tracks.py        track CRUD, upload, URL import, cover art,
│   │                           metadata backfill
│   ├── routes_playlists.py  routes_streams.py  routes_podcasts.py
│   ├── routes_track_folders.py  routes_stream_folders.py  routes_podcast_folders.py
│   ├── routes_rfid.py  routes_scan_history.py  routes_stats.py  routes_system.py
│   └── websocket.py            WebSocketManager: connections, greeting, broadcast
├── core/
│   ├── db_manager.py           ** SQLITE_VERSION lives here ** — engine, sessions,
│   │                           PRAGMAs, SCHEMA_VERSION, migrations
│   ├── mqtt_client.py          handler registry, wildcard dispatch, publish contract
│   ├── mqtt_handlers.py        dispatcher that owns the shared playback state
│   ├── handlers/
│   │   ├── rfid_handler.py     ** the central workflow ** — scan → lookup → play
│   │   ├── audio_handler.py    status transitions, statistics accumulator, auto-advance
│   │   ├── button_handler.py   button actions, next/prev, repeat/shuffle, loop decision
│   │   ├── timer_handler.py    sleep timer, bedtime fade, loop guard, fade-out-and-stop
│   │   └── utils.py            shared playback-event helpers
│   ├── session_manager.py      in-memory playback session: queue, index, shuffle, repeat
│   ├── usage_limits.py         allowed time windows and the daily listening limit
│   ├── announcements.py        what the box says out loud, and when
│   ├── playback_settings.py    playback_end_behavior and the loop guard
│   ├── playback_stats.py       listening minutes: today, total, live
│   ├── resume_position.py      per-URI resume positions
│   ├── rfid_settings.py  sleep_settings.py  media_settings.py
│   ├── track_metadata.py       format-aware tag + embedded-cover reader (ID3, Vorbis, MP4)
│   ├── online_metadata.py      optional MusicBrainz / Cover Art Archive lookup (opt-in)
│   ├── auth.py                 auth_settings.json, bcrypt, JWT session token
│   ├── api_errors.py           ApiError: HTTP error with a stable, translatable code
│   ├── container_registry.py   container discovery and stats via the Docker socket
│   ├── update_check.py         running versions against the release manifest
│   ├── component_catalog.py    what the optional components are, for a box
│   │                           that does not have them yet
│   ├── system_alerts.py        active alerts, keyed by code, most severe wins
│   ├── temperature_logger.py   background loop: sample, retain, alert
│   ├── podcast_fetcher.py      background loop: fetch RSS, insert new episodes
│   └── debug_export/           the diagnostic archive — see docs/DebugExport.md
├── infrastructure/media_downloader_client.py   HTTP client with retries
├── middleware/auth.py          session-cookie guard for protected path prefixes
└── models/
    ├── database.py             SQLAlchemy models
    ├── schemas.py              re-export hub
    └── schemas_{audio,config,content,enums,error,rfid,system,ws}.py
```

Connection handling, reconnect backoff, subscription replay and status replay
are **not** implemented here — they come from `shared_lib.mqtt.BaseMQTTClient`.
`core/mqtt_client.py` only adds the handler registry with wildcard matching and
the backend's own publish contract: **unlike the device services, a failed
publish is raised as `MQTTPublishError`** so an HTTP caller learns about it.

### 2.1 Data model

SQLite through SQLAlchemy at `DATABASE_PATH` (default `/data/minabox.db`). The
connection sets `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` and
`temp_store=MEMORY` — WAL is what lets a read run while a write is in flight,
which matters because the same process serves the API and the MQTT loop.

| Table | Purpose |
| --- | --- |
| `tags` | tag UID → content mapping; `disabled` blocks a card, `content_*` may be `NULL` for unassigned cards |
| `tag_scan_events` | one row per scan attempt: `play`, `blocked` or `unassigned` |
| `tracks` | local files and imported media; `source_uri` is the absolute path |
| `track_folders` | self-referencing folder tree for tracks |
| `playlists` / `playlist_tracks` | playlists and their ordered members (unique per position) |
| `streams` / `stream_folders` | web radio; not part of playlists |
| `podcasts` / `podcast_episodes` / `podcast_folders` | feeds and their episodes (unique per feed and URI) |
| `playback_events` | one playback session for statistics; `listened_ms` is the measured listening time |
| `track_resume_positions` | resume position per `source_uri` |
| `temperature_readings` | temperature samples, retained for 30 days |

Cover art is not stored in the database — only its URL. The files live under
`STATIC_DIR/covers/` as `track_{id}`, `playlist_{id}`, `stream_{id}` or
`podcast_{id}`.

**Schema version and migrations.** The database survives every update — only
the containers are replaced. New code therefore meets old data, and a rollback
means old code meets new data.

`SCHEMA_VERSION` in `core/db_manager.py` makes that difference visible. It is
stored in SQLite's own `PRAGMA user_version`, so it needs no table of its own
and a database predating the counter reads as `0`. **The number is raised only
when a change stops being backwards compatible** — when rows move, columns
disappear or change meaning. A new column that older versions simply ignore
needs no bump.

If the database reports a **higher** version than the code expects, the service
still starts — a box that refuses to boot cannot be diagnosed either — but it
raises the `db_schema_newer` alert, and `/system/status` and `/system/health`
report it. Without that, an old container would look healthy while quietly
failing to find data a newer version had moved.

On connect the manager runs, in order: `create_all()` for missing tables, a set
of idempotent `ALTER TABLE ADD COLUMN` migrations, the one-time move of
`source_type='stream'` rows from `tracks` to `streams`, and finally the cleanup
of playback events left open by an unclean shutdown. Those orphans are closed
with `ended_at = started_at + listened_ms` rather than "now", so a box that was
off for hours does not inflate the statistics of the day it comes back.

Alembic revisions exist under `alembic/versions/` and `run_migrations()` calls
`alembic upgrade head` at startup. Because `create_all()` has already created
every table by then, the Alembic chain is effectively inert on a fresh install;
the column migrations above are what actually maintains an existing database.

## 3. Runtime Flow

### 3.1 Startup and shutdown

`main.py` loads the configuration, sets up structured logging with the ring
buffer processor attached, installs SIGTERM/SIGINT handlers and hands over to
`BackendService`.

Startup order: database (connect, migrate, check the schema version), audio
storage directory, MQTT client, subscriptions, injection of the client into the
route modules, the retained `config/general` announcement, the three background
loops (podcast fetch, temperature log, update check), and finally the uvicorn
server.

**Startup does not wait for the broker.** The MQTT client connects in the
background and retries forever; that dependency is what used to take the
services down when the broker restarted. The retained announcement uses
`publish_state()`, which does not raise and is replayed after a reconnect, so a
broker outage neither fails the boot nor loses the retained value.

Shutdown reverses it: stop the API server (5 s grace), cancel the background
tasks, stop and disconnect MQTT, close the pooled host-helper client, dispose
the database engine.

### 3.2 Tag scan → playback

The central workflow, in `core/handlers/rfid_handler.py`:

1. `rfid/tag-scanned` arrives with a `tag_id`.
2. Two guards suppress repeats: a five second per-tag cooldown, and a check
   that ignores a rescan of the tag that is already playing within 15 seconds.
   **Without them a card resting on the reader restarts itself.**
3. Look up the tag. Unknown → publish `rfid/unknown-tag`, broadcast
   `tag_not_found`, record the scan as `unassigned`, stop.
4. Disabled → publish `rfid/tag-blocked`, broadcast `tag_blocked`, record the
   scan as `blocked`, stop.
5. Check the parental controls (3.5). Denied → publish `led/usage-denied`,
   broadcast `usage_denied`, stop.
6. Record the scan as `play`, update `last_scanned_at`, and dispatch on
   `content_type`:
   - **playlist** — load the members in order, create a session (shuffled), open
     a playback event, publish `audio/play` for the first track;
   - **track** — single-track session, open a playback event, resolve the resume
     position, publish `audio/play`;
   - **stream** — open a playback event and publish `audio/play` with
     `track_id="stream-<id>"`;
   - **podcast** — pick the newest episode, open a playback event, resolve the
     resume position, publish `audio/play` with `track_id="podcast-<id>"`.
7. Broadcast the resulting `repeat_mode` and `rfid_scanned` to the WebUI.

**Learning mode.** The WebUI enables it with `POST /rfid/learning-mode`, which
publishes `rfid/cmd/set-mode`. The RFID service then reports scans on
`rfid/tag-scanned-learning` instead. The backend only checks whether the UID is
already mapped and broadcasts `rfid_scanned_learning`; the WebUI asks the user
what to assign and posts the mapping to `POST /tags`.

### 3.3 End of content, repeat and the loop guard

When the last track runs out, the audio service reports `stopped` and
`AudioHandler` calls `ButtonHandler._handle_next()` — unless the stop was
deliberate.

The `deliberate_stop` flag is consumed once on **every** stop transition. Every
deliberate stop also clears `playback_intent_active`; while only the
`deliberate_stop` branch reset the flag it stayed set and swallowed the next
natural end of track.

With no next track, `_loop_decision()` reads `playback_end_behavior` from
`general_settings.json`:

| Value | Behaviour |
| --- | --- |
| `stop` (default) | send `stop` to the audio service |
| `repeat` | reset the session to the first track and play again |
| `repeat_while_tag` | like `repeat`, but only while `rfid/presence` reports a card |

The first repetition starts `TimerHandler.start_loop_guard()` with
`playback_loop_guard_minutes` (`0` disables it). When it expires,
`fade_out_and_stop()` fades the volume down and stops, so a card left on the
reader cannot keep the box playing for hours. **It is deliberately a timer
rather than a check at the track boundary:** a long audiobook on repeat would
otherwise overshoot the limit by its own length. `_loop_decision()` checks the
same limit again at the track boundary as a backstop. `mark_deliberate_stop()`
cancels the guard, and the guard verifies on firing that the same session is
still running and that repeat is still on.

**`fade_out_and_stop()` is the single path for every case where the box stops on
its own** — sleep timer, daily limit, loop guard. With the bedtime fade switched
off it is a plain stop. Two details matter: the fade aborts as soon as
`playback_intent_active` is gone (the content can run out mid-fade, and without
the abort the fade would keep turning the volume down long after playback
ended), and the volume before the fade is restored afterwards (otherwise the box
stays mute after every sleep timer and looks broken the next morning).

### 3.4 Resume positions and statistics

The audio service reports `audio/position-report` on stop and pause. The backend
stores the position keyed by `source_uri` — the only identifier the two services
share. Positions below 5 s are not stored (the user barely started), and a track
with less than 10 s remaining clears its entry instead so the next play starts
from the beginning. Streams are ignored. On the next scan the position is
applied only when `resume_on_tag_rescan` is on (default: on).

`AudioHandler` keeps an in-memory accumulator of actual playing time and flushes
it into `playback_events.listened_ms` every 60 s, so a crash loses at most a
minute and the dashboard can show a running total. **The wall-clock fallback
(`ended_at - started_at`) was removed:** after a power loss it counted the
downtime as listening time. Each event is capped at 120 minutes so a single
runaway event cannot dominate the totals.

### 3.5 Parental controls

Three independent mechanisms, all read fresh from `general_settings.json` on
every access so a change in the WebUI takes effect without a restart:

- **Blocked tags** — `tags.disabled`; checked on every scan.
- **Allowed time windows** — `usage_times_enabled` plus `allowed_usage_times`
  (weekday, start, end). A window that wraps past midnight is handled.
- **Daily limit** — `daily_limit_enabled` and `daily_limit_minutes`, compared
  against today's completed listening minutes in the host's local timezone.
  Enforced when a tag is scanned, when the REST API starts playback, and at
  every track boundary; the last of these fades out instead of cutting off.

With the announcements switched on (3.9) both limits also get a voice: a
warning a settable number of minutes before the earlier of the two runs out,
and a sentence when the box stops itself. The warning is the one thing here
that needs a timer of its own — the limits have a moment to hang off, a warning
does not (`handlers/timer_handler.py`).

### 3.6 Media import

**Upload** — `POST /tracks/upload` creates the record first, then writes the file
to `AUDIO_STORAGE_PATH/{track_id}/original<ext>` and reads its tags. Both steps
run in a worker thread via `asyncio.to_thread`: writing a large audiobook to the
SD card takes seconds, and on the event loop that would freeze every other
request including the player WebSocket. `core/track_metadata.py` reads title,
artist, album and duration across ID3, Vorbis (FLAC/OGG/Opus) and MP4/M4A, and
extracts the embedded front cover to `STATIC_DIR/covers/track_<id>.<ext>` —
capped at 3 MB. Artist and album only fill in fields the upload form left blank.
If the file carries none of that **and** `online_metadata_lookup_enabled` is on,
a fire-and-forget background task asks the online lookup for the rest so the
upload response stays quick.

**Metadata backfill** — `POST /tracks/metadata/backfill` starts one background
run over every stored file track whose artist, album or cover is still empty:
it re-reads each file's own tags first, and only falls back to the online
lookup (when enabled) for what is still missing. `GET /tracks/metadata/backfill`
reports `{running, total, processed, updated, online_used, finished_at, error}`
from a module-level dict; only one run at a time (409 otherwise).

**Online lookup** — `core/online_metadata.py`, behind
`online_metadata_lookup_enabled` (default off, because it sends the track title
and artist to a third party). Queries MusicBrainz for the recording and the
Cover Art Archive for a front cover, with a descriptive `User-Agent` and a
≥ 1.1 s throttle between MusicBrainz calls. Strictly best effort: any failure
yields nothing.

**URL import** — `POST /tracks/from-url` returns HTTP 202 immediately:

1. Strip playlist parameters from the URL, then check the host against the
   configured allow-list (`core/media_settings.py`, user-editable in Admin →
   General → media import, default excludes YouTube). The allow-list is a
   technical guard against arbitrary fetch targets; it says nothing about
   whether the caller holds the rights to the content.
2. If a track with the same `source_uri` exists, return HTTP 200 with its id.
3. Create a placeholder record and its directory, mark the status `pending`,
   start a background task.
4. The task calls the media-downloader (three attempts, linear backoff), writes
   the real metadata, and resolves cover art — embedded art first, the remote
   thumbnail as fallback. On failure it deletes the placeholder record and the
   directory again.

`GET /tracks/{id}/download-status` reports `pending`, `downloading`, `done`,
`error` or `unknown`. The status lives in a module-level dict, so a restart
loses in-flight entries and the endpoint answers `unknown`. **That route is
registered before the generic `GET /{track_id}`**, because FastAPI matches
routes in order.

### 3.7 Container discovery, status and update check

`core/container_registry.py` asks the read-only Docker socket which containers
exist. That is the only source that covers *every* container uniformly —
Mosquitto and the nginx-based WebUI speak no MQTT and expose no Minabox health
schema, but Docker knows their state, labels and resource usage. It also answers
when a service hangs, and it reflects what is actually installed: which
containers exist depends on `COMPOSE_PROFILES`, so a box without the LED profile
shows no LED entry instead of a permanent "offline".

Two Compose labels separate a real service from a stray `docker run`, and a
`memory_mb` of `null` means "not measurable here" rather than "uses no memory":
Raspberry Pi OS ships with the memory cgroup controller disabled, and then no
per-container figure exists at all. `/system/status` exposes that as
`memory_stats_available` so the UI can omit the bar instead of drawing an empty
one that looks like a reading.

Without a usable socket, `routes_system.py` falls back to probing each known
service's `/health` — no CPU or RAM then, and only the services in the static
catalogue.

**On both paths the service's own verdict is folded in.** Five services —
`audio`, `rfid`, `button`, `display`, `led` — answer `/health` with a `status`
of their own, and it used to be read by nobody. The container health check asks
only whether the endpoint answers with 2xx, and a degraded service answers 2xx
on purpose, so that a lost broker does not make Docker restart something that is
otherwise fine. A service could therefore report itself as broken and be shown
green: the LED service with not a single usable GPIO pin after a wrong
`GPIO_GID`, or any service whose MQTT connection had gone while the container
kept running.

An entry that reports `degraded` carries `service_status: "degraded"` and its
`state` becomes `degraded` — the fourth state next to `online`, `offline` and
`error`. `error` wins over it: an unhealthy container is the worse news, and a
service that still answers must not talk the entry back up into a milder state.
Only entries that are **online** are probed, and all of them together.

`core/update_check.py` compares the running versions against
`release/release-manifest.json`. Two rules shape it:

- **No network never means "update available".** If the fetch fails, the last
  known state is shown together with the error — never an update nobody could
  verify.
- **Only offer what can be pulled.** The manifest is published with the commit,
  the images only when CI finishes. In that window the manifest knows a version
  the registry does not have yet, so every candidate is checked against the
  registry before it is offered.

Results are cached for six hours. The background loop polls every 30 minutes,
but only while the user has the automatic check switched on.

`core/component_catalog.py` rides along on the same fetch. The manifest also
describes the *optional components* — what each one is for, what hardware it
needs, whether it needs the network — and that block is remembered next to the
cache, so `GET /system/components` can answer as a catalogue that includes the
components this box does not have. The descriptions themselves ship inside the
image (`resources/components.json`), so the catalogue works on a box that has
never reached the internet; the manifest copy only wins when it is there. What
earns a container of its own is written down in
[docs/services/README.md](../README.md).

A cached answer belongs to the box it was computed for, in two ways: the
channel (below) and the set of services. The version list is one row per
*existing* container, so switching a component off under *Maintenance →
Components* drops it — but the cache would keep listing it, and keep offering
an update for six hours that `compose pull` could no longer carry out, because
the profile is gone. A different set of services therefore counts as a miss.
When the fetch then fails and the last known state is shown instead, entries
for components the box no longer has are dropped from it: a version for a
component that is gone is not "last known state" but a leftover.

**Channels.** `update_channel` in the general settings decides which releases a
box is offered: `stable` (the default) reads the manifest's `latest` and never
sees a release candidate, `beta` reads `latest_beta` and gets them as soon as
they are published. The channel of a version is derived from the version string
alone — a pre-release marker (`0.3.0-rc.1`) means beta — so it cannot be set
wrong in two places. A cached result belongs to the channel it was computed
for; after a switch it counts as a miss rather than naming the wrong target.
Switching back to stable is enough to be offered finished releases again, and
the running build keeps showing which channel it came from.

**The way back.** `GET /system/update-history` reads the runs the host-helper
recorded and works out, per service, the version it ran before the most recent
change of it. `POST /system/rollback` puts the named services back on it, along
the same path as an update — backup, pin, pull, restart, verify — only with
older tags.

The decision whether a step back is allowed is made **here**, not in the
host-helper: it is a question about `SCHEMA_VERSION`, and this is the only
service that knows it. Every update sends its schema version along and it is
filed with the run. If the recorded one differs from what this build expects,
the backend cannot be stepped back — the database was migrated in between, and
the older code would look for its data where the newer version no longer puts
it. The candidate is still shown, with the reason; hiding it would leave the
same question unanswered one screen further away. The other services do not
read the database, so they stay free to move on their own.

### 3.8 Diagnosis

`system_alerts.py` holds active alerts keyed by code and shows the most severe
one, so a temporary temperature warning cannot displace the permanent notice
about an incompatible database.

`temperature_logger.py` samples the host temperature every five minutes through
the host-helper, stores it, deletes samples older than 30 days, and raises or
clears the overheating alert at `temperature_warning_celsius` (default 80). The
interval sleep runs after every iteration including the failed ones, so an
absent host-helper cannot turn the loop into a busy loop.

The **debug export** builds a diagnosable snapshot of the box into one ZIP.
Collectors are selected by name from a registry — nothing from the request ever
becomes a path or a command — each runs isolated with a timeout, and its outcome
lands in the manifest as ok, failed or skipped, because "display logs
unavailable" is itself a diagnosis. Every file passes redaction, and the
finished payload is checked against the device's real secrets before it is
written. See [docs/DebugExport.md](../../DebugExport.md).

Two bounded in-memory ring buffers feed it with things that are gone by the time
anyone looks: the last 300 warnings and errors, and the last 500 MQTT messages.
Container logs rotate and MQTT traffic is not persisted at all, yet "the button
press never reached the backend" is only answerable if the last few hundred
messages are still around.

### 3.9 Spoken announcements

`core/announcements.py` is the only place that decides a sentence is worth
saying. Everything else is a one-line call from the handler that already knows
the event happened:

| Phrase key | Raised in | Switch |
| --- | --- | --- |
| `card` | `handlers/rfid_handler.py`, before the play command | `announce_card_name` |
| `card_unknown`, `card_empty`, `card_blocked` | the three dead ends of the same scan | `announce_unknown_card` |
| `limit_warning` | `handlers/timer_handler.py`, on its own timer | `announce_usage_limit` |
| `limit_reached` | `fade_out_and_stop("daily_limit")`, before the fade | `announce_usage_limit` |
| `usage_denied` | `notify_usage_denied` — outside the window *or* over the limit | `announce_usage_limit` |
| `muted` | `handlers/audio_handler.py`, on the `muted` edge in the status | `announce_mute` |

The wordings are **not** in the Python. They live in
`resources/announcements.json`, next to the component descriptions and for the
same reasons: a wording is content, it is translated, and it is the only way
the German phrases can carry real umlauts — a phrase spelled `Hoerzeit` is
spoken "Ho-er-zeit". Placeholders are substituted literally, not through
`str.format`: a card name is arbitrary user text and a brace in it would
otherwise take the announcement down.

The call then asks the [tts service](../tts/README.md) for a clip and publishes
`audio/announce` with its path. **Every step gives up quietly.** A box whose
`voice` component is switched off, whose tts container is still starting, or
whose broker refuses, behaves exactly like a box that was never asked to speak:
`announce()` returns `False` and the card scan carries on. An announcement is a
courtesy — it never blocks anything and never becomes an error somebody has to
acknowledge.

`muted` is announced from the *status*, not from the command, so it covers
every route to muting — the physical button, the WebUI, the player page.

Almost every call goes through `announce_soon`, which does **not** wait for
the phrase. A phrase the box has said before comes back in about 70 ms, but the
first time one is made it costs one and a half to two seconds on a Raspberry Pi
(and about seven for the very first after a restart — see the
[tts service](../tts/README.md#31-what-a-phrase-costs)). The places that raise
one are all places where seconds are expensive: inside a card scan, which is
holding a database session open and is followed by the play command, or inside
an MQTT message handler processing the box's status. None of them depends on
the phrase having been said; the audio service ducks around it whenever it
arrives.

`announce` is awaited in exactly two places, where the announcement *is* the
moment: the warning on its own timer, and the sentence before the box fades
itself out.

## 4. Public Interfaces

### 4.1 REST API

Base path `/api/v1`. Every response error carries a stable `code` — see 7.2.

**Tags and scan history**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tags` | list all tag mappings |
| GET | `/tags/{tag_id}` | one mapping, by raw tag UID |
| POST | `/tags` | create a mapping (learning mode) |
| PUT | `/tags/{tag_id}` | update; explicit `null` clears the content assignment |
| DELETE | `/tags/{tag_id}` | delete a mapping |
| GET / DELETE | `/scan-history/` | scan events newest first (`limit`, `offset`, `tag_id`) / clear |

**Playlists**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/playlists` | list |
| GET | `/playlists/{id}` | detail including ordered tracks |
| POST | `/playlists` | create |
| PUT | `/playlists/{id}` | update, optionally replacing the track list |
| DELETE | `/playlists/{id}` | delete |
| POST / DELETE | `/playlists/{id}/cover` | upload or remove cover art |

**Tracks**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tracks` | list, optionally filtered by `folder_id` (`0` = root) |
| GET | `/tracks/{id}` | detail |
| POST | `/tracks` | create a record (JSON) |
| POST | `/tracks/upload` | upload an audio file (multipart) |
| GET | `/tracks/validate-url` | read metadata for a URL without importing |
| POST | `/tracks/from-url` | start an asynchronous import → **HTTP 202** |
| GET | `/tracks/{id}/download-status` | progress of an import started above |
| POST | `/tracks/metadata/backfill` | fill missing artist/album/cover for existing file tracks → **HTTP 202** |
| GET | `/tracks/metadata/backfill` | progress of the backfill started above |
| PUT | `/tracks/{id}` | update metadata or folder |
| DELETE | `/tracks/{id}` | delete record, file and cover art |
| POST / DELETE | `/tracks/{id}/cover` | upload or remove cover art |

**Streams and podcasts** follow the same shape: `/streams`, `/streams/{id}`,
`/streams/{id}/cover`, and `/podcasts`, `/podcasts/{id}`,
`/podcasts/{id}/episodes`, `/podcasts/{id}/cover`.

**Folders** — one identical router per media type: `/tracks/folders`,
`/streams/folders`, `/podcasts/folders`, each with `GET`, `GET /{id}`, `POST`,
`PUT /{id}`, `DELETE /{id}`. Deleting a folder moves its contents and its child
folders to the root rather than deleting them.

> The folder routers are mounted **before** the plain media routers on purpose.
> Without that ordering FastAPI would match `/tracks/folders` against
> `/tracks/{track_id}` with `track_id="folders"`.

**Audio control**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/audio/status` | last known status from the in-memory cache |
| POST | `/audio/play` | start playback (`track_id`, `playlist_id`, `stream_id`, `podcast_id`, or empty to resume) |
| POST | `/audio/pause` / `/audio/stop` | pause or stop |
| POST | `/audio/next` / `/audio/prev` | queue navigation |
| POST | `/audio/seek` | seek within the current track (`position_ms`); 409 for live streams |
| POST | `/audio/volume` | set volume |
| GET / POST / DELETE | `/audio/sleep-timer` | status, start, cancel |
| GET | `/audio/session` | current queue, repeat mode and shuffle state |
| POST | `/audio/repeat` / `/audio/shuffle` | set repeat mode (`none` \| `all`) / shuffle |
| GET | `/audio/devices` | detected output sinks (proxied to the audio service) |
| POST | `/audio/switch-device` | switch output sink or cycle with `direction: "next"` |
| POST | `/audio/test-tone` | play a short test tone (setup wizard) |
| POST | `/audio/troubleshoot` | walk the sound-repair chain, repair what is safe, end with the tone |
| POST | `/audio/restart-service` | restart only the audio container |

**RFID:** `POST /rfid/learning-mode` — enable or disable learning mode.

**Configuration**

| Method | Path | Purpose |
| --- | --- | --- |
| GET / PUT | `/config/general` | device id, log level, MQTT, timers, parental controls, setup state |
| GET / PUT | `/config/audio` | audio service config (PUT **merges** with the existing file) |
| GET / PUT | `/config/leds`, `/config/buttons`, `/config/display` | those services' config files |
| GET / PUT | `/config/rfid` | RFID service config (flat API shape, nested on disk) |
| GET | `/config/leds/states`, `/config/leds/patterns`, `/config/buttons/actions` | enumerations for the admin UI |
| POST | `/config/leds/test`, `/config/display/test` | trigger a hardware self-test |
| POST / DELETE | `/config/logo` | upload or remove the custom logo |

**Statistics**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/stats/overview` | minutes today and total, daily limit, media counts |
| GET | `/stats/usage-today` | minutes today and the daily limit |
| GET | `/stats/listening-summary` | minutes per day, top tags, top playlists, heatmap |
| POST | `/stats/reset` | delete all playback events |

`minutes_today` in `/overview` and `/usage-today` includes completed events
**and** the running total of the open event (flushed roughly every 60 s), so the
dashboard does not sit at 0 during playback. The two sources are mutually
exclusive, so nothing is counted twice. The daily-limit *enforcement* in
`usage_limits.py` deliberately uses completed events only, so active playback is
not cut off a minute early.

**System and diagnosis**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` (root, outside `/api/v1`) | liveness for the container health check |
| GET | `/system/health` | health with DB and MQTT state |
| GET | `/system/status` | one entry per container: state, version, CPU, RAM, database schema state |
| GET | `/system/capabilities` | per optional component (rfid, led, button, display, media_downloader, voice): installed / running / healthy |
| GET / PUT | `/system/components` | the catalogue of optional components — including the ones this box does not have — and changing the selection (proxied; see host-helper 4.12) |
| GET | `/system/logs?service=&tail=` | container logs (host-helper, then Docker, then file) |
| GET | `/system/update-check?force=` | running versions against the release manifest, for the box's channel |
| GET | `/system/update-history` | the recorded runs, and per service what may be stepped back to |
| POST | `/system/rollback` | body `{services}`; puts them back on the recorded version |
| GET | `/system/alerts` | all active system alerts, most severe first |
| GET | `/system/temperature-history?hours=` | temperature time series |
| POST / GET | `/system/debug-export`, `/preview`, `/download/{id}`, `/options` | diagnostic archive |

**Host operations** — all proxied to the host-helper: power and lifecycle,
storage (`audio-path`, `move-audio`), system (`timezone`, `hostname`,
`board-leds`, `network`, `password`, `ssh-*`, `docker-prune`, `factory-reset`),
update (`update-minabox`, `update-os`, `version`), the optional components
(`components`, `components/status`), `time-status`, `syslog`,
`wifi/*`, `usb/*`, `bluetooth/*`, `backup/*`. The full list is in
`routes_host.py`.

Two rules shape the proxy layer:

- `_proxy()` is strict — a failure reaches the caller. `_proxy_optional()` is
  soft: it returns a neutral fallback whenever anything goes wrong, so a status
  widget cannot break the settings page just because the host-helper is
  restarting.
- **A 401 from the host-helper is reported as 503, not 401.** The WebUI treats
  401 as "your session expired" and would log the user out over what is really a
  server-side misconfiguration.

All host calls share one pooled `httpx.AsyncClient`; creating a client per
request meant a fresh TCP handshake for every button press in the WebUI.

**Static files:** `/static` serves `STATIC_DIR` (default `/data/static`) — the
custom logo and all cover art.

### 4.2 WebSocket

Endpoint `/ws`. The backend pushes; incoming text is only parsed as JSON and
acknowledged with `{"type": "ack"}` — **there are no WebSocket commands.** A
newly connected client immediately receives the last enriched `audio_status`
payload so the player page renders without waiting for the next broadcast.

Every message is `{"type": ..., "data": {...}, "timestamp": ...}`.

| `type` | Sent when |
| --- | --- |
| `audio_status` | audio service reported a status; enriched with title, artist, album, cover URL and queue position |
| `rfid_scanned` | a known tag started playback |
| `rfid_scanned_learning` | a tag was scanned in learning mode (`already_assigned`) |
| `tag_not_found` | scanned tag has no mapping |
| `tag_blocked` | scanned tag is disabled |
| `usage_denied` | outside the allowed time window, or daily limit reached |
| `button_action` | a mapped button action was processed |
| `button_raw_event` | any physical button press (drives the WebUI hardware test mode) |
| `repeat_mode` / `shuffle_mode` | mode changed, at the player or through a new session |
| `sleep_timer_status` | sleep timer started, fired or was cancelled |
| `audio_config` | audio config was written — an open player picks up new volume limits without a reload |
| `system_alert` / `system_alert_cleared` | an alert was raised or withdrawn |

### 4.3 MQTT — subscribed

| Topic | Handler |
| --- | --- |
| `rfid/tag-scanned` | look up the mapping and start playback |
| `rfid/tag-scanned-learning` | report the UID and whether it is already assigned |
| `rfid/tag-removed` | stop playback when the setting says so |
| `rfid/presence` | retained; tracks whether a card lies on the reader |
| `audio/status` | statistics, auto-advance, stream reconnect, WebSocket broadcast |
| `audio/position-report` | persist the resume position |
| `button/+` | every mapped button action |
| `button/raw-event` | every physical press, mapped or not |

`rfid/presence` is retained by the RFID service, so a reconnecting backend
learns the current card state immediately. That is what makes the "repeat while
the card lies there" mode work after a restart.

### 4.4 MQTT — published

| Topic | Payload |
| --- | --- |
| `audio/play` | `track_id`, `source_type`, `source_uri`, `start_position_ms` |
| `audio/pause`, `audio/stop` | `{}` |
| `audio/set-volume` | `volume` |
| `audio/mute-toggle` | `{}` |
| `audio/announce` | `source_uri` (a clip in the shared volume), `duck_percent`, `volume_percent` |
| `audio/switch-device` | `sink_name` or `direction` |
| `rfid/cmd/set-mode` | `mode: "learning" \| "normal"` |
| `rfid/unknown-tag`, `rfid/tag-blocked` | `tag_id`, optional `name` |
| `led/usage-denied` | `event`, `timestamp` |
| `<service>/config/reload` | `{}` for audio, led, button, display |
| `config/general` | retained; currently `log_level` |
| `system/service-error`, `system/service-started` | overheating raised and cleared |

### 4.5 Web authentication

Optional and off by default. `POST /auth/password` sets a bcrypt hash in
`/data/auth_settings.json`; `POST /auth/login` verifies it and sets an HttpOnly
session cookie holding an HS256 JWT valid for 24 hours. The signing secret is
`WEB_AUTH_SECRET`, falling back to `HOST_HELPER_API_KEY`; both are generated by
`install.sh`.

`middleware/auth.py` guards **path prefixes, not individual routes**, and the
**longest matching prefix** decides — so a specific path can sit in a stricter
area than the general prefix it lives under: `/api/v1/audio/restart-service`
restarts a container and is `admin`, while the rest of `/api/v1/audio` is
`player`, which is off by default. Resolving that by map order would have made
the answer depend on where the next entry happens to be added.

| Area | Prefixes |
| --- | --- |
| `admin` | `/api/v1/config`, `/api/v1/system` |
| `media` | `/api/v1/playlists`, `/tracks`, `/streams`, `/podcasts` |
| `dashboard` | `/api/v1/stats` |

Everything outside those prefixes — `/api/v1/audio`, `/api/v1/tags`,
`/api/v1/rfid`, `/api/v1/scan-history`, `/ws`, `/static` — is reachable without
a session. So is `/api/v1/auth/*`, and so is the debug export: it is the one
thing a user still needs when the password itself is the problem, and it
enforces its own private-network check, rate limit and privacy tier instead.

## 5. Configuration

### 5.1 Environment

| Variable | Meaning |
| --- | --- |
| `MINABOX_DEVICE_ID` | box id, forms the MQTT topic prefix |
| `MQTT_BROKER`, `MQTT_PORT` | broker connection |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `API_PORT` | REST port (default 8080) |
| `DATABASE_PATH` | default `/data/minabox.db` |
| `DATA_PATH` | default `/data`; holds the settings and state files |
| `AUDIO_STORAGE_PATH` | default `/mnt/audio/tracks` |
| `STATIC_DIR` | default `/data/static` |
| `CONFIG_SERVICES_PATH` | mount point of the other services' config files |
| `HOST_HELPER_URL`, `HOST_HELPER_API_KEY` | host-helper connection; **without the key every host route answers 503** |
| `WEB_AUTH_SECRET` | JWT signing secret; falls back to `HOST_HELPER_API_KEY` |
| `MEDIA_DOWNLOADER_URL` | default `http://media-downloader:8007` |
| `TTS_SERVICE_URL` | default `http://tts:8008`; only reached when announcements are on |
| `ALLOWED_AUDIO_PATHS` | base paths a media directory may be moved to |
| `HOST_DIAG_ROOT` | default `/host`; root of the read-only host mounts |
| `CORS_ALLOWED_ORIGINS` | allowed origins; `['*']` for local development only |
| `MINABOX_MANIFEST_URL` | override for the release manifest URL |
| `COMPOSE_PROFILES` | which optional components this box has; used to hide what is not installed |

### 5.2 The files this service owns

**General settings** live in `/data/general_settings.json` and are read fresh on
every access. `PUT /config/general` filters the body against an allow-list,
clamps every value, and **merges** with the file on disk so a partial update
from one tab does not drop the keys another tab owns. Changing `log_level` takes
effect in this process immediately and is published retained on `config/general`
so the other services follow.

The announcement settings live in the same file: `announcements_enabled` plus
one switch per topic, the language, the two levels and the warning lead time.
They are read through `core/announcements.py`, which carries their defaults and
clamps, so the settings form and the code that acts on them cannot drift apart.

**Service configs** are the other services' own JSON files, mounted under
`CONFIG_SERVICES_PATH`. `GET` returns the file, `PUT` writes it and publishes
`<service>/config/reload`. Audio is merged rather than replaced, so a partial
update from the parent dashboard (say, only `max_volume`) does not wipe
`enabled_output_devices`. RFID is flattened on read and re-nested on write,
because the admin UI works with a flat shape while the service expects
`{ "reader": { ... } }`.

**`config/backend.json`** holds `session_timeout_min`,
`health_check_interval_sec` and `max_upload_size_mb`. None of them is read
anywhere today; the effective configuration comes from environment variables.

Other persistent files under `DATA_PATH`: `auth_settings.json` (password hash
and protected areas), `update-check.json` (cached update result),
`tmp/debug-export-*.zip` (one-slot preview cache, mode 0600).

## 6. Dependencies

| Service | Relationship |
| --- | --- |
| MQTT broker (Mosquitto) | bus for every internal event |
| RFID service | tag events, presence, learning mode |
| Audio service | playback commands and status; also an HTTP proxy target for devices, the test tone and the troubleshoot chain |
| TTS service | optional (`voice`); asked for a clip per announcement. Absent, unreachable or slow costs the phrase and nothing else |
| Button service | action and raw hardware events |
| LED / display services | receive config reloads and self-test triggers |
| WebUI service | the REST and WebSocket client |
| Media-downloader service | URL import |
| Host-helper service | everything requiring host privileges |

**None of them is required for startup.** The backend comes up without the
broker, without the host-helper (host routes answer 503) and without any device
service.

**Infrastructure.** SQLite at `/data/minabox.db`; audio files under
`/mnt/audio/tracks/` (configurable, movable at runtime); static files under
`/data/static/`; the Docker socket mounted read-only for container discovery;
read-only host mounts under `/host` for the debug export (`/proc`, `/sys`,
`/etc/os-release`, the boot config, the dpkg status, the apt log — nothing
writable, nothing secret).

**Python.** `fastapi` and `uvicorn`, `sqlalchemy` and `alembic`, `aiomqtt`,
`pydantic`, `structlog`, `httpx`, `mutagen` (audio metadata and cover art),
`feedparser` (podcast RSS), `docker` (container discovery), `bcrypt` and
`python-jose` (web authentication), `python-multipart` (uploads).
`minabox-shared` provides the MQTT base client, the logging setup and the config
helpers — see [shared-lib](../shared-lib/README.md).

Compose publishes the backend on `${BACKEND_PORT:-8080}` — the one service
reachable from the network, and the reason the WebUI's Nginx can proxy to it.

## 7. Errors, Health & Logging

### 7.1 Health states

`GET /health` (the container health check) reports:

| Status | Condition |
| --- | --- |
| `healthy` | database up and MQTT connected |
| `degraded` | database up, MQTT not connected — the API is usable, MQTT may still be catching up |
| `unhealthy` | no database |

`GET /api/v1/system/health` is stricter: it additionally reports `unhealthy`
when the database schema is newer than this code expects. The connection is fine
there, but the data may not be where this version looks for it.

### 7.2 REST error format

Every error raised through `ApiError` returns:

```json
{ "detail": "Track 42 not found", "code": "track_not_found" }
```

`detail` is English, developer-facing text meant for logs, `curl` and issue
reports. **`code` is what the WebUI actually shows the user**, translated
through the `errors` i18n namespace with `generic_error` as the fallback for
unknown codes. A typo in `detail` is therefore harmless for the display; a typo
in `code` merely falls back to the generic text instead of showing the wrong
language or raw JSON. Some errors add fields — a rate-limited debug export also
returns `retry_after`.

Status codes in use: `200`, `201` (created), `202` (import started), `204` (no
content), `400`, `401` (no valid session), `403` (daily limit, non-private
client), `404`, `409` (nothing to seek, move already running), `422`, `429`
(export rate limited or already running), `500`, `502` (upstream service error),
`503` (dependency unavailable), `504` (export timed out).

### 7.3 Logging

Structured through structlog, JSON in production. Noteworthy events:

- **Playback:** `tag_found`, `track_playback_started`,
  `playlist_playback_started`, `session_created`, `session_looping`,
  `session_end`, `loop_guard_fired`, `faded_out_and_stopped`,
  `playback_stats_flushed`
- **Suppressed and denied:** `rfid_tag_scan_ignored_cooldown`, `tag_blocked`,
  `tag_scanned_outside_allowed_time`, `tag_scanned_daily_limit_exceeded`
- **Import:** `api_create_track_from_url_accepted`, `download_task_completed`,
  `download_task_failed`, `media_downloader_download_5xx_retry`
- **Metadata:** `track_metadata_read_failed`, `track_cover_saved`,
  `track_metadata_online_enriched`, `track_metadata_backfill_started`,
  `track_metadata_backfill_finished`, `online_metadata_lookup_hit`,
  `online_metadata_lookup_failed`
- **Database:** `db_schema_migrated`, `db_schema_newer_than_code`,
  `db_streams_migrated`, `startup_cleanup_closed_orphaned_events`
- **System:** `system_alert_set`, `system_alert_cleared`,
  `temperature_overheating_published`, `update_not_published_yet`
- **Diagnosis:** `debug_export_created` (with client address and privacy tier),
  `debug_export_secret_blocked`, `debug_export_collector_timeout`

Warnings and errors are additionally kept in the in-memory ring buffer so the
debug export still contains them after the container logs have rotated.
`sqlalchemy.engine` and `alembic.runtime.migration` are silenced; the
`log_level` set in the WebUI is applied to the running process without a
restart.

## 8. Development & Tests

The backend runs without hardware and without the other services — it is the one
service that can be exercised end to end on a development machine, given a
broker.

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/backend-service/tests -q
```

The suite is a set of regression pins around the decisions that are easy to
break silently:

| File | Pins |
| --- | --- |
| `test_auto_advance_flags.py`, `test_fade_out_and_stop.py`, `test_playback_loop_guard.py` | the end-of-content logic of 3.3 — the flags, the fade abort, the guard |
| `test_schema_version.py`, `test_schema_migrations.py` | that `SCHEMA_VERSION` and the migrations stay in step (2.1) |
| `test_container_registry.py`, `test_reported_health.py`, `test_capabilities.py` | container discovery, the folded-in service verdict, the capability answer (3.7) |
| `test_update_check.py` | "no network never means update available", the registry check, what each channel is offered, and that the cache forgets a component that was switched off |
| `test_routes_host_proxy.py` | the strict/soft proxy split, the 401 → 503 rule, and the rollback guard |
| `test_auth_prefix_areas.py` | the longest-matching-prefix rule of 4.5 |
| `test_button_config_validation.py`, `test_display_config_validation.py` | that a config the backend writes is one the device service can load |
| `test_debug_export*.py` | the export contract, the endpoint, the log filter, redaction |
| `test_media_downloader_client.py`, `test_media_settings.py`, `test_track_domain_check.py` | retries, the allow-list, the domain check |
| `test_announcements.py`, `test_limit_warning.py` | that every path of 3.9 gives up quietly, the clamps, both languages, and how much listening time is left |
| `test_track_metadata.py`, `test_online_metadata.py` | tag/cover mapping per format, the cover size cap, and that the online lookup swallows every failure |
| `test_temperature_logger.py`, `test_folder_routes.py`, `test_api_smoke.py`, `test_network_status_public.py` | the loops, folder deletion semantics, route wiring |

```bash
.venv/bin/ruff check services/backend-service
```

```bash
./scripts/build-local.sh backend
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add a REST endpoint | the matching `api/routes_*.py` | a Pydantic schema in `models/schemas_*.py`, the WebUI's `api/` module and `types/api.ts`, an `ApiError` code + its `errors` translation, the table in 4.1 |
| add a table or column | `models/database.py` | an idempotent `ALTER TABLE` in `db_manager.py`; **raise `SCHEMA_VERSION` only if the change is not backwards compatible** (2.1); `test_schema_version.py` |
| change playback behaviour | `core/handlers/` — `rfid_handler` (scan), `audio_handler` (status), `button_handler` (next/repeat), `timer_handler` (timers) | the pinning tests; the flags in 3.3 exist for measured reasons |
| add a WebSocket message | `api/websocket.py` + the handler that raises it | the table in 4.2, `useWebSocketEvent` in the WebUI |
| subscribe to a new MQTT topic | the handler registry in `app_factory.py` | a handler under `core/handlers/`, table 4.3, the publishing service |
| add a setting | `general_settings.json` via `PUT /config/general` — extend the allow-list and clamps in `routes_config.py` | a reader module under `core/` (read fresh, do not cache), `settingsIndex.ts` + both locales in the WebUI |
| add a spoken announcement | `resources/announcements.json` (both languages) | `PHRASE_SWITCH` in `core/announcements.py`, the one call site in the handler that already sees the event, `test_announcements.py` |
| expose another service's config | `routes_config.py` | that service's reload topic, and a validation test like `test_display_config_validation.py` — a config the backend writes must be one the service can load |
| proxy a new host action | `api/routes_host.py` | the host-helper route; choose `_proxy()` or `_proxy_optional()` deliberately |
| add a system alert | `core/system_alerts.py` | its severity, the `errors`/`admin` translations, and who clears it |
| add a debug-export collector | `core/debug_export/collectors/` | register it, give it a description in `descriptions.py`, check redaction — see `docs/DebugExport.md` |

### Invariants

- **The backend is the only writer of the database.** Every other service reads
  its own config file and nothing else.
- **`SCHEMA_VERSION` rises only on a breaking change,** and a newer database
  never stops the service from starting — it raises an alert instead. A box that
  refuses to boot cannot be diagnosed.
- **Settings are read fresh, never cached.** A change in the WebUI has to take
  effect without a restart; a module-level copy silently breaks that.
- **`PUT /config/general` and `/config/audio` merge, they do not replace.** One
  tab must not drop the keys another tab owns.
- **A config the backend writes must be one the device service can load.** An
  invalid `display.json` puts that container into a restart loop.
- **Startup never waits for the broker.**
- **Every error goes through `ApiError` with a stable `code`.** The WebUI
  translates codes, never `detail`.
- **A 401 from the host-helper is reported as 503.** Anything else logs the user
  out over a server-side misconfiguration.
- **Route order matters in FastAPI.** Folder routers before media routers,
  `/tracks/{id}/download-status` and `/tracks/metadata/backfill` before
  `/tracks/{track_id}`.
- **Auth resolves by longest matching prefix,** not by map order.
- **Blocking work goes into a thread.** An upload written on the event loop
  freezes the player WebSocket.
- **The daily limit fades out at a track boundary, it does not cut off.**
- **Statistics count measured playing time,** never wall-clock — a power loss
  must not read as listening.
- **An announcement never blocks, fails or delays what raised it.** Every path
  through `core/announcements.py` returns `False` instead of raising; a card
  scan must not get slower because a container is starting up.
- **Announcement wordings stay in `resources/announcements.json`.** In the
  Python they could not carry umlauts, and a phrase spelled `Hoerzeit` is spoken
  as one.

## 10. Related Documents

- [`services/backend-service/README.md`](../../../services/backend-service/README.md) — the short signpost next to the code
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/DebugExport.md`](../../DebugExport.md) — the diagnostic archive in full
- [`docs/services/webui/README.md`](../webui/README.md) — the client of this API
- [`docs/services/host-helper/README.md`](../host-helper/README.md) — the target of every host proxy route
- [`docs/services/audio/README.md`](../audio/README.md), [`rfid`](../rfid/README.md), [`button`](../button/README.md), [`led`](../led/README.md), [`display`](../display/README.md) — the MQTT partners
- [`docs/services/shared-lib/README.md`](../shared-lib/README.md) — MQTT base client, config helpers, logging
