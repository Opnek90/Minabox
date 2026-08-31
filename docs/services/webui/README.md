# WebUI Service

The browser front end: a static React single-page application, built once and
served by Nginx, that turns the backend's REST API and WebSocket feed into the
surface a family actually operates — a player, a card manager, a media library,
a parent dashboard and a settings area.

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-webui` |
| Source | `services/webui-service/src/` |
| Version | `services/webui-service/VERSION` |
| Compose service | `webui` (no profile — always on) |
| Runtime | Nginx `alpine-slim` serving static files; built with Node 20 + Vite 5 |
| Speaks | the backend only: REST `/api/v1`, WebSocket `/ws`, same origin through this container's proxy |
| Needs | the backend at request time; nothing else |

## 1. Purpose & Responsibility

- **One interface for two very different users.** A child taps play and volume;
  a parent sets time limits, imports media and updates the box. The player page
  stays deliberately sparse, everything else lives one navigation step away.
- **Immediate feedback.** Playback state, RFID scans and system alerts arrive
  over the WebSocket, not by polling — the box and the browser must never
  disagree about what is playing.
- **Usable on the device at hand.** Phone, tablet and desktop get three layouts
  from the same components (3.4), and the German/English translation is loaded
  at runtime, not compiled in.
- **Never a dead end.** A missing optional component hides its menu entry
  instead of offering a page that does nothing; a lost connection produces an
  overlay with a diagnostics export rather than a blank screen.

It deliberately does **not**:

| Not this service | Owned by |
| --- | --- |
| Any knowledge of MQTT, the database or the hardware | backend |
| Talking to host-helper, audio, rfid, led or display directly | backend — the WebUI has exactly one host |
| Server-side state | nothing beyond the browser's `localStorage` |
| Token handling | the backend's session cookie; the app only sends `withCredentials` |

## 2. File & Folder Structure

```
services/webui-service/
├── Dockerfile                 node:20-alpine (build) → nginx:alpine-slim (serve)
├── nginx/
│   ├── nginx.conf             SPA fallback, /api + /ws proxy, caching
│   └── security-headers.conf  included per location; see 6.2
├── vite.config.ts             PWA, gzip, manual chunks, BUILD_ID
├── VERSION                    service version, single source
├── scripts/
│   ├── check-locales.mjs      de/en in sync, plurals complete, dead keys
│   └── check-i18n-calls.mjs   every static t() key exists in the JSON
├── public/locales/{de,en}/    common, player, rfid, media, admin, errors, setup
└── src/
    ├── api/
    │   ├── client.ts          ** the only module that talks to the network **
    │   │                      — Axios instance, retry, timeouts, 401 hook,
    │   │                      debug buffer
    │   ├── auth.ts  capabilities.ts  config.ts  system.ts
    │   ├── audio.ts  tags.ts  tracks.ts  playlists.ts
    │   └── streams.ts  podcasts.ts  scanHistory.ts  stats.ts
    ├── contexts/              six providers, see 3.1
    ├── hooks/                 useAudioStatus, useLayout, useSetupStatus, …
    ├── pages/                 one per route, all lazy-loaded
    ├── components/
    │   ├── common/            shell: Header, Navigation, PageShell, dialogs
    │   ├── ui/                ActionButton, VolumeSlider
    │   ├── player/  rfid/  media/  dashboard/  setup/
    │   └── admin/             settings panels + ConfigForm/ sub-forms
    ├── config/settingsIndex.ts  ** the settings tree as data, not JSX **
    ├── types/api.ts           mirrors the backend Pydantic schemas
    ├── i18n/                  init, language list, namespaces, debug mode
    ├── fonts.css              Roboto, latin subset, woff2 only
    └── utils/                 apiError, formatTime, validators, debugRingBuffer
