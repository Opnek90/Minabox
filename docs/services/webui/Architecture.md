# WebUI Service – Architecture

## 1. Purpose & Responsibility

The WebUI is the browser front end of the Minabox. It is a static React
single-page application, built once and served by Nginx, that turns the
backend's REST API and WebSocket feed into the surface a family actually
operates: a player, a card manager, a media library, a parent dashboard and a
settings area.

Goals:

- One interface for two very different users. A child taps play and volume; a
  parent sets time limits, imports media and updates the box. The player page
  stays deliberately sparse, everything else lives one navigation step away.
- Immediate feedback. Playback state, RFID scans and system alerts arrive over
  the WebSocket, not by polling — the box and the browser must never disagree
  about what is playing.
- Usable on the device at hand. Phone, tablet and desktop get three different
  layouts from the same components (section 6), and the German/English
  translation is loaded at runtime, not compiled in.
- Never a dead end. A missing optional component hides its menu entry instead of
  offering a page that does nothing; a lost connection produces an overlay with
  a diagnostics export rather than a blank screen.

The service holds no state of its own beyond browser `localStorage`. It talks to
exactly one host — the backend, through the same origin — and knows nothing
about MQTT, the database or the hardware.

---

## 2. Technology Stack

| Layer            | Choice                                    | Note                                                             |
| ---------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| Framework        | React 18 + TypeScript 5 (`strict`)         | `noUnusedLocals` and `noUnusedParameters` are on.                 |
| Build            | Vite 5                                     | `build:fast` (Vite only) is what the Dockerfile runs.             |
| UI               | MUI v5 + Emotion                           | Deep icon imports only, so the icon set tree-shakes.              |
| Routing          | React Router v6                            | Pages are `React.lazy` — one chunk per page.                      |
| Server state     | React Query 5 **and** local `useState`     | Two layers in parallel; see section 5.3.                          |
| HTTP             | Axios, `baseURL: /api/v1`, `withCredentials` | Session cookie, no token handling in the app.                   |
| Realtime         | Native `WebSocket` at `/ws`                 | Exponential reconnect, 1 s → 30 s.                                |
| i18n             | i18next + `i18next-http-backend`            | 7 namespaces fetched at runtime from `/locales/`.                 |
| PWA              | `vite-plugin-pwa` (`autoUpdate`)            | Manifest, icons, precached shell.                                 |
| Compression      | `vite-plugin-compression` → `gzip_static`   | Pre-built `.gz`, so the Pi does not compress per request.         |
| Web server       | Nginx (`alpine-slim`)                       | SPA fallback, reverse proxy, caching, security headers.           |
| Tests            | Vitest + Testing Library                    | 8 files, 30 tests — regression pins, not coverage.                |

---

## 3. File & Folder Structure

Relevant path: `services/webui-service/`

```text
webui-service/
├── Dockerfile                 # node:20-alpine (build) → nginx:alpine-slim (serve)
├── nginx/
│   ├── nginx.conf             # SPA fallback, /api + /ws proxy, caching
│   └── security-headers.conf  # Included per location; see section 7.1
├── vite.config.ts             # PWA, gzip, manual chunks, BUILD_ID
├── VERSION                    # Own version number (docs/Versionierung.md)
├── scripts/
│   ├── check-locales.mjs      # de/en in sync, plurals complete, dead keys
│   └── check-i18n-calls.mjs   # every static t() key exists in the JSON
├── public/locales/{de,en}/    # common, player, rfid, media, admin, errors, setup
└── src/
    ├── api/                   # One module per backend resource
    │   ├── client.ts          # Axios instance, retry, timeouts, 401 hook, debug buffer
    │   ├── auth.ts  capabilities.ts  config.ts  system.ts
    │   ├── audio.ts  tags.ts  tracks.ts  playlists.ts
    │   └── streams.ts  podcasts.ts  scanHistory.ts  stats.ts
    ├── contexts/              # Six providers, see section 5.1
    ├── hooks/                 # useAudioStatus, useLayout, useSetupStatus, …
    ├── pages/                 # One per route, all lazy-loaded
    ├── components/
    │   ├── common/            # Shell: Header, Navigation, PageShell, dialogs
    │   ├── ui/                # ActionButton, VolumeSlider
    │   ├── player/  rfid/  media/  dashboard/  setup/
    │   └── admin/             # Settings panels + ConfigForm/ sub-forms
    ├── config/settingsIndex.ts # The settings tree — data, not JSX
    ├── types/api.ts           # Mirrors the backend Pydantic schemas
    ├── i18n/                  # init, language list, namespaces, debug mode
    ├── fonts.css              # Roboto, latin subset, woff2 only
    └── utils/                 # apiError, formatTime, validators, debugRingBuffer
```

