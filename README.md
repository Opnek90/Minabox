# Minabox

Phoniebox-/Jukebox-System mit RFID, Audio, WebUI und optionaler Hardware (LED, Buttons, Display).

## Schnellstart

```bash
cp .env.example .env   # anpassen: MQTT_BROKER, MINABOX_DEVICE_ID, etc.
docker compose up -d
```

- **Deployment & Installation:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Entwicklung & Struktur:** [docs/Framework.md](docs/Framework.md), [docs/DEVELOPMENT_INSTRUCTIONS.md](docs/DEVELOPMENT_INSTRUCTIONS.md)
- **Dev-Tools:** `./scripts/dev-tools.sh` (format, check, install, test, venv)

## Wichtige Pfade

| Pfad | Beschreibung |
|------|--------------|
| `docker-compose.yml` | Stack (MQTT, Backend, WebUI, Audio, RFID, LED, Button, Display, Host-Helper) |
| `data/` | Laufzeitdaten (DB, Config, State) – gitignored |
| `audio/tracks/` | Ablage für Musikdateien – gitignored |
| `infrastructure/` | z. B. Mosquitto-Config |
| `services/` | Alle Services (Backend, WebUI, Audio, RFID, LED, Button, Display, …) |
| `scripts/` | Hilfsskripte (dev-tools, setup-folders, test_display) |
