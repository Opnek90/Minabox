# Backend Service – Architecture

## 1. Purpose & Responsibility

The backend service is the central orchestration and data hub of the Minabox.
It is the only component that owns the database, it translates between the
internal MQTT bus and the outward-facing REST/WebSocket interface of the WebUI,
and it holds every decision that spans more than one service — which card plays
what, when playback ends, whether a child is still allowed to listen.

Goals:

- Sole owner of the SQLite database (tag mappings, playlists, tracks, streams,
  podcasts, statistics).
- MQTT ↔ WebSocket bridge, so the WebUI sees hardware events in real time.
- REST API for synchronous queries and commands.
- Cross-service workflows: tag scan → content lookup → audio command.
- Configuration management on behalf of the button, LED, RFID, audio and
  display services.
- Media management: uploads, metadata and cover art, asynchronous URL import
  through the media-downloader service.
- Parental controls: allowed time windows, daily listening limit, blocked tags.
- Diagnosis: system alerts, temperature history, update check, debug export.

Out of scope: no direct hardware access (GPIO, I2C, SPI), no audio decoding or
playback (that is the audio service), no button debouncing or LED patterns, no
multi-tenancy — one box is one backend instance. Everything that must run with
host privileges (reboot, network, WiFi, USB, backup, OS update) is delegated to
the host-helper service; the backend only validates parameters and proxies.

Web authentication exists but is optional: without a configured password every
API path is open on the local network. See section 5.10.

---

## 2. File & Folder Structure

Relevant path: `services/backend-service/src/backend_service/`

```text
backend_service/
├── __init__.py                 # Package init, __version__
├── main.py                     # Runtime entry point: config, logging, signal handling
├── app_factory.py              # BackendService orchestration + FastAPI app factory
├── config.py                   # load_app_config(): env vars + general_settings.json + backend.json
├── config_manager.py           # Thin wrapper around shared_lib JsonConfigManager
├── config_schema.py            # Pydantic: EnvConfig, BackendServiceConfig, AppConfig
├── exceptions.py               # Backend exception hierarchy (MinaboxBackendError and friends)
├── api/
│   ├── __init__.py             # Mounts every sub-router under /api/v1
│   ├── routes_audio.py         # Playback control, sleep timer, session, audio-service proxy
│   ├── routes_auth.py          # Web login/logout, password, protected areas
│   ├── routes_config.py        # Read/write the other services' config files, general settings, logo
│   ├── routes_debug.py         # Debug export: build, preview, download, options
│   ├── routes_host.py          # Host-helper proxy (power, network, WiFi, USB, Bluetooth, backup, update)
│   ├── routes_playlists.py     # Playlist CRUD incl. cover art
│   ├── routes_podcast_folders.py # Podcast folder CRUD
│   ├── routes_podcasts.py      # Podcast CRUD, episode listing, cover art
│   ├── routes_rfid.py          # Learning mode on/off via MQTT
│   ├── routes_scan_history.py  # Tag scan history, list and clear
│   ├── routes_stats.py         # Listening statistics for the parent dashboard
│   ├── routes_stream_folders.py # Stream folder CRUD
│   ├── routes_streams.py       # Stream CRUD incl. cover art
│   ├── routes_system.py        # Service status, container logs, update check, health
│   ├── routes_tags.py          # RFID tag mapping CRUD
│   ├── routes_track_folders.py # Track folder CRUD
│   ├── routes_tracks.py        # Track CRUD, upload, URL import, cover art
│   └── websocket.py            # WebSocketManager: connections, greeting payload, broadcast
├── core/
│   ├── __init__.py             # Re-exports DatabaseManager, MQTTClient, SessionManager
│   ├── api_errors.py           # ApiError: HTTP error with a stable, translatable code
│   ├── auth.py                 # auth_settings.json, bcrypt hashing, JWT session token
│   ├── container_registry.py   # Container discovery, stats and name mapping via the Docker socket
│   ├── db_manager.py           # SQLite engine, sessions, PRAGMAs, schema version, migrations
│   ├── mqtt_client.py          # Handler registry, wildcard dispatch, publish contract
│   ├── mqtt_handlers.py        # Dispatcher that owns the shared playback state
│   ├── playback_settings.py    # playback_end_behavior and loop guard from general_settings.json
│   ├── playback_stats.py       # Listening minutes: today, total, live
│   ├── podcast_fetcher.py      # Background loop: fetch RSS feeds, insert new episodes
│   ├── resume_position.py      # Per-URI resume positions (save/get/clear)
│   ├── rfid_settings.py        # stop_playback_on_tag_remove, resume_on_tag_rescan
│   ├── session_manager.py      # In-memory playback session: queue, index, shuffle, repeat
│   ├── sleep_settings.py       # Sleep timer minutes and bedtime fade parameters
│   ├── system_alerts.py        # Active system alerts, keyed by code, most severe wins
│   ├── temperature_logger.py   # Background loop: sample temperature, retention, overheating alert
│   ├── update_check.py         # Compare running versions against the release manifest
│   ├── usage_limits.py         # Allowed time windows and daily listening limit
│   ├── handlers/
│   │   ├── audio_handler.py    # Audio status transitions, statistics accumulator, auto-advance
│   │   ├── button_handler.py   # Button actions, next/prev, repeat/shuffle, loop decision
│   │   ├── rfid_handler.py     # Tag scanned/removed/presence, content lookup, playback start
│   │   ├── timer_handler.py    # Sleep timer, bedtime fade, loop guard, fade-out-and-stop
│   │   └── utils.py            # Shared playback-event helpers
│   └── debug_export/           # Diagnostic archive — see docs/DebugExport.md
│       ├── __init__.py         # create_export(): the public entry point
│       ├── framework.py        # Collector registry, runner, ZIP builder, size budget
│       ├── redaction.py        # Scrubbing, pseudonymisation, secret tripwire
│       ├── logfilter.py        # Noise filtering and honest truncation for log files
│       ├── hostfiles.py        # Guarded read-only access to the mounted host filesystem
│       ├── runtime_buffers.py  # Bounded in-memory ring buffers for logs and MQTT traffic
│       ├── descriptions.py     # Plain-language description per archive file
│       └── collectors/         # system.py, services.py, data.py
├── infrastructure/
│   └── media_downloader_client.py # HTTP client for the media-downloader service, with retries
├── middleware/
│   └── auth.py                 # Session-cookie guard for protected API path prefixes
└── models/
    ├── __init__.py             # Re-exports the Pydantic schemas
    ├── database.py             # SQLAlchemy models
    ├── schemas.py              # Re-export hub for the domain schema modules
    ├── schemas_audio.py        # Audio commands and status
    ├── schemas_config.py       # Config shapes for the other services
    ├── schemas_content.py      # Tag, playlist, track, stream, podcast, folder schemas
    ├── schemas_enums.py        # ContentType, SourceType, AudioState, ServiceState, RFIDMode
    ├── schemas_error.py        # ErrorDetail, ErrorResponse
    ├── schemas_rfid.py         # Learning mode, scan event, mode response
    ├── schemas_system.py       # Health and system status
    └── schemas_ws.py           # WebSocketMessage envelope
```

