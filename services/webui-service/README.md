# WebUI Service

The browser front end: a static React SPA served by Nginx, which also proxies
`/api/` and `/ws` to the backend. It talks to the backend and nothing else — no
MQTT, no database, no hardware.

**Full documentation: [docs/services/webui/](../../docs/services/webui/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-webui` |
| Version | see `VERSION` |
| Compose | `webui` (always on) |
| Interfaces | serves the SPA on `80`; proxies `/api/v1` and `/ws` to the backend; `GET /health` |
| Config | none at runtime — the container has no environment variables. Build config in `vite.config.ts` and `nginx/nginx.conf` |

## Development

```bash
cd services/webui-service && npm install && npm run dev
```

The dev server proxies `/api/` and `/ws` to `localhost:8080`. Open
`http://localhost:5173`.

**Before every commit** — the Dockerfile skips `tsc`, so this is the only place
type errors are caught:

```bash
cd services/webui-service && npx tsc --noEmit
```

```bash
cd services/webui-service && npm run lint && npm run test && npm run check:locales && npm run check:i18n-calls
```

## Where to make changes

- `src/api/client.ts` — the only module that talks to the network: retry, the
  timeout table, the 401 hook, the debug ring buffer. Every `api/*.ts` sibling
  goes through it.
- `src/config/settingsIndex.ts` — the settings tree as data. The admin page
  renders it and the command palette searches it.
- `src/contexts/WebSocketContext.tsx` — the single connection. Subscribe with
  `useWebSocketEvent`; a `window` listener compiles and does nothing.
- `src/hooks/useLayout.ts` — the one source for mobile/tablet/desktop.
- `public/locales/{de,en}/` — both languages, kept in sync by the two check
  scripts.
- `nginx/nginx.conf` — SPA fallback, proxying, caching, security headers.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
