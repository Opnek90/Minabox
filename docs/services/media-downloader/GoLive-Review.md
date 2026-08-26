# Media Downloader Service – Go-Live Review

Line-by-line review of `services/media-downloader-service/` ahead of going
live: all 5 Python files (325 lines total), the Dockerfile, `pyproject.toml`,
`requirements.txt`, `README.md`, the compose block, and the parts of
`backend-service` this service is coupled to
(`media_downloader_client.py`, `routes_tracks.py`).

**Starting position:** the service worked. Nothing below was a fix for
something visibly broken on the box at the time; it was the list of things
more likely to bite once real, unpredictable URLs and concurrent usage hit
it.

Legend: `[ ]` open · `[x]` done · **[H]** high · **[M]** medium · **[N]** low

---

## Summary

Two items would have concretely hurt a user during normal operation:

- **1.1** — both endpoints blocked the single event loop for the full
  duration of a download (typically tens of seconds, easily minutes for a
  long track on a Pi). While that ran, the container could not answer its own
  Docker health check, and three consecutive misses (90 s) would mark it
  unhealthy and restart it mid-download. The same bug class the team already
  found and fixed in `host-helper` (42 blocking handlers) and the backend's
  upload endpoint — just not caught here.
- **1.2** — a source with no known duration (a livestream, or any extractor
  that returns `duration: None`) crashed the request with an unhandled
  `TypeError` instead of a clean `422`.

Everything else was either a smaller correctness point, dead configuration
that gave a false sense of a safety net that was not actually there, or an
image-size opportunity. Nothing here found a defect in yt-dlp usage itself,
the retry logic, or the domain-check *mechanism* — those were sound; the
allow-list's *default contents* turned out to be a separate, product-level
question (see 2.1).

**One thing changed scope after the initial pass:** while wiring up the
domain allow-list (2.1), the follow-up decision was to make it user-editable
in the WebUI rather than a second static list on this container — and, given
the review was already touching it, to remove YouTube from the shipped
default. That is a bigger, separate change described in full under 2.1.

---

## Result

Everything in sections 1–4 is done except 2.3 (deferred, fleet-wide) and the
424 MB `ffmpeg` layer (deliberately not pursued — see below).

| | Before | After |
| --- | --- | --- |
| ruff findings | 4 | **0** |
| Tests | 0 | **27** |
| German comments (source + config) | 3 lines | **0** |
| Dead/ignored config fields | 5 (`DOWNLOAD_PATH`, `ALLOWED_DOMAINS`, `MAX_FILESIZE_MB`, `SERVICE_PORT`, `LOG_LEVEL`) | **0** |
| `docker inspect` image size | 238.4 MB | **212.5 MB** |

(The image-size tools in this environment disagreed with each other in
absolute terms — see the note in section 4 — so the number above is a
same-tool, same-method before/after on the same build, not a claim about the
size on the actual published registry image.)

Verified, not just read:

- A locally built image starts, answers `/health` as JSON (`LOG_LEVEL`
  unset → INFO → JSON renderer, confirmed in the container logs), and
  rejects an `output_dir` outside `/mnt/audio` with `422` end-to-end through
  the real HTTP path.
- `docker run --rm <image> id minabox` and a directory listing confirm
  `/app/deps`, `/app/src` and the downloads directory are owned by `minabox`,
  not root, after the `COPY --chown` change (4.1).
- All installed Python packages resolve to prebuilt wheels
  (`py3-none-any` or `manylinux`/`cp313` `aarch64`) — confirmed against the
  built image, not assumed (4.2).
- The full backend and media-downloader test suites pass together
  (`pytest -q`), so the domain-check rewrite in `routes_tracks.py` did not
  regress anything already covered.

---

## 1. Functional defects

### [x] [H] 1.1 Both endpoints block the event loop for the whole download

`main.py`:

```python
@app.post("/download", ...)
async def download_video(request: DownloadRequest) -> DownloadResponse:
    ...
    result = downloader.download_video(request.url, output_dir)   # blocking, no await
```

```python
@app.get("/info", ...)
async def get_video_info(...) -> VideoInfoResponse:
    ...
    info = downloader.get_video_info(url)   # blocking, no await
```