Two files deserve naming here because everything else hangs off them.
`config/settingsIndex.ts` describes the settings area as plain data — groups,
sections, the i18n keys of the fields inside them, and which optional component
a section depends on. `AdminPage` renders forms against it and the command
palette searches the same structure, so there is exactly one place where the
settings tree is cut. `api/client.ts` is the only module that talks to the
network; every `api/*.ts` sibling goes through it and therefore inherits the
retry, the 401 handling and the debug-buffer recording for free.

---

## 4. Routes & Pages

| Route        | Page               | Notes                                                                  |
| ------------ | ------------------ | ---------------------------------------------------------------------- |
| `/player`    | `PlayerPage`       | Default route. Cover, transport, volume; everything else in an overflow menu. |
| `/rfid`      | `RfidPage`         | Card list, learn mode, assignment. Hidden entirely without a reader.    |
| `/media`     | `MediaPage`        | Five tabs: recent, playlists, tracks, streams, podcasts.                |
| `/dashboard` | `DashboardPage`    | Parent view: overview, rules, statistics, scan history.                 |
| `/admin`     | `AdminPage`        | Settings, grouped and searchable.                                       |
| `/setup`     | `SetupWizardPage`  | First-run wizard. Deliberately **not** behind `ProtectedRoute`.         |
| `/kiosk`     | `KioskPage`        | Full-screen player. Rendered outside the main layout and outside `CapabilitiesProvider`. |

Everything else redirects to `/player`, including `/rfid` when no reader is
installed — a deep link must not land on a page whose central actions do
nothing.

The setup wizard is the one route without a password gate, and it has to be:
step 2 is where the password is set, so gating it would lock the user out of the
flow that creates the credential.

### 4.1 Player

`useAudioStatus` extrapolates the playback position locally: it takes the last
`audio_status` message and adds the elapsed time, then ticks once a second while
playing. The progress bar therefore moves smoothly without a single extra
request, and a page opened mid-track shows the right position on first render
rather than jumping when the next message lands.

The main card is intentionally short — state chip, cover, progress, transport,
volume. Sleep timer, output device, repeat and shuffle live in an overflow
menu, because the person using this page most often is a child who wants two
buttons, not nine.

### 4.2 RFID

Learn mode is a three-step conversation with the box: the page enables it via
`POST /rfid/learning-mode`, the reader reports the card as
`rfid_scanned_learning` over the WebSocket, and the dialog that opens writes the
assignment. Closing the dialog turns learn mode back off — leaving it on would
make the next card scanned anywhere in the house open an assignment dialog.

A scan outside learn mode surfaces globally rather than only on this page:
`RfidScanDrawer` sits in the app shell, and an unknown card produces a snackbar
with a link to `/rfid`.

### 4.3 Media

Tracks, streams and podcasts each have their own folder tree, and all three
lists share one shape: search field, view toggle (cards or list), sort, filter,
pagination. Folder assignment works by drag and drop onto the tree, with a
"move to" menu as the fallback for touch devices.

Deleting a media item first asks the backend which cards point at it and, if
there are any, offers to clear those assignments in the same step. Deleting only
the media leaves a card pointing at a track that no longer exists; the dialog
names the affected cards instead of asking the user to remember them.

### 4.4 Dashboard and Settings

The dashboard is the parent's everyday view — minutes listened, remaining daily
limit, library counts, listening statistics, scan history, and the rules that
produce those numbers. The settings page is the *setup* area, cut by everyday
question ("Playback", "Sound", "Appearance") rather than by where a value
happens to live in the backend. Everything technical collects at the bottom
under "Advanced".

The search field above the settings renders a jump list, not the expanded forms.
A two-letter query matches almost every section, and mounting eleven panels at
once would fire eleven API calls on a Raspberry Pi.

