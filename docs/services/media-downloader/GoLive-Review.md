# Media Downloader Service – Go-Live Review

Line-by-line review of `services/media-downloader-service/` ahead of going
live: all 5 Python files (325 lines total), the Dockerfile, `pyproject.toml`,
`requirements.txt`, `README.md`, the compose block, and the parts of
`backend-service` this service is coupled to
(`media_downloader_client.py`, `routes_tracks.py`).

**Starting position:** the service works. Nothing below is a fix for
something visibly broken today on the box you have been running; it is the
list of things that are more likely to bite once real, unpredictable URLs and
concurrent usage hit it. None of the fixes below have been applied yet — this
is the assessment, not a result.

Legend: `[ ]` open · **[H]** high · **[M]** medium · **[N]** low

---

## Summary

Two items would concretely hurt a user during normal operation and are worth
fixing before go-live:

- **1.1** — both endpoints block the single event loop for the full duration
  of a download (typically tens of seconds, easily minutes for a long track on
  a Pi). While that runs, the container cannot answer its own Docker health
  check. The health check has `interval 30s / timeout 10s / retries 3` — three
  consecutive misses (90 s) mark the container unhealthy, and on a Pi a
  video-to-MP3 conversion can easily take longer than that. This is the exact
  bug class the team already found and fixed in `host-helper` (42 blocking
  handlers) and the backend's upload endpoint — see `ServiceReview.md`,
  sections 2 and 3 — just not caught here.
- **1.2** — a source with no known duration (a livestream, or any extractor
  that returns `duration: None`) crashes the request with an unhandled
  `TypeError` instead of a clean `422`. `None * 1000` is not guarded anywhere
  the response is built.

Everything else is either a smaller correctness point, dead configuration
that gives a false sense of a safety net that is not actually there, or an
image-size opportunity. Nothing here found a defect in yt-dlp usage itself,
in the retry logic, or in the domain allow-list — those are sound.

---

## 1. Functional defects

### [ ] [H] 1.1 Both endpoints block the event loop for the whole download

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

Both handlers are declared `async def` but call a synchronous method that
does network I/O, spawns `ffmpeg`, and writes to disk — directly, with no
`await asyncio.to_thread(...)`. FastAPI does not move that work off the event
loop by itself; only a genuinely synchronous `def` handler gets the automatic
threadpool treatment. Because this is `async def`, the coroutine runs to
completion on the single event loop, and nothing else the service does —
including `GET /health` — can be served until it returns.

**Consequence on this hardware specifically:** the Dockerfile's health check
is `interval: 30s, timeout: 10s, retries: 3`. Three misses in a row (90 s of
an unresponsive event loop) mark the container unhealthy, and
`docker-compose.yml`'s `restart: unless-stopped` will eventually cycle it. An
in-progress `ffmpeg` conversion gets killed mid-file, the backend's
`MediaDownloaderClient` sees a connection error, retries up to twice more
(section 4 of `Architecture.md`), and if all three attempts land during the
same busy window, the track import is deleted and reported as failed to the
user — for a source that would have downloaded fine on a quieter service.

**Fix:** `await asyncio.to_thread(downloader.download_video, request.url, output_dir)`
and the same for `get_video_info`. This is the identical fix already applied
to `host-helper` and the backend's `upload_track` — see
`ServiceReview.md`, "Datei-Upload fror das Backend ein" and "Host-Helper: 42
blockierende Handler".

**A fix here needs a second decision alongside it, not after:** once the
event loop is free during a download, concurrent `/download` requests become
possible, and each one spawns its own `ffmpeg` process. Two audiobook-length
imports at once on a Pi's limited cores is a worse failure mode than the
current accidental serialization. An `asyncio.Semaphore(1)` (or a small
number) around the download path should land in the same change, not as a
follow-up — otherwise fixing 1.1 trades a health-check problem for a
CPU-contention problem.

**Risk of the fix itself:** low — `asyncio.to_thread` changes no behavior of
`downloader.py`, only where it runs. The semaphore needs a decision on the
concurrency limit, which is the only reason this isn't a one-line change.

---

### [ ] [H] 1.2 A source with no known duration crashes the request

`downloader.py`, both `download_video()` (line 95) and `get_video_info()`
(line 123):

```python
"duration_ms": int(info.get("duration", 0) * 1000),
```

