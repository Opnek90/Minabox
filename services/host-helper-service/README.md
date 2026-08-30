# Host-Helper Service

Internal service for host-level actions (moving files, network and WiFi,
backup, updates, container logs). Called over HTTP by the backend only and
never exposed outside the compose network.

- **Architecture:** [docs/services/host-helper/](../../docs/services/host-helper/README.md)
- **Stack:** part of `docker compose` in the repository root.