Sections that hang off an optional component carry `requiresFeature` in
`settingsIndex.ts` and disappear — along with a group that becomes empty —
when `GET /system/capabilities` says the component is not installed. Details:
[Component-Capabilities.md](Component-Capabilities.md).

---

## 5. Application Architecture

### 5.1 Provider stack

```text
QueryClientProvider → BrowserRouter → ThemeContextProvider → ThemedApp
  └ ThemeProvider (MUI) → AuthProvider → WebSocketProvider → App
      └ ToastProvider → UserPrefsProvider → Routes
          └ CapabilitiesProvider → MainLayout   (not on /kiosk)
```

| Context             | Holds                                          | Persistence                    |
| ------------------- | ---------------------------------------------- | ------------------------------ |
| `ThemeContext`      | Light/dark, accent preset, font scale           | `localStorage`, applied as CSS custom properties on `<html>` |
| `AuthContext`       | Whether auth is on, which paths are gated, session state | Cookie (backend), config fetched at start |
| `WebSocketContext`  | Connection, last message, cached audio status   | Memory                          |
| `ToastContext`      | Notification stack (max 3 visible)               | Memory                          |
| `UserPrefsContext`  | View mode, sort, filter, page size per list      | `localStorage`                  |
| `CapabilitiesContext` | Which optional components exist                | `localStorage` cache + refresh  |

Two of these fail *open* on purpose. `CapabilitiesContext` treats everything as
installed while loading and when the request fails, and it reads its last known
answer from `localStorage` synchronously at start — a network hiccup must never
make a feature disappear, and a returning user must not watch the menu
rearrange itself. `useSetupStatus` takes the same line in reverse: if the
backend cannot be reached, it decides the setup wizard is *not* needed, because
a false "please set up your box" is worse than no hint at all.

### 5.2 WebSocket

`WebSocketContext` holds a single connection for the whole app. Every message is
pushed twice: into React state (`lastMessage`, plus the two cached shapes
`cachedAudioStatus` and `sleepTimerStatus`) and onto a module-level
`EventTarget`. The event target exists so a component can subscribe to one
message type without re-rendering on every unrelated message; `useWebSocketEvent`
is the hook for that, and the only correct way to subscribe. Listening on
`window` compiles, type-checks and does nothing — `PlayerPage` did exactly that,
and its button-feedback overlay and repeat/shuffle sync were dead for as long as
it lasted.

Reconnect is exponential — 1 s doubling to a 30 s cap, reset on a successful
open. `ConnectionLostScreen` waits three seconds before showing its overlay, so
a reconnect during a tab switch does not flash a full-page error.

Messages the app acts on: `audio_status`, `audio_config`, `sleep_timer_status`,
`rfid_scanned_learning`, `tag_not_found`, `system_alert`, `system_alert_cleared`,
`service_status`, `button_raw_event`, `button_action`, `repeat_mode`,
`shuffle_mode`.

The last three are the ones nobody in the browser asked for: someone pressed a
button on the box, or turned the rotary knob, or changed repeat from a second
browser session. They are the reason the event target exists at all.

### 5.3 Server state: two layers

React Query is configured globally (`staleTime` 5 min, 2 retries, refetch on
focus) but is used in only two files — `PlayerPage` and the `AudioConfigSync`
component in `App.tsx`. Everything else loads with `useState` + `useEffect` and
carries its own `loading`/`error` pair.

This is a real split, not a nuance: the same track list is fetched by
`MediaPage`, by `RfidPage` and again by the command palette, and none of the
three sees the other's copy. It is recorded here as the current state; the
consolidation is item C2 in [Redesign.md](Redesign.md).

### 5.4 API layer

`api/client.ts` is a single Axios instance with `baseURL: /api/v1`,
`withCredentials: true` and a 15-second default timeout. Two interceptors do the
work:

- **Retry.** Only `GET` and `HEAD` are ever repeated — network errors and server
  errors (5xx, 408) alike. Up to 3 attempts, exponential backoff 1 s → 10 s. A
  timeout, a dropped Wi-Fi link and a 502 all look identical from the client, so
  a repeated `POST` may well have reached the backend and been carried out; the
  method is the only thing that distinguishes a safe repeat from uploading the
  same file twice. `client.test.ts` pins this down.