`dict.get(key, default)` only returns the default when the key is **absent**.
Several yt-dlp extractors set `duration` to `None` explicitly — livestreams
and some non-YouTube sources are the common case — and then this line
computes `None * 1000`, which raises `TypeError` inside the `try` block that
is only set up to catch `yt_dlp.utils.DownloadError`. The `TypeError`
propagates out of the endpoint unhandled, and FastAPI turns it into a bare
`500 Internal Server Error` with no `DOWNLOAD_FAILED`/`INFO_FAILED` envelope —
the one error shape every other failure path in this service produces.

**Fix:** `info.get("duration") or 0` in both places.

**Risk:** none. It only changes behavior for the case that currently crashes.

---

### [ ] [N] 1.3 A comment describes the opposite of what the code does

`downloader.py`, lines 80–86:

```python
# Best-quality thumbnail URL from yt-dlp: prefer the first entry in
# info["thumbnails"] (sorted best-first by yt-dlp) or fall back to
# the top-level "thumbnail" field.
thumbnail_url: str = ""
thumbnails = info.get("thumbnails")
if thumbnails and isinstance(thumbnails, list):
    thumbnail_url = thumbnails[-1].get("url", "") or ""
```

The comment says the list is sorted best-first and to take the first entry.
The code takes `thumbnails[-1]` — the **last** entry. yt-dlp actually sorts
`info["thumbnails"]` ascending by preference (worst first, best last), so the
code is right and the comment describes the reverse of reality. Left as is,
a future reader who trusts the comment over the code has a plausible reason
to "fix" this into an actual bug.

**Fix:** correct the comment to describe the actual (correct) behavior. Purely
a documentation fix inside the code, worth doing in the same pass as the
English-language cleanup (section 3.2).

**Risk:** none — comment-only.

---

### [ ] [N] 1.4 `output_dir` reaches the filesystem with no validation

`models.py`: `output_dir: str | None = None  # optional: absolute path inside the container`
has no path validation. `main.py` turns it straight into `Path(request.output_dir)`,
and `downloader.py` uses it both for `mkdir(parents=True, exist_ok=True)` and
as the yt-dlp `outtmpl` base. Whoever can reach this service's port can point
a download at any path the `minabox` user (UID 1000) can write to inside the
container — bounded by container filesystem permissions, but not by the API
itself.

In the intended flow this is harmless: only the backend calls `/download`,
and it always builds `output_dir` itself
(`AUDIO_STORAGE_PATH / str(track_id)`). But per section 9 of
`Architecture.md`, the API has no authentication and is reachable from the
host at `127.0.0.1:8007` — anything with local shell access to the box
bypasses the backend, the domain allow-list, and this validation gap all at
once.

**Fix, if pursued:** require `output_dir` to resolve inside a configured base
directory (e.g. `AUDIO_TRACKS_DIR`), reject anything else with `422`.

**Risk:** low, but double-check the backend never legitimately sends an
`output_dir` outside that base before tightening this — a quick grep confirms
it does not today (always under `AUDIO_STORAGE_PATH`).

---

## 2. Robustness & configuration

### [ ] [H] 2.1 Three environment variables are set on this container and read by nobody

`docker-compose.yml` sets `DOWNLOAD_PATH`, `MAX_FILESIZE_MB` and
`ALLOWED_DOMAINS` on the `media-downloader` service. `config.py` has no field
for any of the three — they are silently ignored. Concretely:

- `DOWNLOAD_PATH` — dead. The service reads `AUDIO_TRACKS_DIR` instead, and in
  the actual `/from-url` flow the backend always supplies `output_dir`
  explicitly anyway, so neither variable matters in practice today. It does
  matter for anyone calling `/download` directly without `output_dir` — the
  wrong variable name means they cannot redirect it via `.env` the way the
  compose file implies they can.
- `ALLOWED_DOMAINS` — dead in this service. The actual enforcement
  (`_ALLOWED_DOMAINS` in `routes_tracks.py`) lives in the backend and does not
  read this variable either — it is a hardcoded `frozenset` in Python. So
  `MEDIA_DOWNLOADER_ALLOWED_DOMAINS` in `.env.example` currently configures
  nothing at all, anywhere.
- `MAX_FILESIZE_MB` — dead, and unlike the other two, **nothing replaces it.**
  Grepping both this service and the backend finds no file-size check on the
  URL-import path at all (the upload path has its own, unrelated limit via
  `max_audio_upload_bytes()`). yt-dlp is never given a `max_filesize` option.
  A URL on an allowed domain that happens to be a very large or very long
  file downloads in full, with nothing to stop it, onto a shared volume that
  also holds every other track.

**Fix, three independent pieces:**