Both handlers were declared `async def` but called a synchronous method that
does network I/O, spawns `ffmpeg`, and writes to disk — directly, with no
`await asyncio.to_thread(...)`. Because the coroutine ran to completion on
the single event loop, nothing else the service does — including
`GET /health` — could be served until it returned.

**Consequence on this hardware specifically:** the Dockerfile's health check
is `interval: 30s, timeout: 10s, retries: 3`. Three misses in a row (90 s of
an unresponsive event loop) would mark the container unhealthy, and
`docker-compose.yml`'s `restart: unless-stopped` would eventually cycle it
mid-download.

**Done.** Both handlers now do
`await asyncio.to_thread(downloader.download_video, request.url, output_dir)`
(and the equivalent for `get_video_info`), the identical fix already applied
to `host-helper` and the backend's `upload_track`.

Alongside it, an `asyncio.Semaphore(1)` now serializes actual downloads: once
the event loop is free during a download, concurrent `/download` requests
become possible, and two `ffmpeg` conversions at once on a Pi's limited cores
would fight each other rather than genuinely run in parallel. `/info` is not
gated by the semaphore — it does not touch `ffmpeg`.

Verified with a locally built image: `/health` answers correctly and the
`/download` happy path (mocked downloader) returns `201` through the real
`asyncio.to_thread` dispatch (`tests/test_main.py`).

---

### [x] [H] 1.2 A source with no known duration crashes the request

`downloader.py`, both `download_video()` and `get_video_info()`:

```python
"duration_ms": int(info.get("duration", 0) * 1000),
```

`dict.get(key, default)` only returns the default when the key is **absent**.
Several yt-dlp extractors set `duration` to `None` explicitly — livestreams
and some non-YouTube sources are the common case — and this line then
computed `None * 1000`, raising an unhandled `TypeError` that FastAPI turned
into a bare `500` with none of the `DOWNLOAD_FAILED`/`INFO_FAILED` envelope
every other failure path produces.

**Done.** `info.get("duration") or 0` in both places. Regression-tested in
`tests/test_downloader.py` with a fake `yt_dlp.YoutubeDL` returning
`duration: None`.

---

### [x] [N] 1.3 A comment describes the opposite of what the code does

`downloader.py`:

```python
# Best-quality thumbnail URL from yt-dlp: prefer the first entry in
# info["thumbnails"] (sorted best-first by yt-dlp) or fall back to
# the top-level "thumbnail" field.
...
thumbnail_url = thumbnails[-1].get("url", "") or ""
```

The comment said the list is sorted best-first and to take the first entry.
The code takes `thumbnails[-1]` — the **last** entry, which is actually
correct: yt-dlp sorts `info["thumbnails"]` ascending by preference (worst
first, best last).

**Done.** Comment corrected to describe the real (correct) ordering.
`tests/test_downloader.py` pins both the "best of several" and the
"fall back to top-level `thumbnail`" cases.

---

### [x] [N] 1.4 `output_dir` reached the filesystem with no validation

`models.py`'s `output_dir` had no path validation; `downloader.py` used it
both for `mkdir(parents=True, exist_ok=True)` and as the yt-dlp `outtmpl`
base. Since this service's port has no authentication, anything able to
reach it directly could point a download at any path the container user can
write to.

**Done.** `config.py` gained `audio_base_dir` (default `/mnt/audio`, the
shared volume mount point); `main.py`'s new `_resolve_output_dir()` resolves
the caller-supplied (or default) path and rejects anything outside it with a
`422` before a `MediaDownloader` is even constructed. Verified against a
running container: `output_dir: "/etc/evil"` is rejected with
`"output_dir must be inside /mnt/audio"`; a path under the configured base
still reaches the downloader (`tests/test_main.py`).

---

## 2. Robustness & configuration

### [x] [H] 2.1 Three environment variables were set on this container and read by nobody

`docker-compose.yml` set `DOWNLOAD_PATH`, `MAX_FILESIZE_MB` and
`ALLOWED_DOMAINS` on the `media-downloader` service; `config.py` had no field
for any of the three.

**Done, but the domain piece grew into something bigger than "wire it up."**