- **Failure recording.** Every finally-failed request is written into the debug
  ring buffer (method, URL, status, duration) so the diagnostics export can
  show what the browser saw. Retries are not recorded individually.

The 15 seconds are enough for plain JSON, and wrong for everything else. Calls
that legitimately run longer take their value from the `TIMEOUT` table in the
same file:

| Value             |         | Used by                                                       |
| ----------------- | ------- | ------------------------------------------------------------- |
| `NONE`            | none    | `tracksApi.upload` — `onUploadProgress` is the sign of life, and a large file over Wi-Fi has no upper bound worth guessing. |
| `HOST_ACTION`     |  30 s   | Wi-Fi scan and connect, Bluetooth scan, factory reset, update check. The Host-Helper's Bluetooth scan alone runs 12 seconds. |
| `UPLOAD`          | 120 s   | Cover and logo uploads. Nginx cuts the connection at 120 s anyway. |
| `LONG_RUNNING`    | 180 s   | Backup download and restore, USB import, debug export.         |

A `401` calls a registered callback, which `AuthContext` uses to drop the
session and let `ProtectedRoute` show the password dialog again.

The web password must be at least eight characters (`MIN_PASSWORD_LENGTH` in
`utils/validators.ts`). It is the only lock in front of the media library, the
parent dashboard and maintenance — and maintenance holds the factory reset, the
OS update and the backup download with the whole database. The backend enforces
the same number in `routes_auth.py`; a limit that lives only in the frontend is
decoration. An existing shorter password keeps working for login, only setting a
new one is affected.

Errors are translated, never passed through. The backend sends a stable `code`
plus an English `detail` meant for logs; `translateApiError()` looks the code up
in the `errors` namespace and falls back to `errors:generic_error`. A raw
backend string never reaches the screen.

### 5.5 Diagnostics

`utils/debugRingBuffer.ts` keeps the last 100 client errors and the last 100
failed requests in memory. Uncaught errors and rejected promises are captured
globally, render crashes by `ErrorBoundary` — a React render crash never reaches
`window.onerror`, so it has to be recorded where it is caught.

None of this is persisted; closing the tab clears it. The export dialog is
reachable from three places on purpose: the settings page, the error boundary,
and the connection-lost overlay — the two screens where a user is most likely to
need it are exactly the two from which they can no longer navigate to the
settings.

### 5.6 i18n

Seven namespaces (`common`, `player`, `rfid`, `media`, `admin`, `errors`,
`setup`), fetched at runtime from `/locales/{lng}/{ns}.json`. Two mechanisms
guard against a broken cache, which is the failure mode that turns the whole UI
into raw key names:

- Every URL carries `?v=<BUILD_ID>`, a per-build identifier from
  `vite.config.ts`, so a corrupted entry cannot survive an update; the fetch
  additionally sends `cache: 'no-cache'`.
- A `failedLoading` event logs, records into the ring buffer, and retries that
  one namespace once after two seconds — i18next never retries on its own, so
  a single hiccup at startup would otherwise be permanent.

Language and namespace lists have one source each (`i18n/languages.ts`,
`i18n/namespaces.ts`). When the server reports `log_level: debug`, the fallback
is switched off after the first config call so missing keys show up as raw keys
instead of hiding behind English.

Two scripts guard the translations and both run in `package.json`:
`check-locales.mjs` compares de/en for missing keys, plural completeness and
keys no longer referenced; `check-i18n-calls.mjs` checks every static `t()` call
against the JSON files.

---

## 6. Responsive Layout

`useLayout()` is the single source for layout decisions. Three tiers, cut at
MUI's `sm` and `lg` so that `sx` breakpoints line up with the same edges:

| Tier    | Width       | Navigation           | Density              |
| ------- | ----------- | -------------------- | -------------------- |
| mobile  | < 600 px    | Bottom bar           | One column, full-screen sheets |
| tablet  | 600–1199 px | Icon rail (72 px)    | Two columns          |
| desktop | ≥ 1200 px   | Drawer (220 px)      | Three columns        |

The tablet tier exists because of one concrete device: on a 1024 px iPad in
portrait, a permanent 220 px drawer plus full desktop density left 804 px for a
three-column card grid. Two separate switch points used to sit in the code — the
navigation flipped at 900 px, density and dialogs at 600 px — and the band
between them belonged to neither layout.

