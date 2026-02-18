# Minabox WebUI Service

React/TypeScript web interface for the Minabox audio player. Served via Nginx in Docker, proxying API and WebSocket connections to the Backend Service.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build Tool | Vite 5 |
| UI Library | MUI v5 (Material-UI) |
| Routing | React Router v6 |
| HTTP Client | Axios |
| WebSocket | Native WebSocket API |
| i18n | i18next + react-i18next |
| Web Server | Nginx (Alpine) |
| Container | Docker (multi-stage build) |

## Features

### Player Page (`/player`)
- Real-time audio status via WebSocket
- Play / Pause / Stop / Next / Previous controls
- Progress bar with time display
- Volume slider (clamped to `max_volume` from audio config)
- Playlist info (track X of Y)

### RFID Tags Page (`/rfid`)
- List all RFID tags with content assignments
- Search and filter
- Learn Mode: scan new tag → assign playlist or track
- Edit and delete existing tags

### Media Library (`/media`)
- **Playlists**: create, edit, delete
- **Tracks**: upload audio files (MP3, OGG, FLAC, WAV, M4A) or add stream URLs

### Admin / Settings (`/admin`)
- System status overview (all services)
- General settings (language: DE/EN)
- Audio configuration (device, volume limits)
- LED configuration (view and delete)
- Button configuration (view and delete)
- RFID configuration (reader type, interface, intervals)

## Project Structure

```
webui-service/
├── src/
│   ├── api/              # Axios API clients (tags, playlists, tracks, audio, config, system)
│   ├── components/       # Reusable React components
│   │   ├── common/       # Header, Navigation, LoadingSpinner, ErrorBoundary
│   │   ├── player/       # PlaybackControls, VolumeControl, ProgressBar, TrackInfo
│   │   ├── rfid/         # TagList, TagCard, TagEditDialog, LearnModeButton
│   │   ├── media/        # PlaylistList, TrackList, UploadDialog, StreamDialog
│   │   └── admin/        # SystemStatus, ServiceStatus, ConfigForm
│   ├── contexts/         # WebSocketContext (with auto-reconnect)
│   ├── hooks/            # useAudioStatus, useApi, useAsyncAction
│   ├── pages/            # PlayerPage, RfidPage, MediaPage, AdminPage
│   ├── types/            # TypeScript interfaces (mirrors backend Pydantic schemas)
│   ├── utils/            # formatTime, validators
│   ├── App.tsx           # Router, layout (Header + Sidebar + Main)
│   ├── main.tsx          # Entry point, MUI Theme, Providers
│   └── i18n.ts           # i18next configuration
├── public/
│   └── locales/          # Translation files (DE, EN)
│       ├── de/           # common, player, rfid, media, admin, errors
│       └── en/           # common, player, rfid, media, admin, errors
├── nginx/
│   └── nginx.conf        # SPA routing + /api/ + /ws proxy
├── Dockerfile            # Multi-stage: node:20-alpine → nginx:alpine
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Local Development

```bash
# Install dependencies
cd services/webui-service
npm install

# Start dev server (proxies /api/ and /ws to localhost:8080)
npm run dev
# Open http://localhost:5173

# Lint
npm run lint

# Build for production
npm run build
```

The dev server proxies `/api/` to `http://localhost:8080` and `/ws` to `ws://localhost:8080`, so the backend must be running locally or via Docker.

## Docker Build

The service is built automatically via the root `docker-compose.yml`:

```bash
# Build and start (uses build:fast in Dockerfile for quicker rebuilds on Raspberry Pi)
docker compose up -d --build webui

# View logs
docker compose logs -f webui
```

**Faster rebuilds:** The Dockerfile uses `npm run build:fast` (Vite only, no `tsc`) so image builds finish much faster during development. Type checking is not run in the container; run `npm run build:check` or `npm run build` locally before committing. For production images you can switch the Dockerfile back to `npm run build`. BuildKit cache for `npm ci` is used when available (`DOCKER_BUILDKIT=1` is default in recent Docker).

## Environment Variables

The WebUI service itself has no environment variables – it is a static build served by Nginx. Backend URL and WebSocket URL are configured via the Nginx reverse proxy.

## Nginx Configuration

| Path | Target |
|---|---|
| `/` | SPA (`index.html`) |
| `/api/*` | `http://backend:8080` |
| `/ws` | `ws://backend:8080/ws` |
| `/health` | Nginx health check (returns 200) |

Static assets (JS, CSS) are cached for 1 year via `Cache-Control: immutable`. `index.html` is never cached.

## WebSocket

The `WebSocketContext` connects to `/ws` and automatically reconnects with exponential backoff (1s → 2s → 4s → ... → 30s max) on disconnect.

WebSocket message types handled:
- `audio_status` → updates PlayerPage in real time
- `rfid_scanned_learning` → opens tag assignment dialog in RfidPage
- `service_status` → updates AdminPage system status

## i18n

Supported languages: **Deutsch (de)** and **English (en)**.

Language preference is stored in `localStorage` under key `minabox-language`. Default is German.

To switch language: Admin → General → Language dropdown.