- **`MAX_FILESIZE_MB`** — now a real `config.py` field, wired into `yt-dlp`'s
  own `max_filesize` option (bytes) in `download_video()`. This is the piece
  that had no safety net anywhere before; it now does.
- **`DOWNLOAD_PATH`** — renamed to `AUDIO_TRACKS_DIR` in `docker-compose.yml`,
  matching what `config.py` actually reads.
- **`ALLOWED_DOMAINS`** — removed from this service entirely rather than
  wired up here. The follow-up decision was that a domain allow-list
  duplicated across two independently configured sources (an env var on this
  container, plus whatever the backend enforces) is exactly the
  "two sources of truth that drift" pattern this codebase already flags
  elsewhere (duplicated version numbers, the two migration mechanisms in
  `ServiceReview.md`). So there is now exactly **one** list, and it lives in
  the backend:
  - `backend_service/core/media_settings.py` reads
    `media_import_allowed_domains` from `general_settings.json` — the same
    file and the same "read fresh, no restart needed" contract as
    `playback_settings.py` and every other WebUI-editable setting.
  - It is editable in the WebUI: Admin -> General -> "Media import: allowed
    domains" (`MediaImportDomainsForm.tsx`), a comma-separated field next to
    the existing upload-limit setting.
  - **The default changed, on explicit product direction, not just a
    technical fix:** YouTube is no longer in the shipped default. Unlike
    SoundCloud and Bandcamp, which both offer downloading as a feature a
    rights holder opts into, YouTube (and other pure streaming platforms)
    have no such mechanism, and importing from them by default carries
    meaningfully higher legal risk than the lawful-use notice alone covers.
    The shipped default is now `soundcloud.com`, `www.soundcloud.com`,
    `bandcamp.com` only. A user who has satisfied themselves that they hold
    the necessary rights for a specific source (including YouTube) can add
    it in the WebUI — it is no longer a code change.
  - `routes_tracks.py`'s `_check_allowed_domain()` now calls
    `read_allowed_domains()` instead of a hardcoded `frozenset`; this
    service itself still has no domain check of its own — see 1.4 for the
    "reached directly, bypassing the backend" risk that leaves open,
    unchanged from before.