```

Two files deserve naming because everything else hangs off them.
`config/settingsIndex.ts` describes the settings area as plain data — groups,
sections, the i18n keys of the fields inside them, and which optional component
a section depends on. `AdminPage` renders forms against it and the command
palette searches the same structure, so there is exactly one place where the
settings tree is cut. `api/client.ts` is the only module that talks to the
network; every `api/*.ts` sibling goes through it and therefore inherits the
retry, the 401 handling and the debug-buffer recording for free.

### 2.1 Technology stack

| Layer | Choice | Note |
| --- | --- | --- |
| Framework | React 18 + TypeScript 5 (`strict`) | `noUnusedLocals` and `noUnusedParameters` are on |
| Build | Vite 5 | `build:fast` (Vite only) is what the Dockerfile runs |
| UI | MUI v5 + Emotion | deep icon imports only, so the icon set tree-shakes |
| Routing | React Router v6 | pages are `React.lazy` — one chunk per page |
| Server state | React Query 5 **and** local `useState` | two layers in parallel; see 3.3 |
| HTTP | Axios, `baseURL: /api/v1`, `withCredentials` | session cookie, no token handling in the app |
| Realtime | native `WebSocket` at `/ws` | exponential reconnect, 1 s → 30 s |
| i18n | i18next + `i18next-http-backend` | 7 namespaces fetched at runtime from `/locales/` |
| PWA | `vite-plugin-pwa` (`autoUpdate`) | manifest, icons, precached shell |
| Compression | `vite-plugin-compression` → `gzip_static` | pre-built `.gz`, so the Pi does not compress per request |
| Web server | Nginx (`alpine-slim`) | SPA fallback, reverse proxy, caching, security headers |
| Tests | Vitest + Testing Library | regression pins, not coverage |

## 3. Runtime Flow

### 3.1 Provider stack

```text
QueryClientProvider → BrowserRouter → ThemeContextProvider → ThemedApp
  └ ThemeProvider (MUI) → AuthProvider → WebSocketProvider → App
      └ ToastProvider → UserPrefsProvider → Routes
          └ CapabilitiesProvider → MainLayout   (not on /kiosk)
```

| Context | Holds | Persistence |
| --- | --- | --- |
| `ThemeContext` | light/dark, accent preset, font scale | `localStorage`, applied as CSS custom properties on `<html>` |
| `AuthContext` | whether auth is on, which paths are gated, session state | cookie (backend), config fetched at start |
| `WebSocketContext` | connection, last message, cached audio status | memory |
| `ToastContext` | notification stack (max 3 visible) | memory |
| `UserPrefsContext` | view mode, sort, filter, page size per list | `localStorage` |
| `CapabilitiesContext` | which optional components exist | `localStorage` cache + refresh |

**Two of these fail *open* on purpose.** `CapabilitiesContext` treats everything
as installed while loading and when the request fails, and it reads its last
known answer from `localStorage` synchronously at start — a network hiccup must
never make a feature disappear, and a returning user must not watch the menu
rearrange itself. `useSetupStatus` takes the same line in reverse: if the
backend cannot be reached it decides the setup wizard is *not* needed, because a
false "please set up your box" is worse than no hint at all.

### 3.2 WebSocket

`WebSocketContext` holds a single connection for the whole app. Every message is
pushed twice: into React state (`lastMessage`, plus the cached shapes
`cachedAudioStatus` and `sleepTimerStatus`) and onto a module-level
`EventTarget`. The event target exists so a component can subscribe to one
message type without re-rendering on every unrelated message;
**`useWebSocketEvent` is the hook for that, and the only correct way to
subscribe.** Listening on `window` compiles, type-checks and does nothing —
`PlayerPage` did exactly that, and its button-feedback overlay and
repeat/shuffle sync were dead for as long as it lasted.

Reconnect is exponential — 1 s doubling to a 30 s cap, reset on a successful
open. `ConnectionLostScreen` waits three seconds before showing its overlay, so
a reconnect during a tab switch does not flash a full-page error.

Messages the app acts on: `audio_status`, `audio_config`, `sleep_timer_status`,
`rfid_scanned_learning`, `tag_not_found`, `system_alert`,
`system_alert_cleared`, `service_status`, `button_raw_event`, `button_action`,
`repeat_mode`, `shuffle_mode`.

The last three are the ones nobody in the browser asked for: someone pressed a
button on the box, or turned the rotary knob, or changed repeat from a second
browser session. They are the reason the event target exists at all.

### 3.3 Server state: two layers

React Query is configured globally (`staleTime` 5 min, 2 retries, refetch on
focus) but used in only two files — `PlayerPage` and the `AudioConfigSync`
component in `App.tsx`. Everything else loads with `useState` + `useEffect` and
carries its own `loading`/`error` pair.

**This is a real split, not a nuance:** the same track list is fetched by
`MediaPage`, by `RfidPage` and again by the command palette, and none of the
three sees the other's copy. It is recorded here as the current state; folding
these onto one shared cache is still open.

### 3.4 Responsive layout

`useLayout()` is the single source for layout decisions. Three tiers, cut at
MUI's `sm` and `lg` so `sx` breakpoints line up with the same edges:

| Tier | Width | Navigation | Density |
| --- | --- | --- | --- |
| mobile | < 600 px | bottom bar | one column, full-screen sheets |
| tablet | 600–1199 px | icon rail (72 px) | two columns |
| desktop | ≥ 1200 px | drawer (220 px) | three columns |

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
themselves — `Navigation.tsx` exports it as `SAFE_AREA_BOTTOM`. Selected
navigation items use `primary.dark`, not `.main`: white text needs 4.5:1 for
WCAG AA and `.main` reaches only about 3.8:1 with the default orange. And the
font-size setting scales the root `<html>` size rather than MUI's
`typography.fontSize`, so text grows while bar heights and icons stay put.

### 3.5 i18n

Seven namespaces (`common`, `player`, `rfid`, `media`, `admin`, `errors`,
`setup`), fetched at runtime from `/locales/{lng}/{ns}.json`. Two mechanisms
guard against a broken cache, which is the failure mode that turns the whole UI
into raw key names:

- Every URL carries `?v=<BUILD_ID>`, a per-build identifier from
  `vite.config.ts`, so a corrupted entry cannot survive an update; the fetch
  additionally sends `cache: 'no-cache'`.
- A `failedLoading` event logs, records into the ring buffer, and retries that
  one namespace once after two seconds — i18next never retries on its own, so a
  single hiccup at startup would otherwise be permanent.

Language and namespace lists have one source each (`i18n/languages.ts`,
`i18n/namespaces.ts`). When the server reports `log_level: debug`, the fallback
is switched off after the first config call so missing keys show up as raw keys
instead of hiding behind English.

### 3.6 Diagnostics

`utils/debugRingBuffer.ts` keeps the last 100 client errors and the last 100
failed requests in memory. Uncaught errors and rejected promises are captured
globally, render crashes by `ErrorBoundary` — a React render crash never reaches
`window.onerror`, so it has to be recorded where it is caught.

None of this is persisted; closing the tab clears it. The export dialog is
reachable from three places on purpose: the settings page, the error boundary,
and the connection-lost overlay — the two screens where a user is most likely to
need it are exactly the two from which they can no longer navigate to the
settings.

## 4. Public Interfaces

### 4.1 Routes

| Route | Page | Notes |
| --- | --- | --- |
| `/player` | `PlayerPage` | default route. Cover, transport, volume; everything else in an overflow menu |
| `/rfid` | `RfidPage` | card list, learn mode, assignment. Hidden entirely without a reader |
| `/media` | `MediaPage` | five tabs: recent, playlists, tracks, streams, podcasts |
| `/dashboard` | `DashboardPage` | parent view: overview, rules, statistics, scan history |
| `/admin` | `AdminPage` | settings, grouped and searchable |
| `/setup` | `SetupWizardPage` | first-run wizard. Deliberately **not** behind `ProtectedRoute` |
| `/kiosk` | `KioskPage` | full-screen player, outside the main layout and outside `CapabilitiesProvider` |

Everything else redirects to `/player`, including `/rfid` when no reader is
installed — a deep link must not land on a page whose central actions do
nothing.

The setup wizard is the one route without a password gate, and it has to be:
step 2 is where the password is set, so gating it would lock the user out of the
flow that creates the credential.

**Player.** `useAudioStatus` extrapolates the playback position locally: it
takes the last `audio_status` message and adds the elapsed time, then ticks once
a second while playing. The progress bar therefore moves smoothly without a
single extra request, and a page opened mid-track shows the right position on
first render rather than jumping when the next message lands. The main card is
intentionally short — state chip, cover, progress, transport, volume — because
the person using this page most often is a child who wants two buttons, not
nine.

**RFID.** Learn mode is a three-step conversation with the box: the page enables
it via `POST /rfid/learning-mode`, the reader reports the card as
`rfid_scanned_learning` over the WebSocket, and the dialog that opens writes the
assignment. Closing the dialog turns learn mode back off — leaving it on would
make the next card scanned anywhere in the house open an assignment dialog. A
scan outside learn mode surfaces globally: `RfidScanDrawer` sits in the app
shell.

**Media.** Tracks, streams and podcasts each have their own folder tree, and all
three lists share one shape: search field, view toggle, sort, filter,
pagination. Deleting a media item first asks the backend which cards point at it
and, if there are any, offers to clear those assignments in the same step —
deleting only the media leaves a card pointing at a track that no longer exists.

**Dashboard and settings.** The settings page is cut by everyday question
("Playback", "Sound", "Appearance") rather than by where a value happens to live
in the backend; everything technical collects under "Advanced". The search field
renders a jump list, not the expanded forms: a two-letter query matches almost
every section, and mounting eleven panels at once would fire eleven API calls on
a Raspberry Pi. Sections that hang off an optional component carry
`requiresFeature` in `settingsIndex.ts` and disappear — along with a group that
becomes empty — when `GET /system/capabilities` says the component is not
installed.

### 4.2 The API layer

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
  ring buffer (method, URL, status, duration) so the diagnostics export can show
  what the browser saw. Retries are not recorded individually.

The 15 seconds are enough for plain JSON and wrong for everything else. Calls
that legitimately run longer take their value from the `TIMEOUT` table in the
same file:

| Value | | Used by |
| --- | --- | --- |
| `NONE` | none | `tracksApi.upload` — `onUploadProgress` is the sign of life, and a large file over Wi-Fi has no upper bound worth guessing |
| `HOST_ACTION` | 30 s | Wi-Fi scan and connect, Bluetooth scan, factory reset, update check. The host-helper's Bluetooth scan alone runs 12 seconds |
| `UPLOAD` | 120 s | cover and logo uploads. Nginx cuts the connection at 120 s anyway |
| `LONG_RUNNING` | 180 s | backup download and restore, USB import, debug export |

A `401` calls a registered callback, which `AuthContext` uses to drop the
session and let `ProtectedRoute` show the password dialog again.

The web password must be at least eight characters (`MIN_PASSWORD_LENGTH` in
`utils/validators.ts`). It is the only lock in front of the media library, the
parent dashboard and maintenance — and maintenance holds the factory reset, the
OS update and the backup download with the whole database. The backend enforces
the same number in `routes_auth.py`; a limit that lives only in the frontend is
decoration. An existing shorter password keeps working for login; only setting a
new one is affected.

**Errors are translated, never passed through.** The backend sends a stable
`code` plus an English `detail` meant for logs; `translateApiError()` looks the
code up in the `errors` namespace and falls back to `errors:generic_error`. A
raw backend string never reaches the screen.

## 5. Configuration

The built app is static files: **the container has no environment variables of
its own.** Everything configurable lives in the backend and arrives over the
API — the theme, the language, whether auth is on, which optional components
exist.

What the browser keeps in `localStorage`: theme and accent, font scale, per-list
view mode/sort/filter/page size, and the last known capability answer. None of
it is authoritative; all of it is a convenience the app can lose without harm.

Build-time configuration is `vite.config.ts` (PWA manifest, manual chunks,
`BUILD_ID`) and `nginx/nginx.conf`.

## 6. Dependencies

**Services:** the backend, and only the backend — REST at `/api/v1`, WebSocket
at `/ws`, both same-origin through the Nginx proxy in this container. There is
no direct call to the host-helper, to MQTT or to any hardware service.

**Runtime:** Nginx `alpine-slim`.

**Build:** Node 20 and npm. The dependency set is small on purpose — React, MUI,
React Router, React Query, Axios, i18next, dnd-kit and Fontsource Roboto.

### 6.1 Image and compose

The Dockerfile is two-stage: `node:20-alpine` runs `npm ci` — from the lockfile,
so the same source cannot produce a different image four weeks later, and
without `--omit=dev`, because Vite and TypeScript live in `devDependencies` and
are what does the building — then `npm run build:fast` (Vite only; `tsc` is
deliberately skipped, it costs minutes on an ARM runner and the CI check job
runs it instead), then `dist/` is copied into `nginx:alpine-slim`.

**`alpine-slim`, not `alpine`.** The full image carries njs, XSLT, GeoIP and the
image filter — 92.8 MB against 21.8 MB — and none of it is used here. The whole
image goes from 97.7 MB to 24.5 MB. Two things had to be checked first, because
everything hangs on them: `alpine-slim` is still built
`--with-http_gzip_static_module`, so the pre-compressed files keep being served,
and it has no `curl` at all.

That last point makes the health check part of the base image choice. It asks
`wget -q -O /dev/null http://127.0.0.1:80/health` — `wget` because BusyBox is
all there is, and `127.0.0.1` because BusyBox `wget` resolves `localhost` to
`::1` first and gives up when that is refused, while Nginx listens on IPv4 only.
The same line stands in `docker-compose.yml`, which overrides the Dockerfile's
health check either way, so **the two must not drift apart**. This is the one
service in the stack that does not use `curl` for its health check.

**Fonts.** `src/fonts.css` declares the four Roboto weights MUI uses (300, 400,
500, 700) as `latin` `woff2` only. The `@fontsource` entry points would pull
every subset — latin-ext, cyrillic, greek, vietnamese, math, symbols — as both
`.woff2` and `.woff`: 64 files for an interface that ships German and English.
Thanks to `unicode-range` the browser only ever downloaded what it needed, so
this was never a load-time problem, but it took `dist/` from 3.0 MB to 2.1 MB.
Media titles with eastern European names would want a second `latin-ext` block
here.

`depends_on` is deliberately asymmetric. The backend is **not** waited for —
Nginx resolves the name at request time, so the UI can come up first and
`ConnectionLostScreen` covers the gap. The hardware services *are* waited for
(`service_healthy`, `required: false`), because they have no equivalent
fallback: without the wait, features that talk to them failed visibly in the
first seconds after boot.

### 6.2 Nginx

| Location | Behaviour |
| --- | --- |
| `/` | `try_files` with `index.html` fallback — SPA routing |
| `/api/` | proxy to the backend. Forwards `Set-Cookie`, 120 s timeouts, 100 MB body |
| `/ws` | proxy with upgrade headers, 3600 s timeouts |
| `/static/` | proxy (user files: logo, covers), `no-cache`. `^~` so the image regex cannot claim it |
| `/locales/` | `no-cache` — revalidate against the ETag, cheap 304s |
| `*.js/css/…` | `public, max-age=31536000, immutable`. Vite content-hashes these names |
| `/index.html` | `no-store` — the entry point must never be cached |
| `/health` | returns `healthy` |

Three of these entries encode a bug that was fixed there.

**The resolver.** `resolver 127.0.0.11` plus a variable in `proxy_pass` forces
Nginx to resolve `backend` per request instead of once at config load. Without
it, a rebuilt backend container gets a new IP and Nginx keeps proxying to the old
one — permanent 502s until the WebUI container is restarted too.

**`proxy_pass_header Set-Cookie`.** Without it Nginx silently drops the
`Set-Cookie` response header from the backend, and login never delivers the
`minabox_session` cookie.

**`no-cache` on `/locales/`.** These URLs have no content hash, so they stay
identical across builds. With no explicit header, browsers fall back to
heuristic caching and serve a stale `admin.json` long after the file changed —
which looks exactly like "the translations are broken".

`gzip_static on` serves the `.gz` files that `vite-plugin-compression` produced
at build time; dynamic `gzip` remains as the fallback.

**Security headers.** `X-Content-Type-Options: nosniff`,
`X-Frame-Options: SAMEORIGIN` and `Referrer-Policy: no-referrer` go out on every
response, and `server_tokens off` keeps the Nginx version out of the `Server`
header. The three headers live in `nginx/security-headers.conf` and are included
**six times, not written once**: Nginx does not inherit `add_header` into a
block that sets one of its own, so every location above with a `Cache-Control`
header would silently have dropped them.

`Content-Security-Policy` is deliberately absent. MUI and Emotion write inline
styles at runtime, so a policy needs at least
`style-src 'self' 'unsafe-inline'`, and streams pull audio and cover art from
arbitrary hosts. A wrong policy whites out the entire interface with nothing in
the server log to show for it, so it belongs in its own change with a
click-through.

## 7. Errors, Health & Logging

| Situation | What the user sees |
| --- | --- |
| API error with a known code | the translated text from the `errors` namespace |
| API error, unknown code | `errors:generic_error`. The English `detail` stays in the console |
| Network error / 5xx on a GET | up to 3 retries with backoff before anything is shown |
| `401` | session dropped, password dialog reopens |
| WebSocket down > 3 s | full-page overlay with a button for the diagnostics export |
| Render crash | `ErrorBoundary` with retry and diagnostics export; recorded in the ring buffer |
| Missing translation | falls back to English — unless `log_level: debug`, then the raw key shows |

`GET /health` on the Nginx side returns `healthy` and says nothing about the
backend: this container is up as soon as it can serve files, and that is the
truth it should report.

Console output is prefixed `[WebUI]` and limited to `console.error`/`warn` —
there is no `console.log` in the shipped code.

## 8. Development & Tests

```bash
cd services/webui-service && npm install
```

```bash
cd services/webui-service && npm run dev
```

The dev server proxies `/api/` and `/ws` to `localhost:8080`, so it works
against a backend running on the box or locally. Open `http://localhost:5173`.

**Before any commit that touches this service** — the Dockerfile skips `tsc`, so
this is the only place type errors are caught:

```bash
cd services/webui-service && npx tsc --noEmit
```

```bash
cd services/webui-service && npm run lint && npm run test && npm run check:locales && npm run check:i18n-calls
```

| Test file | Pins |
| --- | --- |
| `api/client.test.ts` | the retry rule: GET/HEAD only, backoff, what is recorded |
| `contexts/CapabilitiesContext.test.tsx` | failing open, and the synchronous `localStorage` read |
| `components/common/Navigation.test.tsx` | which entries appear for which capabilities |
| `components/media/MediaFab.test.tsx`, `MediaImportDialog.test.tsx` | the import flow and its confirmation |
| `components/admin/SystemMaintenanceSection.test.tsx` | the maintenance panel's destructive actions |
| `hooks/useGeneralConfig.test.tsx` | config loading and its defaults |
| `i18n/debugMode.test.ts` | the fallback switch-off under `log_level: debug` |

These are regression pins, not coverage — each one exists because something
broke there once.

`.github/workflows/checks.yml` runs `tsc --noEmit`, `eslint src`, `vitest run`
and the two i18n guards on `ubuntu-latest` in about two minutes. It is wired in
twice: on every pull request, and via `workflow_call` from `build-images.yml` so
a red run stops the push to GHCR. It exists because the CI used to build images
and nothing else — which is how a dead `window` listener in `PlayerPage`
survived as long as it did.

```bash
./scripts/build-local.sh webui
```

## 9. Extending the Service

### Common changes

| I want to … | Start in | Also touch |
| --- | --- | --- |
| add a page | `pages/` + a lazy route in `App.tsx` | `Navigation.tsx`, the route table in 4.1, a locale namespace if it needs one |
| add a settings section | `config/settingsIndex.ts` (data, not JSX) | the panel under `components/admin/`, both locale files, `requiresFeature` if it depends on an optional component |
| call a new backend endpoint | a module under `api/` — **always through `client.ts`** | `types/api.ts` to mirror the backend schema; a `TIMEOUT` entry if it runs long |
| react to a new WebSocket message | `useWebSocketEvent` in the component | the message list in 3.2; the backend must send it. **Never `window.addEventListener`** |
| add a translated string | both `public/locales/de/` and `en/` | `npm run check:locales && npm run check:i18n-calls` — the guards fail on a missing pair |
| change a layout breakpoint | `hooks/useLayout.ts` only | nothing else — every call site reads it from there |
| add an error code | the `errors` namespace in both locales | the backend must emit the same `code`; unknown codes fall back to `generic_error` |
| change caching or proxying | `nginx/nginx.conf` | re-check the `add_header` inheritance trap in 6.2 |
| add a font weight or subset | `src/fonts.css` | measure `dist/` — this is where 900 KB came from |

### Invariants

- **`api/client.ts` is the only module that touches the network.** Retry, 401
  handling and failure recording all live there; a stray `fetch` silently opts
  out of all three.
- **Only `GET` and `HEAD` are retried.** A repeated `POST` may have already
  been carried out.
- **Subscribe with `useWebSocketEvent`, never on `window`.** The latter compiles
  and does nothing.
- **A raw backend string never reaches the screen.** Every error goes through
  `translateApiError()`.
- **`settingsIndex.ts` stays the one place the settings tree is cut.** The
  command palette searches the same structure the page renders.
- **Capabilities fail open.** A network hiccup must never make a feature
  disappear.
- **`/setup` stays outside `ProtectedRoute`.** It is where the password is set.
- **The security headers stay included in every location block.** Nginx does not
  inherit them.
- **`tsc --noEmit` must pass before a commit.** The image build skips it.
- **The health-check line in the Dockerfile and in `docker-compose.yml` must
  stay identical.** There is no `curl` in this image to paper over a difference.

## 10. Related Documents

- [`services/webui-service/README.md`](../../../services/webui-service/README.md) — the short signpost next to the code
- [Setup-Wizard.md](Setup-Wizard.md) — the first-run flow
- [`docs/services/README.md`](../README.md) — all services at a glance
- [`docs/services/_TEMPLATE.md`](../_TEMPLATE.md) — the outline this document follows
- [`docs/services/backend/README.md`](../backend/README.md) — the only host this app talks to: the REST API, the WebSocket feed and the error codes
