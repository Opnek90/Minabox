# Minabox

Phoniebox-/Jukebox-System mit RFID, Audio, WebUI und optionaler Hardware (LED, Buttons, Display).

## Installation auf dem Raspberry Pi

Auf einem frisch aufgesetzten Raspberry Pi OS (64-bit):

```bash
curl -fsSL https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh -o minabox-install.sh
```

```bash
bash minabox-install.sh
```

Der Assistent fragt Sprache und Komponenten ab, installiert Docker, richtet den
Hardware-Zugriff ein, laedt die Container und nennt am Ende die Adresse, unter
der die Bedienoberflaeche erreichbar ist.

Bewusst zwei Schritte statt `curl | bash`: die Dialoge brauchen ein echtes
Terminal, das eine Pipe nicht liefert.

Ein erneuter Aufruf auf einer bestehenden Installation oeffnet das
Wartungsmenue (Komponenten aendern, Update, Audio, Diagnose, Deinstallieren).

Ausfuehrlich: [docs/INSTALLATION.md](docs/INSTALLATION.md)

## Schnellstart fuer Entwickler

Aus einem Klon des Repos heraus:

```bash
cp .env.example .env
echo "HOST_HELPER_API_KEY=$(openssl rand -hex 32)" >> .env
./scripts/setup-folders.sh
docker compose up -d
```

`HOST_HELPER_API_KEY` ist Pflicht – ohne den Wert bricht `docker compose up` ab.
Die uebrigen Werte (`MQTT_BROKER`, `MINABOX_DEVICE_ID`, `LOG_LEVEL`) sind in
`.env.example` vorbelegt und koennen so bleiben. `setup-folders.sh` legt die
Laufzeitverzeichnisse an und erzeugt die Service-Configs aus ihren
`.example`-Vorlagen.

Standardmaessig laufen nur die Pflichtservices (MQTT, Backend, Host-Helper,
Audio, WebUI). Optionale Komponenten werden ueber `COMPOSE_PROFILES` in der
`.env` zugeschaltet:

```bash
COMPOSE_PROFILES=rfid,led,button,display,media
```

Die Images kommen aus `ghcr.io/opnek90/minabox-*`. Zum lokalen Bauen statt
Laden: `docker compose build`.

- **Installation (Endnutzer):** [docs/INSTALLATION.md](docs/INSTALLATION.md)
- **Offene Pruefpunkte zum Installer:** [docs/Installer-Verification.md](docs/Installer-Verification.md)
- **Deployment (manuell, Entwickler):** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Entwicklung & Struktur:** [docs/Framework.md](docs/Framework.md), [docs/DEVELOPMENT_INSTRUCTIONS.md](docs/DEVELOPMENT_INSTRUCTIONS.md)
- **Service-Review (Backend, Audio, Host-Helper, …):** [docs/ServiceReview.md](docs/ServiceReview.md)
- **Diagnose-Paket (Support):** [docs/DebugExport.md](docs/DebugExport.md)
- **Entwicklungs- und Ausliefer-Workflow:** [docs/Entwicklungs-Workflow.md](docs/Entwicklungs-Workflow.md)
- **Versionierung der Dienste:** [docs/Versionierung.md](docs/Versionierung.md)
- **Aenderungen je Dienst:** [CHANGELOG.md](CHANGELOG.md) · [englisch](CHANGELOG.en.md)
- **Release- und Update-Workflow (Plan):** [docs/Release-Update-Workflow.md](docs/Release-Update-Workflow.md)
- **Dev-Tools:** `./scripts/dev-tools.sh` (format, check, install, test, venv)
- **Tests:** `./scripts/run-tests.sh`

## Rechtmaessiger Medienimport

Die optionale Komponente `media` kann Medien von einer URL in die lokale
Bibliothek importieren. Sie ist fuer Inhalte gedacht, an denen du die noetigen
Rechte hast:

- eigene Aufnahmen und eigene Uploads,
- gemeinfreie Werke,
- Inhalte mit ausdruecklicher Erlaubnis oder passender Lizenz des
  Rechteinhabers,
- Faelle, in denen eine gesetzliche Erlaubnis greift.

Ob diese Voraussetzungen im Einzelfall vorliegen, kann die Anwendung nicht
pruefen — die Verantwortung dafuer liegt bei dir. Die Domain-Whitelist
(`MEDIA_DOWNLOADER_ALLOWED_DOMAINS`) begrenzt technisch, welche Hosts
ueberhaupt abgerufen werden, und ist keine rechtliche Freigabe.

Das Projekt ist nicht dafuer bestimmt, technische Schutzmassnahmen,
Zugangs-, Konto-, Zahlungs- oder Plattformbeschraenkungen zu umgehen. Die
Schnittstellen nehmen dafuer weder Zugangsdaten noch Cookies oder Schluessel
entgegen; Details in
[services/media-downloader-service/README.md](services/media-downloader-service/README.md).

Fragen oder Hinweise zu Rechten an importierbaren Inhalten bitte ueber
[GitHub Issues](https://github.com/Opnek90/Minabox/issues) — eine gesonderte
Kontaktadresse fuehrt das Projekt derzeit nicht.

## Wichtige Pfade

| Pfad | Beschreibung |
|------|--------------|
| `docker-compose.yml` | Stack (MQTT, Backend, WebUI, Audio, RFID, LED, Button, Display, Host-Helper) |
| `data/` | Laufzeitdaten (DB, Config, State) – gitignored |
| `audio/tracks/` | Ablage für Musikdateien – gitignored |
| `infrastructure/` | z. B. Mosquitto-Config |
| `services/` | Alle Services (Backend, WebUI, Audio, RFID, LED, Button, Display, …) |
| `scripts/` | Hilfsskripte (dev-tools, setup-folders, test_display) |
| `install.sh` | Installations- und Wartungsassistent fuer den Pi |
| `.github/workflows/` | Baut die Container-Images und schiebt sie nach GHCR |


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