1. Wire `MAX_FILESIZE_MB` into this service's `ydl_opts` as yt-dlp's own
   `max_filesize` option (in bytes) — this is the one with an actual gap
   behind it.
2. Either read `ALLOWED_DOMAINS` from the environment in the backend instead
   of the hardcoded set, or remove the variable from compose/`.env.example`
   so it stops implying a control that does not exist.
3. Fix `DOWNLOAD_PATH` → `AUDIO_TRACKS_DIR` in `docker-compose.yml`, or drop
   it if the intent is that `output_dir` always wins.

**Risk:** low for (1) — it only rejects sources that would have filled the
disk anyway. (2) and (3) are consistency fixes with no behavior change to the
normal `/from-url` flow, since the backend never relies on either variable
today.

---

### [ ] [M] 2.2 `SERVICE_PORT` and `LOG_LEVEL` are also configured and ignored

Smaller version of 2.1, inside `config.py` itself rather than compose:

- `service_port` is read from `SERVICE_PORT` but nothing in `main.py` uses
  it — the port is hardcoded in the Dockerfile's `CMD` (`--port 8007`).
  Setting `SERVICE_PORT` today changes nothing and does not even break
  anything, which is its own problem: it looks like a working knob.
- `log_level` is read from `LOG_LEVEL` but `main.py`'s
  `structlog.configure(...)` call never uses it — there is no
  `wrapper_class=structlog.make_filtering_bound_logger(...)`. Every log call
  at every level is emitted regardless of what `LOG_LEVEL` is set to.