Two derived flags carry most of the call sites: `isCompact` (anything below
desktop, for spacing) and `hasRoomForInlineControls` (tablet and up, for sort
and filter controls that would otherwise need a popover).

Three details matter beyond the breakpoints. `index.html` sets
`viewport-fit=cover`, so fixed elements must add `env(safe-area-inset-bottom)`
themselves — `Navigation.tsx` exports it as `SAFE_AREA_BOTTOM` and the mini
player and FAB offset against it. Selected navigation items use `primary.dark`,
not `.main`: white text needs 4.5:1 for WCAG AA and `.main` reaches only about
3.8:1 with the default orange. And the font-size setting scales the root
`<html>` size rather than MUI's `typography.fontSize`, so text grows while bar
heights and icons stay put.

---

## 7. Deployment

Defined in the root `docker-compose.yml` as the `webui` service. Image
`ghcr.io/opnek90/minabox-webui:${MINABOX_WEBUI_TAG}`; the service carries its own
version number (`docs/Versionierung.md`).

The Dockerfile is two-stage: `node:20-alpine` runs `npm ci` — from the
lockfile, so the same source cannot produce a different image four weeks later,
and without `--omit=dev`, because Vite and TypeScript live in `devDependencies`
and are what does the building — then
`npm run build:fast` (Vite only — `tsc` is deliberately skipped, it costs
minutes on an ARM runner and the CI check job below runs it instead), then the
resulting `dist/` is copied into `nginx:alpine-slim`. Version metadata is set as
OCI labels from build args at the end of the file, so a version change
invalidates only the last layers. The defaults are `0.0.0-dev`: a locally built
image must not pass itself off as a release.

**`alpine-slim`, not `alpine`.** The full image carries njs, XSLT, GeoIP and the
image filter — 92.8 MB against 21.8 MB — and none of it is used here. The whole
image goes from 97.7 MB to 24.5 MB. Two things had to be checked first, because
everything hangs on them: `alpine-slim` is still built
`--with-http_gzip_static_module`, so the pre-compressed files below keep being
served, and it has no `curl` at all.

That last point makes the health check part of the base image choice. It asks
`wget -q -O /dev/null http://127.0.0.1:80/health` — `wget` because BusyBox is
all there is, and `127.0.0.1` because BusyBox `wget` resolves `localhost` to
`::1` first and gives up when that is refused, while Nginx listens on IPv4 only.
`curl` used to paper over this by falling back. The same line stands in
`docker-compose.yml`, which overrides the Dockerfile's health check either way,
so the two must not drift apart. This is the one service in the stack that does
not use `curl` for its health check.

**Fonts.** `src/fonts.css` declares the four Roboto weights MUI uses (300, 400,
500, 700) as `latin` `woff2` only. The `@fontsource` entry points would pull
every subset — latin-ext, cyrillic, greek, vietnamese, math, symbols — as both
`.woff2` and `.woff`: 64 files for an interface that ships German and English.
Thanks to `unicode-range` the browser only ever downloaded what it needed, so
this was never a load-time problem, but it took `dist/` from 3.0 MB to 2.1 MB.
Media titles with eastern European names would want a second `latin-ext` block
here.

`depends_on` is deliberately asymmetric. The backend is **not** waited for —
Nginx resolves the name at request time (below), so the UI can come up first and
`ConnectionLostScreen` covers the gap. The hardware services *are* waited for
(`service_healthy`, `required: false`), because they have no equivalent
fallback: without the wait, features that talk to them failed visibly in the
first seconds after boot.

### 7.1 Nginx

| Location      | Behaviour                                                                 |
| ------------- | ------------------------------------------------------------------------- |
| `/`           | `try_files` with `index.html` fallback — SPA routing.                       |
| `/api/`       | Proxy to the backend. Forwards `Set-Cookie`, 120 s timeouts, 100 MB body.   |
| `/ws`         | Proxy with upgrade headers, 3600 s timeouts.                               |
| `/static/`    | Proxy (user files: logo, covers), `no-cache`. `^~` so the image regex below cannot claim it. |
| `/locales/`   | `no-cache` — revalidate against the ETag, cheap 304s.                       |
| `*.js/css/…`  | `public, max-age=31536000, immutable`. Vite content-hashes these names.      |
| `/index.html` | `no-store` — the entry point must never be cached.                          |
| `/health`     | Returns `healthy`.                                                          |

