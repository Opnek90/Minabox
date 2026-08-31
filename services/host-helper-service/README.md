# Host-Helper Service

The only service allowed to act on the host itself: reboot, WiFi, static IP,
hostname, USB import, backup, updates, Bluetooth, container logs. Every action
is a named, validated route — there is no generic "run this command" endpoint.
The backend is its only caller; the WebUI never talks to it directly.

**Full documentation: [docs/services/host-helper/](../../docs/services/host-helper/README.md)**

| | |
| --- | --- |
| Image | `ghcr.io/opnek90/minabox-host-helper` |
| Version | see `VERSION` |
| Compose | `host-helper` (always on) |
| Interfaces | HTTP on `8000`, **not published** — compose network only. 48 routes, all requiring `X-Api-Key` except `GET /health` |
| Config | environment only; no config file |

**This container runs as root with the host root mounted read-write**
(`pid: host`, `SYS_ADMIN`, `SYS_PTRACE`, the Docker socket). The shared secret
in `X-Api-Key` is the only thing between a caller and full control of the box.
Read section 4.1 of the architecture document before changing anything here.

## Tests

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest services/host-helper-service/tests -q
```

The service itself cannot run off the box — almost every route needs `nsenter`,
a host root or the Docker socket. The tests cover the pure logic: allowlists,
`.env` rewriting, `nmcli` parsing, the watchdog, the audio repair.

## Where to make changes

- `src/host_helper/api/routes/` — one module per domain; new routes are
  registered in `routes/__init__.py`.
- `src/host_helper/api/routes/deps.py` — the only module the others import
  from: config, the API key check, host root and tool lookups, `nsenter`,
  compose, the Docker client.
- `src/host_helper/network_ops.py` — the `nmcli` plumbing, shared by the route
  module and the watchdog.
- `src/host_helper/netwatch.py` — the connectivity watchdog that raises the
  fallback hotspot.
- `src/host_helper/config.py` — the path allowlist and every environment value.

Section 9 of the architecture document maps common changes to files and lists
the invariants a change must not break.