Tests live in `services/backend-service/tests/` and cover the auto-advance
flags, the fade-out-and-stop path, the loop guard, the container registry, the
schema version, the temperature logger, the update check, the host proxy and
the debug export (contract, endpoint, log filter).

Connection handling, reconnect backoff, subscription replay and status replay
are **not** implemented here — they come from `shared_lib.mqtt.BaseMQTTClient`.
`core/mqtt_client.py` only adds the handler registry with wildcard matching and
the backend's own publish contract: unlike the device services, a failed
publish is raised as `MQTTPublishError` so an HTTP caller learns about it.

---

## 3. Public Interfaces

### 3.1 REST API

Base path `/api/v1`. Every response error carries a stable `code` — see
section 7.2.

**Tags**

| Method | Path | Purpose |
|---|---|---|
| GET | `/tags` | List all tag mappings |
| GET | `/tags/{tag_id}` | One mapping, by raw tag UID |
| POST | `/tags` | Create a mapping (learning mode) |
| PUT | `/tags/{tag_id}` | Update; explicit `null` clears the content assignment |
| DELETE | `/tags/{tag_id}` | Delete a mapping |

**Scan history**

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan-history/` | Scan events, newest first (`limit`, `offset`, `tag_id`) |
| DELETE | `/scan-history/` | Clear the history |

**Playlists**

| Method | Path | Purpose |
|---|---|---|
| GET | `/playlists` | List |
| GET | `/playlists/{id}` | Detail including ordered tracks |
| POST | `/playlists` | Create |
| PUT | `/playlists/{id}` | Update, optionally replacing the track list |
| DELETE | `/playlists/{id}` | Delete |
| POST / DELETE | `/playlists/{id}/cover` | Upload or remove cover art |

**Tracks**

| Method | Path | Purpose |
|---|---|---|
| GET | `/tracks` | List, optionally filtered by `folder_id` (`0` = root) |
| GET | `/tracks/{id}` | Detail |
| POST | `/tracks` | Create a record (JSON) |
| POST | `/tracks/upload` | Upload an audio file (multipart) |
| GET | `/tracks/validate-url` | Read metadata for a URL without importing |
| POST | `/tracks/from-url` | Start an asynchronous import → **HTTP 202** |
| GET | `/tracks/{id}/download-status` | Progress of an import started above |
| PUT | `/tracks/{id}` | Update metadata or folder |
| DELETE | `/tracks/{id}` | Delete record, file and cover art |
| POST / DELETE | `/tracks/{id}/cover` | Upload or remove cover art |

**Streams and podcasts** follow the same shape:
`/streams`, `/streams/{id}`, `/streams/{id}/cover`, and `/podcasts`,
`/podcasts/{id}`, `/podcasts/{id}/episodes`, `/podcasts/{id}/cover`.

**Folders** — one identical router per media type:
`/tracks/folders`, `/streams/folders`, `/podcasts/folders`, each with
`GET`, `GET /{id}`, `POST`, `PUT /{id}`, `DELETE /{id}`. Deleting a folder
moves its contents and its child folders to the root rather than deleting them.

> The folder routers are mounted **before** the plain media routers on purpose.
> Without that ordering FastAPI would match `/tracks/folders` against
> `/tracks/{track_id}` with `track_id="folders"`.

**Audio control**

| Method | Path | Purpose |
|---|---|---|
| GET | `/audio/status` | Last known status from the in-memory cache |
| POST | `/audio/play` | Start playback (`track_id`, `playlist_id`, `stream_id`, `podcast_id`, or empty to resume) |
| POST | `/audio/pause` / `/audio/stop` | Pause or stop |
| POST | `/audio/next` / `/audio/prev` | Queue navigation |
| POST | `/audio/seek` | Seek within the current track (`position_ms`); 409 for live streams |
| POST | `/audio/volume` | Set volume |
| GET / POST / DELETE | `/audio/sleep-timer` | Status, start, cancel |
| GET | `/audio/session` | Current queue, repeat mode and shuffle state |
| POST | `/audio/repeat` | Set repeat mode (`none` \| `all`) |
| POST | `/audio/shuffle` | Set shuffle for the current session |
| GET | `/audio/devices` | Detected output sinks (proxied to the audio service) |
| POST | `/audio/switch-device` | Switch output sink or cycle with `direction: "next"` |
| POST | `/audio/test-tone` | Play a short test tone (setup wizard) |

**RFID**

| Method | Path | Purpose |
|---|---|---|
| POST | `/rfid/learning-mode` | Enable or disable learning mode |

**Configuration**

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/config/general` | Device id, log level, MQTT, timers, parental controls, setup state |
| GET / PUT | `/config/audio` | Audio service config (PUT merges with the existing file) |
| GET / PUT | `/config/leds` | LED service config |
| GET / PUT | `/config/buttons` | Button service config |
| GET / PUT | `/config/rfid` | RFID service config (flat API shape, nested on disk) |
| GET / PUT | `/config/display` | Display service config |
| GET | `/config/leds/states`, `/config/leds/patterns` | Enumerations for the admin UI |
| GET | `/config/buttons/actions` | Enumerations for the admin UI |
| POST | `/config/leds/test`, `/config/display/test` | Trigger a hardware self-test |
| POST / DELETE | `/config/logo` | Upload or remove the custom logo |