Three of these entries encode a bug that was fixed there.

**The resolver.** `resolver 127.0.0.11` plus a variable in `proxy_pass` forces
Nginx to resolve `backend` per request instead of once at config load. Without
it, a rebuilt backend container gets a new IP and Nginx keeps proxying to the
old one — permanent 502s until the WebUI container is restarted too.

**`proxy_pass_header Set-Cookie`.** Without it Nginx silently drops the
`Set-Cookie` response header from the backend, and login never delivers the
`minabox_session` cookie.

**`no-cache` on `/locales/`.** These URLs have no content hash, so they stay
identical across builds. With no explicit header, browsers fall back to
heuristic caching and serve a stale `admin.json` long after the file changed —
which looks exactly like "the translations are broken".

`gzip_static on` serves the `.gz` files that `vite-plugin-compression` produced
at build time, rather than compressing on every request; dynamic `gzip` remains
as the fallback for anything without a pre-built sibling.

**Security headers.** `X-Content-Type-Options: nosniff`, `X-Frame-Options:
SAMEORIGIN` and `Referrer-Policy: no-referrer` go out on every response, and
`server_tokens off` keeps the exact Nginx version out of the `Server` header and
off the error pages. The three headers live in `nginx/security-headers.conf` and
are included six times, not written once: Nginx does **not** inherit `add_header`
into a block that sets one of its own, so every location in the table above with
a `Cache-Control` header would silently have dropped them.

`Content-Security-Policy` is deliberately absent. MUI and Emotion write inline
styles at runtime, so a policy needs at least `style-src 'self' 'unsafe-inline'`,
and streams pull audio and cover art from arbitrary hosts. A wrong policy whites
out the entire interface with nothing in the server log to show for it, so it
belongs in its own change with a click-through, not bundled in with the rest.

### 7.2 Checks before the build

`.github/workflows/checks.yml` runs `tsc --noEmit`, `eslint src`, `vitest run`
and the two i18n guards on `ubuntu-latest` in about two minutes. It is wired in
twice: on every pull request, so a failure shows up before the merge, and via
`workflow_call` from `build-images.yml`, so a red run stops the push to GHCR.

It exists because the CI used to build images and nothing else. With `tsc`
skipped in the Dockerfile and no test run anywhere, a type error or a broken
test could travel all the way into the registry unnoticed — which is how a dead
`window` listener in `PlayerPage` survived as long as it did.

---

## 8. Dependencies

**Services:** the backend, and only the backend — REST at `/api/v1`, WebSocket
at `/ws`, both same-origin through the Nginx proxy in this container. There is
no direct call to the host-helper, to MQTT or to any hardware service.

**Runtime:** Nginx. The built app is static files; the container has no
environment variables of its own.

**Build:** Node 20 and npm. The dependency set is small on purpose — React,
MUI, React Router, React Query, Axios, i18next, dnd-kit and Fontsource Roboto.

---

## 9. Errors & Diagnostics

| Situation                    | What the user sees                                                      |
| ---------------------------- | ------------------------------------------------------------------------ |
| API error with a known code  | The translated text from the `errors` namespace.                          |
| API error, unknown code      | `errors:generic_error`. The English `detail` stays in the console.        |
| Network error / 5xx on a GET | Up to 3 retries with backoff before anything is shown.                    |
| `401`                        | Session dropped, password dialog reopens.                                 |
| WebSocket down > 3 s         | Full-page overlay with a button for the diagnostics export.               |
| Render crash                 | `ErrorBoundary` with retry and diagnostics export; recorded in the ring buffer. |
| Missing translation          | Falls back to English — unless `log_level: debug`, then the raw key shows. |

Console output is prefixed `[WebUI]` and limited to `console.error`/`warn` —
there is no `console.log` in the shipped code.

---

## 10. Related Documents

- [Component-Capabilities.md](Component-Capabilities.md) — how optional
  components are detected and hidden.
- [Setup-Wizard.md](Setup-Wizard.md) — the first-run flow.
- [Settings-Reorganisation.md](Settings-Reorganisation.md) — why the settings
  are cut the way they are.
- [Redesign.md](Redesign.md) — the open review items, including the data-layer
  consolidation named in section 5.3.