Compare `shared_lib.logging.setup_structlog()`, used by `host-helper` and
`audio-service`: it both applies the level filter and switches the renderer
(`ConsoleRenderer` in `DEBUG`, `JSONRenderer` otherwise — the format the rest
of the fleet's log aggregation expects). This service always uses
`ConsoleRenderer`, in every environment, regardless of `LOG_LEVEL`.

**Fix:** either drop `SERVICE_PORT` from `config.py` (it does nothing and
should not appear to), or wire it into the `CMD`/`uvicorn.run()` for real.
For logging, apply the same filtering + JSON-in-production pattern already
established elsewhere. Given this service deliberately has no `shared_lib`
dependency (see `Architecture.md` section 1 — it is meant to stay easy to
extract as a standalone package), the cleanest fix is to inline the ~15 lines
of the correct `structlog.configure(...)` call rather than adding the
dependency, not to pull in `shared_lib.logging`.

**Risk:** low. This only makes existing settings do what their names already
claim.

---

### [ ] [N] 2.3 `/health` cannot report a broken dependency

`GET /health` always returns `"status": "healthy"` — there is no check of
whether `ffmpeg` is on `PATH`, whether `AUDIO_TRACKS_DIR` (or the shared
volume it lives on) is writable, or whether the last several downloads
succeeded. This is the same "configured is not the same as usable" gap the
team already found and fixed for the audio service
([Offene-Punkte 1.5](../Offene-Punkte.md)) and is tracking for the fleet in
general ([Offene-Punkte 1.2](../Offene-Punkte.md)).

Lower urgency here than for `audio`: this service does not run continuously,
so a broken dependency fails the *next* request loudly (a `422` from a failed
download) rather than degrading silently in the background. Worth a mention,
not worth doing in isolation — bundle with whatever fleet-wide `/health`
work comes out of Offene-Punkte 1.2.

---

## 3. Code quality

### [ ] [N] 3.1 Three ruff findings, all auto-fixable

```
.venv/bin/ruff check services/media-downloader-service/src/
```

```
E501   line-too-long        downloader.py:101
UP035  deprecated-import    main.py:7   (typing.AsyncGenerator → collections.abc)
UP043  unnecessary-default  main.py:35  (AsyncGenerator[None, None] → AsyncGenerator)
```

`mypy --strict` passes cleanly with zero issues — the typing itself is solid.

**Risk:** none, `ruff check --fix` handles two of the three; the long line
needs a manual wrap.

---

### [ ] [N] 3.2 Two spots of German in an otherwise English service

Checked every line of every source and config file. The result is short:

- `main.py:65–66` — one comment block:
  ```python
  # Dieser Dienst bindet shared-lib nicht ein; die Variable setzt der
  # Dockerfile aus dem Build-Arg (docs/Versionierung.md).
  ```
- `pyproject.toml:11,13` — two comment lines about where the version number
  lives.

Everything else — every docstring, every identifier, every `structlog` event
name, the entire `Dockerfile`, and the entire `README.md`'s technical
sections — is already English (`README.md`'s lawful-use notice is
deliberately bilingual; see that file). This is by a wide margin the
smallest language-cleanup item of anything in this review — three lines, no
structural change, safe to do together with 1.3.

**Risk:** none — comment-only.

---

### [ ] [N] 3.3 Zero tests

```
services/audio-service:    8 test files
services/backend-service: 21 test files
services/button-service:   3 test files
services/display-service: 17 test files
services/host-helper:      2 test files
services/led-service:      7 test files
services/media-downloader: 0 test files
services/rfid-service:     6 test files
```

The only Python service in the fleet with no test directory at all. The
highest-value first tests, none of which need network access or a real
download:

1. `_embed_thumbnail_fallback()` — with a prepared MP3 + sidecar image fixture,
   confirms the APIC frame is written and the sidecar is removed; also the
   "no leftover thumbnail" early-return path.
2. The result dict assembly in `download_video()`/`get_video_info()` against a
   hand-built yt-dlp `info` dict — this is exactly what would have caught 1.2,
   and cheaply, since it needs no real yt-dlp call.
3. `DownloadRequest.url_must_not_be_empty` — trivial, but it is the one
   validator in the service and currently unverified.

**Risk:** none — pure addition.

---

### [ ] [N] 3.4 `yt-dlp` has no upper version bound, unlike everything else in `requirements.txt`

```
yt-dlp>=2025.3.31
```

Every other dependency in this file has a `<x.y.0` ceiling. This one likely
is deliberate — yt-dlp ships frequent releases purely to track upstream site
changes, and pinning it tightly would mean extractors silently going stale —
but nothing in the repository says so, which makes it look like an oversight
next to the disciplined pinning everywhere else.

**Fix, if the reasoning above is correct:** a one-line comment above it
saying why, so a future pass does not "fix" it into a ceiling by accident.

**Risk:** none — documentation only.

---

## 4. Docker image

**A note on measurement:** the three tools available in this environment
disagreed with each other on this image's total size — `docker images`/
`docker system df` report **978 MB**, `docker inspect --format '{{.Size}}'`
reports **238 MB**, and summing `docker history` gives **≈ 728 MB**. This
looks like an artifact of this specific local Docker setup rather than a real
ambiguity in the image itself, so no absolute total below should be trusted
without re-checking `docker images` directly on the target box. What *is*
reliable — because it comes from a single, consistent tool run once — is the
**relative** layer breakdown from `docker history`, which is what the
findings below are based on:

```
424 MB   RUN apt-get install ffmpeg curl        ← by far the largest single layer
 73 MB   COPY /app/deps (pip packages)
 73.1 MB RUN useradd && chown -R                ← 4.1, nearly duplicates the line above
 109 MB  debian trixie base
 43.7 MB python build layer (base image)
  5 MB   ca-certificates, netbase, tzdata
```

For comparison, every other locally-tagged image in the fleet is smaller,
`minabox-audio` (which genuinely needs VLC + PulseAudio client libraries)
being the closest second.

### [ ] [N] 4.1 `chown -R` nearly doubles the cost of the layer before it

```dockerfile
COPY --from=builder /app/deps /app/deps        # 73 MB
...
RUN useradd -m -u 1000 minabox \
    && mkdir -p /mnt/audio/tracks/downloads \
    && chown -R minabox:minabox /app /mnt/audio   # 73.1 MB
```

`chown -R` on a directory copied in an earlier layer changes every file's
metadata, and on overlayfs that forces a full copy-up of each file into the
new layer even though its content is untouched — so this layer costs almost
exactly what the `COPY` before it cost, a second time.

**This is not unique to this service** — `backend-service`, `rfid-service`
and `led-service` all use the identical `useradd && chown -R` pattern. It is
flagged here specifically because this service's `/app/deps` is what makes
the duplication expensive; the fix is worth doing fleet-wide, in its own
branch, rather than only here.

**Fix:** `COPY --from=builder --chown=minabox:minabox /app/deps /app/deps` and
`COPY --chown=minabox:minabox media-downloader-service/src/ ./src/`, dropping
`chown -R` from the `RUN` line (keep `useradd` and `mkdir`). `--chown` sets
ownership as part of the copy itself, with no separate metadata-only layer.

**Risk:** none functionally — final ownership on disk is identical. Confirm
with `docker run --rm <image> id minabox` and a directory listing after
rebuilding, since it is easy to typo the flag and end up back at root
ownership silently.

### [ ] Not pursued here: shrinking the 424 MB `ffmpeg` layer

This is the actual size driver, and cutting it meaningfully means one of:

- **A minimal static `ffmpeg` build**, pinned to a tag and checksum — the
  same pattern already accepted in this repo for `lgpio`
  ([Offene-Punkte 2.1](../Offene-Punkte.md)). This needs someone to first
  confirm a build with `libmp3lame` (the encoder this service actually needs
  for `preferredcodec: "mp3"`) exists for `aarch64`, since many minimal
  builds strip encoders with licensing complications.
- **Switching the base image to Alpine** and installing `ffmpeg` via `apk`,
  which typically pulls a much smaller dependency tree than Debian's package.

**I would not do either of these before go-live, and would want a dedicated
branch with its own test pass even after:** this container's entire purpose
is the `ffmpeg` conversion step. A minimal build that is missing a codec a
real-world URL happens to need, or an Alpine/musl switch that changes how
`pydantic-core`'s compiled extension or DNS resolution behaves, fails exactly
the thing this service exists to do — and might only show up on a specific
class of source URL, not on whatever gets tested by hand before shipping.
The 424 MB is a real cost on a Pi's SD card, but it is currently a *working*
424 MB. Worth a future, isolated investigation; not worth the risk attached
to doing it now.

### [ ] [N] 4.2 `gcc` in the builder stage may be unused

The builder stage installs `gcc` alongside `ffmpeg` before `pip install`. Not
checked here whether any of the seven dependencies actually need to compile
(most likely candidate: `pydantic-core`, which does ship `aarch64` wheels on
PyPI for recent Python versions, in which case `gcc` never fires). This does
not affect the shipped image size — the builder stage is discarded — only CI
build time. Worth the same one-command check the display review used:

```
docker exec <container> sh -c \
  'for w in /app/deps/lib/python3.13/site-packages/*.dist-info/WHEEL; do \
     echo "$(basename $(dirname $w)): $(grep -h ^Tag: $w | tr "\n" " ")"; done'
```

If everything resolves to `py3-none-any` or a `manylinux`/`musllinux` wheel,
`gcc` (and `ffmpeg` in the *builder* stage specifically — it has no reason to
be there either, since nothing at build time shells out to it) can go.

**Risk:** none for the image; only rebuild-time savings.

---

## 5. What I would not touch

- **The domain allow-list and retry logic in the backend.** Both are correct,
  tested-by-inspection, and match what `Architecture.md` describes. Section
  2.1 above is about the *unused* variables around them, not about the
  allow-list or retry mechanism itself.
- **The `extractor_args` workaround for YouTube's client selection.** It is
  a narrowly scoped fix for a real, named breakage, with a comment that says
  why. Leave it alone until it stops working.
- **The multi-stage Dockerfile structure itself.** Builder/runtime separation
  is correct and already keeps `gcc` (mostly) and build-only tooling out of
  the shipped image.
- **Storing audio as MP3 with embedded ID3 cover art.** Matches every other
  track in the library regardless of source; changing it would ripple into
  the audio service and the WebUI player for no benefit identified here.

---

## 6. Suggested order

**Before go-live:**

1. **1.2** — the `duration_ms` crash. One line, two call sites, no risk.
2. **1.1** — `asyncio.to_thread` plus a concurrency limit, together. This is
   the item most likely to actually cause a support ticket ("the import
   failed for no reason") once real usage starts.
3. **2.1(1)** — wire `MAX_FILESIZE_MB` into yt-dlp's `max_filesize`. Closes
   the one gap that has no safety net anywhere today.
4. **1.3, 3.2** — the wrong comment and the three German lines, together,
   since both are comment-only and touch the same files as the fixes above.

**Shortly after, in one branch:**

5. **2.1(2)+(3), 2.2** — make the compose/`.env.example` variables either do
   what they claim or disappear.
6. **3.1** — the three ruff findings.
7. **3.3** — tests, starting with the two listed in section 3.3 — they would
   have caught 1.2 for free.

**Its own branch, own testing:**

8. **4.1** — the `chown -R` → `COPY --chown` fix, ideally done fleet-wide
   (backend, rfid, led) in the same branch rather than once per service.

**Deliberately not before go-live:**

9. The 424 MB `ffmpeg` layer (section 4). Real cost, real risk, needs its own
   investigation and its own hardware test pass — see the reasoning above.

**Fleet-wide, not this service:**

10. `/health` honesty (2.3) — bundle with [Offene-Punkte 1.2](../Offene-Punkte.md).
