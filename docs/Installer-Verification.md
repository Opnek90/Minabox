# Installationsassistent - offene Pruefpunkte

Stand: 2026-08-20

Der Assistent (`install.sh`), die Compose-Profile und der GHCR-Workflow sind
umgesetzt. Was hier steht, ist **noch nicht auf echter Hardware bestaetigt** —
auf dem Entwicklungs-Pi sind Docker, Gruppen, Overlays und Configs bereits
vorhanden, dadurch laeuft der Assistent dort durch einen grossen Teil seiner
Logik gar nicht.

## Voraussetzungen ausserhalb des Codes

Ohne diese beiden Punkte funktioniert der Installationsbefehl aus der README
nicht — `curl` und `docker pull` scheitern beide an fehlenden Berechtigungen.

- [ ] **Repository oeffentlich schalten.** `github.com/Opnek90/Minabox` ist
      derzeit nur per SSH erreichbar. `raw.githubusercontent.com` und ein
      anonymer `git clone` ueber HTTPS brauchen ein Public-Repo.
- [ ] **GHCR-Packages auf „public" stellen.** Einmalig nach dem ersten
      erfolgreichen Workflow-Lauf unter *Packages → Package settings →
      Change visibility*, fuer alle neun Images. Sonst verlangt `docker pull`
      auf dem Pi ein Login.

## CI

- [ ] Workflow einmal per `workflow_dispatch` starten und alle neun Jobs gruen
      sehen. Erwarteter Knackpunkt: `led` und `button` uebersetzen lgpio aus
      dem Quelltext, `webui` baut mit npm — das Job-Timeout steht auf 60 min.
- [ ] Steht der Runner `ubuntu-24.04-arm` zur Verfuegung? Er ist fuer
      oeffentliche Repos kostenlos. Falls nicht, auf `ubuntu-latest` mit
      `docker/setup-qemu-action` umstellen — dann werden die Builds aber
      deutlich langsamer und das Timeout muss hoch.
- [ ] Auf dem Pi ohne Login pruefen:
      `docker pull ghcr.io/opnek90/minabox-backend:latest`
- [ ] Architektur bestaetigen:
      `docker image inspect ghcr.io/opnek90/minabox-backend:latest --format '{{.Architecture}}'`
      muss `arm64` liefern.

## Frisch geflashte SD-Karte

Der einzige belastbare Test. Raspberry Pi OS 64-bit, nichts vorinstalliert.

- [ ] Assistent mit Standardauswahl (nur RFID) durchlaufen. Danach ist die
      Oberflaeche unter `http://<IP>` erreichbar und `docker compose ps` zeigt
      alle Pflichtcontainer als `healthy`.
- [ ] Zweiter Aufruf oeffnet das Wartungsmenue statt einer Neuinstallation.
- [ ] *Komponenten aendern* mit LED und Display: die Container kommen dazu.
- [ ] Dieselbe Komponente wieder abwaehlen: der Container ist danach wirklich
      **weg**, nicht nur gestoppt. Das prueft, ob
      `docker compose down --remove-orphans` greift.
- [ ] `bash install.sh --unattended --components led` laeuft ohne einen
      einzigen Dialog durch.

## Audio

Der historisch fehleranfaelligste Teil.

- [ ] Kopfhoererbuchse waehlen, Titel abspielen, Ton pruefen.
- [ ] **Reboot ohne SSH-Login**, danach erneut abspielen. Das ist der Test fuer
      `loginctl enable-linger`: der Audio-Container spricht ueber
      `/run/user/<UID>/pulse` mit der Benutzersitzung. Fehlt das Linger,
      existiert der Socket nach einem Neustart ohne Login nicht und die Box
      bleibt stumm. Gegenprobe:
      `loginctl show-user $USER | grep Linger`
- [ ] Mit einem HAT (WM8960 oder HiFiBerry): Overlay-Eintrag in `config.txt`
      pruefen, neu starten, dann im Wartungsmenue *Audio neu einrichten*.
- [ ] Sicherung `config.txt.minabox-backup` ist angelegt und der Assistent hat
      nur seinen eigenen markierten Block angefasst.
- [ ] **Offen:** startet der Audio-Service sauber, wenn `output_device_name` in
      `audio.json` leer ist, und faellt er dann tatsaechlich auf die
      Autoerkennung zurueck? Die Vorlage `audio.json.example` setzt das Feld
      bewusst leer. Falls der Service dabei mit einem Fehler abbricht, muss der
      Assistent immer einen Sink schreiben.

## Negativtests

Der Assistent soll verstaendlich melden statt mit einem Bash-Fehler abzubrechen.

- [ ] Port 80 belegt (z. B. laufender nginx)
- [ ] Netzverbindung waehrend `docker compose pull` unterbrochen
- [ ] `raspi-config` nicht vorhanden
- [ ] 32-Bit-System (muss mit klarer Meldung ablehnen)
- [ ] Zu wenig freier Speicher

## Bestehende Installationen migrieren

Wer Minabox vor der Profil-Umstellung installiert hat, dessen `.env` kennt
`COMPOSE_PROFILES` nicht. Beim naechsten `docker compose up -d` fallen dann
`rfid`, `led`, `button`, `display` und `media-downloader` **still weg**.

- [ ] Migrationshinweis in die Release-Notes aufnehmen:

```bash
echo "COMPOSE_PROFILES=rfid,led,button,display,media" >> .env
```

- [ ] Ebenso ergaenzen, falls nicht vorhanden: `HOST_UID`, `I2C_GID`,
      `GPIO_GID`, `BOOT_CONFIG_DIR`. Die Defaults in `docker-compose.yml`
      passen nur zufaellig auf ein Standard-Raspberry-Pi-OS.

Auf dem Entwicklungs-Pi ist das bereits erledigt.

## Ersteinrichtungs-Assistent (WebUI)

Gebaut, aber noch nicht auf echter Hardware durchgespielt. Die vollstaendige
Liste steht in [services/webui/Setup-Wizard.md](services/webui/Setup-Wizard.md);
die wichtigsten Punkte:

- [ ] Frische Box: Assistent springt beim ersten Aufruf auf, nach Abbruch
      bleibt nur der Hinweis.
- [ ] Bestandsinstallation mit Karten: Assistent springt **nicht** auf.
- [ ] Testton stoppt die laufende Wiedergabe nicht und kommt aus dem
      tatsaechlich gewaehlten Ausgang.
- [ ] Lernmodus wird beim Verlassen des Inhalte-Schritts wieder abgeschaltet.
- [ ] Neue Images noetig: die Endpunkte `POST /api/v1/audio/test-tone` und
      `POST /api/v1/config/display/test` stecken in backend, audio und
      display — der Assistent funktioniert erst mit frisch gebauten Images.

## Sonstiges

- [ ] `POST /system/update-minabox` mit dem neuen `git pull --ff-only` gegen
      eine echte Installation testen — insbesondere den Fall „lokale
      Aenderungen vorhanden", der bewusst nicht fatal sein soll.
- [ ] `docs/DEPLOYMENT.md` einmal vollstaendig von Hand nachvollziehen. Die
      Seite wurde an die Profile und GHCR angepasst, aber nicht durchgespielt.