Tests: `backend-service/tests/test_media_settings.py` (the list itself:
defaults, clamping, live reload) and `test_track_domain_check.py` (the check
as `routes_tracks.py` actually calls it, including "an admin-added domain is
enforced without a restart").

**Risk actually encountered:** none — `MAX_FILESIZE_MB` only rejects sources
that would have filled the disk anyway; the domain-list move is additive
(same enforcement point, same backend, just configurable) and the full
backend test suite still passes.

---

### [x] [M] 2.2 `SERVICE_PORT` and `LOG_LEVEL` were also configured and ignored

- `service_port` was read from `SERVICE_PORT` but nothing used it — the port
  is hardcoded in the Dockerfile's `CMD`.
- `log_level` was read from `LOG_LEVEL` but `structlog.configure(...)` never
  applied it — every log level was emitted regardless of the setting, and the
  renderer was always the human-readable console format, unlike the rest of
  the fleet's JSON-in-production convention (`shared_lib.logging.setup_structlog()`).

**Done.**

- `service_port` removed from `config.py` outright rather than wired up —
  nothing sets `SERVICE_PORT` today (it was never even in `.env.example`),
  and building out a knob nobody uses is worse than having none.
- `LOG_LEVEL` is now applied via an inlined `structlog.configure(...)` with
  `wrapper_class=structlog.make_filtering_bound_logger(...)` and a
  DEBUG-console / INFO+-JSON renderer switch — the same behavior as
  `shared_lib.logging.setup_structlog()`, copied rather than imported so this
  service keeps its deliberate independence from `shared_lib`
  (`Architecture.md` section 1). Verified in a running container: default
  `LOG_LEVEL` produces JSON log lines with a `"level"` field.

---

### [ ] [N] 2.3 `/health` cannot report a broken dependency

Unchanged from the original finding. `GET /health` always returns
`"status": "healthy"` regardless of whether `ffmpeg` is on `PATH` or the
shared volume is writable. Same "configured is not the same as usable" gap
already found and fixed for the audio service
([Offene-Punkte 1.5](../Offene-Punkte.md)) and tracked fleet-wide
([Offene-Punkte 1.2](../Offene-Punkte.md)).

**Deliberately not done here** — lower urgency than for `audio` (this
service fails the *next* request loudly rather than degrading silently in
the background), and it belongs bundled with whatever fleet-wide `/health`
work comes out of Offene-Punkte 1.2, not solved once per service.

---

## 3. Code quality

### [x] [N] 3.1 Three ruff findings, all auto-fixable

```
E501   line-too-long        downloader.py:101
UP035  deprecated-import    main.py:7   (typing.AsyncGenerator → collections.abc)
UP043  unnecessary-default  main.py:35  (AsyncGenerator[None, None] → AsyncGenerator)
```

**Done.** `ruff check services/media-downloader-service/src/` now reports
zero findings; `mypy --strict` continues to pass cleanly.

---

### [x] [N] 3.2 Two spots of German in an otherwise English service

`main.py:65–66` (one comment block) and `pyproject.toml:11,13` (two lines).
Everything else in the service was already English.

**Done.** Both translated.

---

### [x] [N] 3.3 Zero tests

The only Python service in the fleet with no test directory.

**Done.** 27 tests across four files:

- `tests/test_downloader.py` — the `duration: None` regression (both call
  sites), thumbnail selection (best-of-several and the top-level fallback),
  `max_filesize` reaching `yt-dlp`'s option dict, the "no MP3 appeared"
  error path, and `_embed_thumbnail_fallback()` (embeds and removes the
  sidecar; no-op when there is none) — all via a fake `yt_dlp.YoutubeDL`, no
  network access needed.
- `tests/test_models.py` — the one validator in the service.
- `tests/test_config.py` — environment-variable defaults and overrides.
- `tests/test_main.py` — the health endpoint, and the `output_dir` guard
  (1.4) both rejecting and accepting, the latter proving the
  `asyncio.to_thread` dispatch (1.1) actually completes end-to-end.

---

### [x] [N] 3.4 `yt-dlp` had no upper version bound, unlike everything else in `requirements.txt`

```
yt-dlp>=2025.3.31
```

**Done.** A comment now explains why: yt-dlp ships releases purely to track
upstream site changes, so a ceiling would mean extractors going stale instead
of a controlled version bump.

**Found in passing, fixed alongside it:** `uvicorn[standard]` was pulling in
uvloop, PyYAML, websockets, watchfiles and httptools — the same unused-extras
finding already made for `led`/`button`/`display` in their own reviews. None
of it is used here either (no WebSocket endpoint, no YAML config, no
`--reload`). Unlike those three services, uvloop would actually have applied
here (this service starts via `python -m uvicorn`, not a custom loop that
preempts uvicorn's loop selection) — but the event loop's job is limited to
HTTP handling and dispatching to a thread for the real work (1.1), which is
not enough traffic for uvloop's throughput gains to matter. Switched to plain
`uvicorn`.

---

## 4. Docker image

**A note on measurement:** the three tools available in this environment
disagreed with each other on this image's total size — `docker images`/
`docker system df` reported **978 MB**, `docker inspect --format '{{.Size}}'`
reported **238 MB**, and summing `docker history` gave **≈ 728 MB**. This
looks like an artifact of this specific local Docker setup rather than a real
ambiguity in the image itself. The before/after in the Result section above
uses `docker inspect` consistently on both builds, which is the one
comparison that stays valid regardless of which absolute number is "true" —
re-check `docker images` directly on the target box before trusting an
absolute figure from either build.

Layer breakdown before this branch:

```
424 MB   RUN apt-get install ffmpeg curl        ← by far the largest single layer
 73 MB   COPY /app/deps (pip packages)
 73.1 MB RUN useradd && chown -R                ← 4.1, nearly duplicated the line above
 109 MB  debian trixie base
 43.7 MB python build layer (base image)
  5 MB   ca-certificates, netbase, tzdata
```

### [x] [N] 4.1 `chown -R` nearly doubled the cost of the layer before it

```dockerfile
COPY --from=builder /app/deps /app/deps        # 73 MB
...
RUN useradd -m -u 1000 minabox \
    && mkdir -p /mnt/audio/tracks/downloads \
    && chown -R minabox:minabox /app /mnt/audio   # 73.1 MB
```

`chown -R` on a directory copied in an earlier layer forces a full copy-up of
every file into the new layer on overlayfs, even though content is
untouched — so this layer cost almost exactly what the `COPY` before it cost,
a second time.

**Not unique to this service** — `backend-service`, `rfid-service` and
`led-service` use the identical `useradd && chown -R` pattern and would see
the same effect, proportional to the size of what they copy. Fixed here
only; the fleet-wide version is a separate, follow-up branch.

**Done.** `useradd`/`mkdir` moved earlier (into the existing `apt-get` layer,
before anything is copied), and both `COPY` instructions now carry
`--chown=minabox:minabox` directly instead of a trailing `chown -R`. Verified
with a local build: `COPY --from=builder --chown=... /app/deps /app/deps`
measured **47.2 MB** (replacing the old 73 MB + 73.1 MB pair outright — the
gap is smaller than the deps copy alone because of 3.4's `uvicorn[standard]`
removal landing in the same build), and `id minabox` / a directory listing
inside the built image confirm `/app/deps`, `/app/src` and the downloads
directory are owned by `minabox`, not root.

---

### [ ] Not pursued: shrinking the 424 MB `ffmpeg` layer

Still the actual size driver, and still not attempted, for the same reason as
before: this container's entire purpose is the `ffmpeg` conversion step, and
both realistic options — a minimal static build (needs a confirmed
`libmp3lame`-capable `aarch64` build, pinned and checksummed like the `lgpio`
precedent) or an Alpine/musl base switch — carry a real chance of silently
breaking that conversion for some class of source URL, in a way that would
not show up until it hits a real user's box. Worth a dedicated, isolated
investigation; not worth doing inside this change.

---

### [x] [N] 4.2 `gcc` in the builder stage was unused

Not checked in the original pass whether any dependency actually needed to
compile.

**Done, and confirmed rather than assumed.** Every installed package's
`WHEEL` metadata resolves to `py3-none-any` or a `manylinux`/`cp313`
`aarch64` tag — nothing compiles. Removed `gcc` from the builder stage; also
removed `ffmpeg` from the builder stage specifically (it was installed there
too, redundantly — nothing at build time shells out to it, and the runtime
stage already installs its own copy). Neither change affects the shipped
image size on its own, since the builder stage is discarded either way; both
shorten the build.

---

## 5. What I would not touch

- **The retry logic in the backend's `MediaDownloaderClient`.** Correct,
  tested-by-inspection, and matches what `Architecture.md` describes.
- **The `extractor_args` workaround for YouTube's client selection.** A
  narrowly scoped fix for a real, named breakage, with a comment that says
  why. Leave it alone until it stops working.
- **The multi-stage Dockerfile structure itself.** Builder/runtime separation
  is correct and already keeps build-only tooling out of the shipped image.
- **Storing audio as MP3 with embedded ID3 cover art.** Matches every other
  track in the library regardless of source; changing it would ripple into
  the audio service and the WebUI player for no benefit identified here.

---

## 6. Remaining / follow-up

**Not done here, on purpose:**

1. **2.3** — `/health` honesty. Bundle with
   [Offene-Punkte 1.2](../Offene-Punkte.md) (fleet-wide) rather than solving
   it once per service.
2. **The 424 MB `ffmpeg` layer** (section 4). Real cost, real risk, needs its
   own investigation and its own hardware test pass.
3. **The `chown -R` → `COPY --chown` fix, fleet-wide.** Applied here only;
   `backend-service`, `rfid-service` and `led-service` carry the same
   pattern and would see the same effect at a size proportional to what each
   copies.

**Worth knowing about, not a defect:** this service still has no domain
check of its own (1.4/2.1) — reaching it directly, bypassing the backend,
still bypasses the allow-list entirely. That was true before this branch and
remains true after it; the fix would be a second enforcement point with its
own configuration to keep in sync, which is the exact duplication 2.1 just
removed on the backend side. Left as an accepted risk of the "no
authentication on this port" design documented in `Architecture.md` section
8, not reopened here.