**Statistics**

| Method | Path | Purpose |
|---|---|---|
| GET | `/stats/overview` | Minutes today and total, daily limit, media counts |
| GET | `/stats/usage-today` | Minutes today and the daily limit |
| GET | `/stats/listening-summary` | Minutes per day, top tags, top playlists, heatmap |
| POST | `/stats/reset` | Delete all playback events |

`minutes_today` in `/overview` and `/usage-today` includes completed events
**and** the running total of the open event (flushed roughly every 60 s), so
the dashboard does not sit at 0 during playback. The two sources are mutually
exclusive, so nothing is counted twice. The daily-limit *enforcement* in
`usage_limits.py` deliberately uses completed events only, so active playback
is not cut off a minute early.

**System and diagnosis**

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` (root, outside `/api/v1`) | Liveness for the container health check |
| GET | `/system/health` | Health with DB and MQTT state |
| GET | `/system/status` | One entry per container: state, version, CPU, RAM, database schema state |
| GET | `/system/logs?service=&tail=` | Container logs (host-helper, then Docker, then file) |
| GET | `/system/update-check?force=` | Running versions against the release manifest |
| GET | `/system/alerts` | All active system alerts, most severe first |
| GET | `/system/temperature-history?hours=` | Temperature time series from the database |
| POST / GET | `/system/debug-export`, `/system/debug-export/preview`, `/system/debug-export/download/{id}`, `/system/debug-export/options` | Diagnostic archive |

**Host operations** — all proxied to the host-helper:

- Power and lifecycle: `POST /system/reboot`, `/system/shutdown`, `/system/restart`
- Storage: `GET`/`PUT /system/audio-path`, `POST /system/move-audio`, `GET /system/move-status`
- System: `PUT /system/timezone`, `GET`/`PUT /system/hostname`, `GET`/`PUT /system/board-leds`,
  `GET`/`PUT /system/network`, `POST /system/password`, `GET /system/ssh-status`,
  `POST /system/ssh-toggle`, `POST /system/docker-prune`, `POST /system/factory-reset`
- Update: `POST /system/update-minabox`, `GET /system/update-minabox/status`,
  `POST /system/update-os`, `GET /system/update-os/log`, `GET /system/version`
- Time: `GET /system/time-status`
- Logs: `GET /system/syslog?n=&source=kernel|docker`
- WiFi: `GET /system/wifi/scan`, `POST /system/wifi/connect`,
  `POST /system/wifi/hotspot/start`, `/stop`, `GET /system/wifi/hotspot/status`
- USB: `GET /system/usb/devices`, `GET /system/usb/{id}/files`,
  `POST /system/usb/import`, `POST /system/usb/eject`
- Bluetooth: `GET /system/bluetooth/scan`, `/paired`, `POST /system/bluetooth/pair`,
  `/connect`, `/disconnect`, `/remove`
- Backup: `GET /system/backup/download`, `POST /system/backup/restore`

Two rules shape the proxy layer in `routes_host.py`:

- `_proxy()` is strict — a failure reaches the caller. `_proxy_optional()` is
  soft: it returns a neutral fallback whenever anything goes wrong, so a status
  widget cannot break the settings page just because the host-helper is
  restarting.
- A 401 from the host-helper is reported as **503**, not 401. The WebUI treats
  401 as "your session expired" and would log the user out over what is really
  a server-side misconfiguration.

All host calls share one pooled `httpx.AsyncClient`; creating a client per
request meant a fresh TCP handshake for every button press in the WebUI.

**Static files**: `/static` serves `STATIC_DIR` (default `/data/static`) —
the custom logo and all cover art.

### 3.2 WebSocket

Endpoint `/ws`. The backend pushes; incoming text is only parsed as JSON and
acknowledged with `{"type": "ack"}` — there are no WebSocket commands. A newly
connected client immediately receives the last enriched `audio_status` payload
so the player page renders without waiting for the next broadcast.

Every message is `{"type": ..., "data": {...}, "timestamp": ...}`.

| `type` | Sent when |
|---|---|
| `audio_status` | Audio service reported a status; enriched with title, artist, album, cover URL and queue position |
| `rfid_scanned` | A known tag started playback |
| `rfid_scanned_learning` | A tag was scanned in learning mode (`already_assigned`) |
| `tag_not_found` | Scanned tag has no mapping |
| `tag_blocked` | Scanned tag is disabled |
| `usage_denied` | Outside the allowed time window, or daily limit reached |
| `button_action` | A mapped button action was processed |
| `button_raw_event` | Any physical button press (drives the WebUI hardware test mode) |
| `repeat_mode` / `shuffle_mode` | Mode changed, at the player or through a new session |
| `sleep_timer_status` | Sleep timer started, fired or was cancelled |
| `audio_config` | Audio config was written — an open player picks up new volume limits without a reload |
| `system_alert` / `system_alert_cleared` | An alert was raised or withdrawn (overheating, update available, database too new) |

### 3.3 MQTT

Topic scheme `minabox/<device-id>/<domain>/<action>`, built centrally by
`AppConfig.get_mqtt_topic()`. All publishes use QoS 1.

**Subscribed**

| Topic | Handler |
|---|---|
| `rfid/tag-scanned` | Look up the mapping and start playback |
| `rfid/tag-scanned-learning` | Report the UID and whether it is already assigned |
| `rfid/tag-removed` | Stop playback when the setting says so |
| `rfid/presence` | Retained; tracks whether a card lies on the reader |
| `audio/status` | Statistics, auto-advance, stream reconnect, WebSocket broadcast |
| `audio/position-report` | Persist the resume position |
| `button/+` | Every mapped button action |
| `button/raw-event` | Every physical press, mapped or not |

`rfid/presence` is retained by the RFID service, so a reconnecting backend
learns the current card state immediately. That is what makes the
"repeat while the card lies there" mode work after a restart.

**Published**

| Topic | Payload |
|---|---|
| `audio/play` | `track_id`, `source_type`, `source_uri`, `start_position_ms` |
| `audio/pause`, `audio/stop` | `{}` |
| `audio/set-volume` | `volume` |
| `audio/mute-toggle` | `{}` |
| `audio/switch-device` | `sink_name` or `direction` |
| `rfid/cmd/set-mode` | `mode: "learning" \| "normal"` |
| `rfid/unknown-tag`, `rfid/tag-blocked` | `tag_id`, optional `name` |
| `led/usage-denied` | `event`, `timestamp` |
| `<service>/config/reload` | `{}` for audio, led, button, display |
| `config/general` | Retained; currently `log_level` |
| `system/service-error`, `system/service-started` | Overheating raised and cleared |

---

## 4. Data Model

SQLite through SQLAlchemy, at `DATABASE_PATH` (default `/data/minabox.db`).
The connection sets `foreign_keys=ON`, `journal_mode=WAL`,
`synchronous=NORMAL` and `temp_store=MEMORY` — WAL is what lets a read run
while a write is in flight, which matters because the same process serves the
API and the MQTT loop.

| Table | Purpose |
|---|---|
| `tags` | Tag UID → content mapping; `disabled` blocks a card, `content_*` may be `NULL` for unassigned cards |
| `tag_scan_events` | One row per scan attempt: `play`, `blocked` or `unassigned` |
| `tracks` | Local files and imported media; `source_uri` is the absolute path |
| `track_folders` | Self-referencing folder tree for tracks |
| `playlists` / `playlist_tracks` | Playlists and their ordered members (unique per position) |
| `streams` / `stream_folders` | Web radio; not part of playlists |
| `podcasts` / `podcast_episodes` / `podcast_folders` | Feeds and their episodes (unique per feed and URI) |
| `playback_events` | One playback session for statistics; `listened_ms` is the measured listening time |
| `track_resume_positions` | Resume position per `source_uri` |
| `temperature_readings` | Temperature samples, retained for 30 days |

Cover art is not stored in the database — only its URL. The files live under
`STATIC_DIR/covers/` as `track_{id}`, `playlist_{id}`, `stream_{id}` or
`podcast_{id}`.

### 4.1 Schema version and migrations

The database survives every update — only the containers are replaced. New code
therefore meets old data, and a rollback means old code meets new data.

`SCHEMA_VERSION` in `core/db_manager.py` makes that difference visible. It is
stored in SQLite's own `PRAGMA user_version`, so it needs no table of its own
and a database predating the counter reads as `0`. The number is raised only
when a change stops being backwards compatible — when rows move, columns
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

---

## 5. Core Functions

### 5.1 Tag scan → playback

1. `rfid/tag-scanned` arrives with a `tag_id`.
2. Two guards suppress repeats: a five second per-tag cooldown, and a check
   that ignores a rescan of the tag that is already playing within 15 seconds.
   Without them a card resting on the reader restarts itself.
3. Look up the tag. Unknown → publish `rfid/unknown-tag`, broadcast
   `tag_not_found`, record the scan as `unassigned`, stop.
4. Disabled → publish `rfid/tag-blocked`, broadcast `tag_blocked`, record the
   scan as `blocked`, stop.
5. Check the parental controls (section 5.5). Denied → publish
   `led/usage-denied`, broadcast `usage_denied`, stop.
6. Record the scan as `play`, update `last_scanned_at`, and dispatch on
   `content_type`:
   - **playlist** — load the members in order, create a session (shuffled),
     open a playback event, publish `audio/play` for the first track;
   - **track** — create a single-track session, open a playback event, resolve
     the resume position and publish `audio/play`;
   - **stream** — open a playback event and publish `audio/play` with
     `track_id="stream-<id>"`;
   - **podcast** — pick the newest episode, open a playback event, resolve the
     resume position and publish `audio/play` with `track_id="podcast-<id>"`.
7. Broadcast the resulting `repeat_mode` and `rfid_scanned` to the WebUI.

### 5.2 Learning mode

The WebUI enables it with `POST /rfid/learning-mode`, which publishes
`rfid/cmd/set-mode`. The RFID service then reports scans on
`rfid/tag-scanned-learning` instead. The backend only checks whether the UID is
already mapped and broadcasts `rfid_scanned_learning`; the WebUI asks the user
what to assign and posts the mapping to `POST /tags`.

### 5.3 End of content, repeat and the loop guard

When the last track runs out, the audio service reports `stopped` and
`AudioHandler` calls `ButtonHandler._handle_next()` — unless the stop was
deliberate.

The `deliberate_stop` flag is consumed once on **every** stop transition. Every
deliberate stop also clears `playback_intent_active`, and while only the
`deliberate_stop` branch reset the flag it stayed set and swallowed the next
natural end of track.

With no next track, `_loop_decision()` reads `playback_end_behavior` from
`general_settings.json`:

| Value | Behaviour |
|---|---|
| `stop` (default) | Send `stop` to the audio service |
| `repeat` | Reset the session to the first track and play again |
| `repeat_while_tag` | Like `repeat`, but only while `rfid/presence` reports a card |

The first repetition starts `TimerHandler.start_loop_guard()` with
`playback_loop_guard_minutes` (`0` disables it). When it expires,
`fade_out_and_stop()` fades the volume down and stops, so a card left on the
reader cannot keep the box playing for hours. It is deliberately a timer rather
than a check at the track boundary: a long audiobook on repeat would otherwise
overshoot the limit by its own length. `_loop_decision()` checks the same limit
again at the track boundary as a backstop. `mark_deliberate_stop()` cancels the
guard, and the guard verifies on firing that the same session is still running
and that repeat is still on.

### 5.4 Fade out and stop

`fade_out_and_stop()` is the single path for every case where the box stops on
its own — sleep timer, daily limit, loop guard. With the bedtime fade switched
off it is a plain stop. Two details matter:

- The fade aborts as soon as `playback_intent_active` is gone. The content can
  run out mid-fade, and without the abort the fade would keep turning the
  volume down long after playback ended.
- The volume before the fade is restored afterwards. Otherwise the box stays
  mute after every sleep timer and looks broken the next morning.

### 5.5 Parental controls

Three independent mechanisms, all read fresh from `general_settings.json` on
every access so a change in the WebUI takes effect without a restart:

- **Blocked tags** — `tags.disabled`; checked on every scan.
- **Allowed time windows** — `usage_times_enabled` plus `allowed_usage_times`
  (weekday, start, end). A window that wraps past midnight is handled.
- **Daily limit** — `daily_limit_enabled` and `daily_limit_minutes`, compared
  against today's completed listening minutes in the host's local timezone.
  Enforced when a tag is scanned, when the REST API starts playback, and at
  every track boundary; the last of these fades out instead of cutting off.

### 5.6 Resume positions

The audio service reports `audio/position-report` on stop and pause. The
backend stores the position keyed by `source_uri` — the only identifier the two
services share. Positions below 5 s are not stored (the user barely started),
and a track with less than 10 s remaining clears its entry instead so the next
play starts from the beginning. Streams are ignored: they have no meaningful
position. On the next scan the position is applied only when
`resume_on_tag_rescan` is on (default: on).

### 5.7 Playback statistics

`AudioHandler` keeps an in-memory accumulator of actual playing time and
flushes it into `playback_events.listened_ms` every 60 s, so a crash loses at
most a minute and the dashboard can show a running total. The wall-clock
fallback (`ended_at - started_at`) was removed: after a power loss it counted
the downtime as listening time. Each event is capped at 120 minutes so a single
runaway event cannot dominate the totals.

### 5.8 Media import

**Upload** — `POST /tracks/upload` creates the record first, then writes the
file to `AUDIO_STORAGE_PATH/{track_id}/original<ext>` and reads its tags. Both
steps run in a worker thread via `asyncio.to_thread`: writing a large audiobook
to the SD card takes seconds, and on the event loop that would freeze every
other request including the player WebSocket. Embedded cover art is extracted
to `STATIC_DIR/covers/`.

**URL import** — `POST /tracks/from-url` returns HTTP 202 immediately:

1. Strip playlist parameters from the URL, then check the host against
   `_ALLOWED_DOMAINS`. The allow-list is a technical guard against arbitrary
   fetch targets; it says nothing about whether the caller holds the rights to
   the content.
2. If a track with the same `source_uri` exists, return HTTP 200 with its id.
3. Create a placeholder record and its directory, mark the status `pending`,
   and start a background task.
4. The task calls the media-downloader (three attempts, linear backoff), writes
   the real metadata, and resolves cover art — embedded art first, the remote
   thumbnail as fallback. On failure it deletes the placeholder record and the
   directory again.

`GET /tracks/{id}/download-status` reports `pending`, `downloading`, `done`,
`error` or `unknown`. The status lives in a module-level dict, so a restart
loses in-flight entries and the endpoint answers `unknown`. That route is
registered **before** the generic `GET /{track_id}`, because FastAPI matches
routes in order.

`GET /tracks/validate-url` reads publicly available metadata for a URL without
importing anything — it drives the preview dialog.

### 5.9 Configuration management

The backend owns two kinds of configuration on behalf of others.

**General settings** live in `/data/general_settings.json` and are read fresh
on every access. `PUT /config/general` filters the body against an allow-list,
clamps every value, and merges with the file on disk so a partial update from
one tab does not drop the keys another tab owns. Changing `log_level` takes
effect in this process immediately and is published retained on
`config/general` so the other services follow.

**Service configs** are the other services' own JSON files, mounted under
`CONFIG_SERVICES_PATH`. `GET` returns the file, `PUT` writes it and publishes
`<service>/config/reload`. Audio is merged rather than replaced, so a partial
update from the parent dashboard (say, only `max_volume`) does not wipe
`enabled_output_devices`. RFID is flattened on read and re-nested on write,
because the admin UI works with a flat shape while the service expects
`{ "reader": { ... } }`.

`config/backend.json` holds `session_timeout_min`, `health_check_interval_sec`
and `max_upload_size_mb`. None of them is read anywhere today; the effective
configuration comes from environment variables.

### 5.10 Web authentication

Optional and off by default. `POST /auth/password` sets a bcrypt hash in
`/data/auth_settings.json`; `POST /auth/login` verifies it and sets an HttpOnly
session cookie holding an HS256 JWT valid for 24 hours. The signing secret is
`WEB_AUTH_SECRET`, falling back to `HOST_HELPER_API_KEY`; both are generated by
`install.sh`.

`middleware/auth.py` guards path prefixes, not individual routes. Three areas
can be protected independently:

| Area | Prefixes |
|---|---|
| `admin` | `/api/v1/config`, `/api/v1/system` |
| `media` | `/api/v1/playlists`, `/tracks`, `/streams`, `/podcasts` |
| `dashboard` | `/api/v1/stats` |

Everything outside those prefixes — `/api/v1/audio`, `/api/v1/tags`,
`/api/v1/rfid`, `/api/v1/scan-history`, `/ws`, `/static` — is reachable without
a session. So is `/api/v1/auth/*`, and so is the debug export: it is the one
thing a user still needs when the password itself is the problem, and it
enforces its own private-network check, rate limit and privacy tier instead.

### 5.11 Container discovery, status and update check

`core/container_registry.py` asks the read-only Docker socket which containers
exist. That is the only source that covers *every* container uniformly —
Mosquitto and the nginx-based WebUI speak no MQTT and expose no Minabox health
schema, but Docker knows their state, labels and resource usage. It also
answers when a service hangs, and it reflects what is actually installed: which
containers exist depends on `COMPOSE_PROFILES`, so a box without the LED
profile shows no LED entry instead of a permanent "offline".

Two Compose labels separate a real service from a stray `docker run`, and a
`memory_mb` of `null` means "not measurable here" rather than "uses no memory":
Raspberry Pi OS ships with the memory cgroup controller disabled, and then no
per-container figure exists at all. `/system/status` exposes that as
`memory_stats_available` so the UI can omit the bar instead of drawing an empty
one that looks like a reading.

Without a usable socket, `routes_system.py` falls back to probing each known
service's `/health` — no CPU or RAM then, and only the services in the static
catalogue.

On **both** paths the service's own verdict is folded in. Five services —
`audio`, `rfid`, `button`, `display`, `led` — answer `/health` with a `status`
of their own, and it used to be read by nobody. The container health check asks
only whether the endpoint answers with 2xx, and a degraded service answers 2xx
on purpose, so that a lost broker does not make Docker restart something that
is otherwise fine. A service could therefore report itself as broken and be
shown green: the LED service with not a single usable GPIO pin after a wrong
`GPIO_GID`, or any service whose MQTT connection had gone while the container
kept running.

An entry that reports `degraded` carries `service_status: "degraded"` and its
`state` becomes `degraded` — the fourth state next to `online`, `offline` and
`error`. `error` wins over it: an unhealthy container is the worse news, and a
service that still answers must not talk the entry back up into a milder state.

Only entries that are **online** are probed, and all of them together: a
container already known to be down has nothing to add and would only spend
`HEALTH_TIMEOUT` saying so, and the round costs one timeout rather than one per
service.

`core/update_check.py` compares the running versions against
`release-manifest.json` in the repository. Two rules shape it:

- **No network never means "update available".** If the fetch fails, the last
  known state is shown together with the error — never an update nobody could
  verify.
- **Only offer what can be pulled.** The manifest is published with the commit,
  the images only when CI finishes. In that window the manifest knows a version
  the registry does not have yet, so every candidate is checked against the
  registry before it is offered.

Results are cached for six hours. The background loop polls every 30 minutes,
but only while the user has the automatic check switched on.

### 5.12 Diagnosis

`system_alerts.py` holds active alerts keyed by code and shows the most severe
one, so a temporary temperature warning cannot displace the permanent notice
about an incompatible database.

`temperature_logger.py` samples the host temperature every five minutes through
the host-helper, stores it, deletes samples older than 30 days, and raises or
clears the overheating alert at `temperature_warning_celsius` (default 80).
The interval sleep runs after every iteration including the failed ones, so an
absent host-helper cannot turn the loop into a busy loop.

The **debug export** builds a diagnosable snapshot of the box into one ZIP.
Collectors are selected by name from a registry — nothing from the request ever
becomes a path or a command — each runs isolated with a timeout, and its
outcome lands in the manifest as ok, failed or skipped, because "display logs
unavailable" is itself a diagnosis. Every file passes redaction, and the
finished payload is checked against the device's real secrets before it is
written. See [docs/DebugExport.md](../../DebugExport.md).

Two bounded in-memory ring buffers feed it with things that are gone by the
time anyone looks: the last 300 warnings and errors, and the last 500 MQTT
messages. Container logs rotate and MQTT traffic is not persisted at all, yet
"the button press never reached the backend" is only answerable if the last few
hundred messages are still around.

### 5.13 Startup and shutdown

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

---

## 6. Dependencies

**Services**

| Service | Relationship |
|---|---|
| MQTT broker (Mosquitto) | Bus for every internal event |
| RFID service | Tag events, presence, learning mode |
| Audio service | Playback commands and status; also an HTTP proxy target for devices and the test tone |
| Button service | Action and raw hardware events |
| LED / display services | Receive config reloads and self-test triggers |
| WebUI service | The REST and WebSocket client |
| Media-downloader service | URL import |
| Host-helper service | Everything requiring host privileges |

**Infrastructure**

- SQLite at `/data/minabox.db`
- Audio files under `/mnt/audio/tracks/` (configurable, movable at runtime)
- Static files under `/data/static/` (logo, cover art)
- Docker socket, mounted read-only, for container discovery and stats
- Read-only host mounts under `/host` for the debug export

**Python**

`fastapi` and `uvicorn` (REST, WebSocket, ASGI), `sqlalchemy` and `alembic`
(database), `aiomqtt` (MQTT), `pydantic` (validation), `structlog` (logging),
`httpx` (async HTTP), `mutagen` (audio metadata and cover art), `feedparser`
(podcast RSS), `docker` (container discovery), `bcrypt` and `python-jose`
(web authentication), `python-multipart` (uploads). `minabox-shared` provides
the MQTT base client, the logging setup and the config helpers.

**Environment**

| Variable | Meaning |
|---|---|
| `MINABOX_DEVICE_ID` | Box id, forms the MQTT topic prefix |
| `MQTT_BROKER`, `MQTT_PORT` | Broker connection |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `API_PORT` | REST port (default 8080) |
| `DATABASE_PATH` | Default `/data/minabox.db` |
| `DATA_PATH` | Default `/data`; holds the settings and state files |
| `AUDIO_STORAGE_PATH` | Default `/mnt/audio/tracks` |
| `STATIC_DIR` | Default `/data/static` |
| `CONFIG_SERVICES_PATH` | Mount point of the other services' config files |
| `HOST_HELPER_URL`, `HOST_HELPER_API_KEY` | Host-helper connection; without the key every host route answers 503 |
| `WEB_AUTH_SECRET` | JWT signing secret; falls back to `HOST_HELPER_API_KEY` |
| `MEDIA_DOWNLOADER_URL` | Default `http://media-downloader:8007` |
| `ALLOWED_AUDIO_PATHS` | Base paths a media directory may be moved to |
| `HOST_DIAG_ROOT` | Default `/host`; root of the read-only host mounts |
| `CORS_ALLOWED_ORIGINS` | Allowed origins; `['*']` for local development only |
| `MINABOX_MANIFEST_URL` | Override for the release manifest URL |

**Persistent files under `DATA_PATH`**

`general_settings.json` (user settings), `auth_settings.json` (password hash
and protected areas), `update-check.json` (cached update result),
`tmp/debug-export-*.zip` (one-slot preview cache, mode 0600).

---

## 7. Errors & Status

### 7.1 Health states

`GET /health` (the container health check) reports:

| Status | Condition |
|---|---|
| `healthy` | Database up and MQTT connected |
| `degraded` | Database up, MQTT not connected — the API is usable, MQTT may still be catching up |
| `unhealthy` | No database |

`GET /api/v1/system/health` is stricter: it additionally reports `unhealthy`
when the database schema is newer than this code expects. The connection is
fine there, but the data may not be where this version looks for it.

### 7.2 REST error format

Every error raised through `ApiError` returns:

```json
{
  "detail": "Track 42 not found",
  "code": "track_not_found"
}
```

`detail` is English, developer-facing text meant for logs, `curl` and issue
reports. `code` is what the WebUI actually shows the user, translated through
the `errors` i18n namespace with `generic_error` as the fallback for unknown
codes. A typo in `detail` is therefore harmless for the display; a typo in
`code` merely falls back to the generic text instead of showing the wrong
language or raw JSON. Some errors add fields — a rate-limited debug export also
returns `retry_after`.

Status codes in use: `200`, `201` (created), `202` (import started), `204` (no
content), `400`, `401` (no valid session), `403` (daily limit, non-private
client), `404`, `409` (nothing to seek, move already running), `422`,
`429` (export rate limited or already running), `500`, `502` (upstream service
error), `503` (dependency unavailable), `504` (export timed out).

### 7.3 Logging

Structured through structlog, JSON in production. Noteworthy events:

- Playback: `tag_found`, `track_playback_started`, `playlist_playback_started`,
  `session_created`, `session_looping`, `session_end`, `loop_guard_fired`,
  `faded_out_and_stopped`, `playback_stats_flushed`
- Suppressed and denied: `rfid_tag_scan_ignored_cooldown`, `tag_blocked`,
  `tag_scanned_outside_allowed_time`, `tag_scanned_daily_limit_exceeded`
- Import: `api_create_track_from_url_accepted`, `download_task_completed`,
  `download_task_failed`, `media_downloader_download_5xx_retry`
- Database: `db_schema_migrated`, `db_schema_newer_than_code`,
  `db_streams_migrated`, `startup_cleanup_closed_orphaned_events`
- System: `system_alert_set`, `system_alert_cleared`,
  `temperature_overheating_published`, `update_not_published_yet`
- Diagnosis: `debug_export_created` (with client address and privacy tier),
  `debug_export_secret_blocked`, `debug_export_collector_timeout`

Warnings and errors are additionally kept in the in-memory ring buffer so the
debug export still contains them after the container logs have rotated.
`sqlalchemy.engine` and `alembic.runtime.migration` are silenced; the
`log_level` set in the WebUI is applied to the running process without a
restart.
