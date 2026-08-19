# Minabox

Phoniebox-/Jukebox-System mit RFID, Audio, WebUI und optionaler Hardware (LED, Buttons, Display).

## Schnellstart

```bash
cp .env.example .env
echo "HOST_HELPER_API_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d
```

`HOST_HELPER_API_KEY` ist Pflicht – ohne den Wert bricht `docker compose up` ab.
Die uebrigen Werte (`MQTT_BROKER`, `MINABOX_DEVICE_ID`, `LOG_LEVEL`) sind in
`.env.example` vorbelegt und koennen so bleiben.

- **Deployment & Installation:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Entwicklung & Struktur:** [docs/Framework.md](docs/Framework.md), [docs/DEVELOPMENT_INSTRUCTIONS.md](docs/DEVELOPMENT_INSTRUCTIONS.md)
- **Service-Review (Backend, Audio, Host-Helper, …):** [docs/ServiceReview.md](docs/ServiceReview.md)
- **Diagnose-Paket (Support):** [docs/DebugExport.md](docs/DebugExport.md)
- **Dev-Tools:** `./scripts/dev-tools.sh` (format, check, install, test, venv)
- **Tests:** `./scripts/run-tests.sh`

## Wichtige Pfade

| Pfad | Beschreibung |
|------|--------------|
| `docker-compose.yml` | Stack (MQTT, Backend, WebUI, Audio, RFID, LED, Button, Display, Host-Helper) |
| `data/` | Laufzeitdaten (DB, Config, State) – gitignored |
| `audio/tracks/` | Ablage für Musikdateien – gitignored |
| `infrastructure/` | z. B. Mosquitto-Config |
| `services/` | Alle Services (Backend, WebUI, Audio, RFID, LED, Button, Display, …) |
| `scripts/` | Hilfsskripte (dev-tools, setup-folders, test_display) |


## Diagnose-Paket bei Problemen

Sammelt Systemzustand, Protokolle und Konfiguration in einer ZIP-Datei, die man
dem Entwickler schicken kann. Passwoerter, WLAN-Kennwoerter und Zugangsschluessel
sind nie enthalten; Seriennummern, WLAN-Name und Karten-IDs nur als unlesbare
Pruefsumme.

- **In der Oberflaeche:** Einstellungen → Diagnose → *Diagnose-Paket*
- **Direktlink** (auch als Support-Link verschickbar):
  `http://<box>:8080/api/v1/system/debug-export`
- **Wenn die Oberflaeche nicht mehr laedt:** denselben Link im Browser oeffnen –
  die Route braucht bewusst keine Anmeldung, ist aber nur aus dem lokalen Netz
  erreichbar und liefert ohne Anmeldung nur die Standard-Stufe (keine
  Dateinamen, kein Abspielverlauf, keine Datenbank).

Auswertung als Entwickler: `.claude/skills/minabox-debug-analyze/` (Skill
`minabox-debug-analyze`, entpackt und triagiert das Paket).
