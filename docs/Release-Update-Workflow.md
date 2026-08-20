# Release- und Update-Workflow

**Status:** Entwurf, Stand 2026-08-20. Noch nichts davon ist implementiert.
Dieses Dokument legt die Leitentscheidungen fest und schneidet die Arbeit in
Phasen. Die Detailausarbeitung (Datenmodelle, genaue Endpunkte, UI-Screens)
folgt pro Phase.

Ziel: ein Weg von "Code auf main" bis "Pi laeuft auf der neuen Version", der
fuer Nutzer aus genau zwei Schritten besteht - *Pruefen* und *Aktualisieren* -
und der jederzeit sichtbar macht, was gerade laeuft.

---

## 1. Ausgangslage

### Was schon da ist

| Baustein | Ort | Zustand |
|---|---|---|
| Image-Build fuer 9 Services | [.github/workflows/build-images.yml](../.github/workflows/build-images.yml) | Laeuft, nativ arm64, pusht nach GHCR |
| Tag-Ableitung `latest` / `sha-xxxxxxx` / SemVer | ebd., Schritt `Derive tags` | SemVer-Zweig existiert, wird aber nie ausgeloest |
| Image-Referenz mit Variable | [docker-compose.yml](../docker-compose.yml) | `ghcr.io/opnek90/minabox-*:${MINABOX_IMAGE_TAG:-latest}` |
| Update-Ausfuehrung | [host-helper routes.py:1742](../services/host-helper-service/src/host_helper/api/routes.py) | `git pull --ff-only` + `compose pull` + `compose up -d` |
| Versionsanzeige | [host-helper routes.py:1804](../services/host-helper-service/src/host_helper/api/routes.py) | Liest Git-Commit des Arbeitsbaums |
| Wartungs-UI mit Update-Knopf | [SystemMaintenanceSection.tsx](../services/webui-service/src/components/admin/SystemMaintenanceSection.tsx) | Vorhanden, ohne Vorher-Nachher-Information |
| Dienste-Uebersicht | [routes_system.py:29](../services/backend-service/src/backend_service/api/routes_system.py), [ServiceStatus.tsx](../services/webui-service/src/components/admin/ServiceStatus.tsx) | Status + CPU/RAM pro Container |
| Backup vor Eingriffen | `/system/backup/download`, `/system/backup/restore` | Vorhanden, aber nicht an das Update gekoppelt |
| Docker-Socket im Backend | docker-compose.yml, `group_add: DOCKER_GID` | Read-only gemountet - reicht fuer `inspect` |

### Was fehlt oder nicht stimmt

1. **Es gibt keine Version.** `git tag` ist leer, kein `CHANGELOG.md`, kein
   `version`-Feld in einem `pyproject.toml`. Alle Images tragen `latest`.
   Der SemVer-Zweig der CI hat noch nie gefeuert.
2. **`/system/version` misst das falsche Objekt.** Es vergleicht den
   Git-Arbeitsbaum des Pi mit `origin/main`. Das sagt nichts darueber, welche
   *Images* laufen. Ein Pi kann git-aktuell sein und trotzdem Container von
   vorletzter Woche fahren (oder umgekehrt, wenn `up -d` nicht durchlief).
3. **`update_available` ist damit strukturell unzuverlaessig** und der
   Update-Knopf laeuft blind - er sagt vorher nicht, was er tut, und nachher
   nicht, was passiert ist.
4. **Die Dienste-Uebersicht ist unvollstaendig.** `SERVICE_IDS` ist eine feste
   Liste aus acht Namen; **host-helper** und **media-downloader** fehlen ganz.
5. **Die Liste ignoriert die Profile.** Welche Container es real gibt, haengt
   an `COMPOSE_PROFILES` in der `.env` (Standard aus dem Installer: `rfid`).
   Ein Pi ohne LED-Profil zeigt "led: offline" statt "nicht installiert".
6. **MQTT hat kein CPU/RAM**, weil `stats_checks` `mqtt` explizit ausschliesst -
   obwohl `minabox-mqtt` in `CONTAINER_NAMES` steht und `inspect`/`stats`
   funktionieren wuerden.
7. **Kein Rueckweg.** Ohne feste Tags gibt es kein "zurueck auf die vorige
   Version", und ohne Schema-Stempel in der DB weiss niemand, ob ein
   Rueckschritt die Datenbank ueberhaupt vertraegt.

---

## 2. Leitentscheidungen

### E1 - Eine Version fuer den ganzen Stack, angezeigt pro Container

Alle neun Images entstehen aus **einem** Repository, in **einem** CI-Lauf, aus
**einem** Commit. Sie sind keine unabhaengig veroeffentlichten Artefakte. Sie
einzeln zu versionieren wuerde eine Freiheit vortaeuschen, die es nicht gibt,
und den Kompatibilitaetstest ("passt Backend 1.4 zu WebUI 1.2?") zu einem
echten Problem machen, das wir uns heute schenken koennen.

Deshalb: **eine SemVer-Nummer pro Release**, `v1.4.0`, die jedes Image traegt.

Trotzdem wird die Version **pro Container erfasst und angezeigt** - denn sie
ist eine *Beobachtung*, keine Deklaration. Genau dort wird Drift sichtbar:
wenn `led` nach dem Update nicht neu gestartet ist, steht dort weiter `1.3.2`,
und die UI kann das als Warnung zeigen statt es zu verschlucken.

*Spaeter erweiterbar:* Wenn ein Dienst je einen eigenen Zyklus bekommt, kann
er ein eigenes Tag bekommen, ohne dass das Anzeigemodell sich aendert.

### E2 - Docker-Labels sind die Wahrheit, MQTT die Ergaenzung

Zwei moegliche Quellen fuer "welche Version laeuft in Container X":

| | Docker-Labels (`docker inspect`) | MQTT-Info-Topic |
|---|---|---|
| Deckt mqtt + webui ab | ja | nein (kein MQTT-Client in Mosquitto/nginx) |
| Verfuegbar wenn Dienst haengt | ja | nein |
| Zeigt Image-Digest, nicht nur Tag | ja | nein |
| Zeigt, was der Prozess *selbst* meint | nein | ja |
| Neue Abhaengigkeit | keine (Socket ist schon gemountet) | keine (Basis-Client kann retained publishen) |

**Primaer: Docker-Labels.** Das Backend hat den Socket bereits read-only und
die passende Gruppe. `inspect` liefert fuer *jeden* Container einheitlich
`org.opencontainers.image.version`, `.revision`, `.created` plus
`RepoDigests` - auch fuer `eclipse-mosquitto` und die nginx-basierte WebUI,
und auch fuer einen Container, dessen Prozess nicht mehr antwortet.

**Sekundaer: ein retained MQTT-Topic** `minabox/<device>/<service>/info` pro
Dienst, der einen MQTT-Client hat. Das kostet fast nichts, weil
`shared_lib.mqtt.base_client` retained-Publish und Status-Replay nach
Reconnect schon kann. Es liefert die *selbstgemeldete* Version und deckt damit
den Fall ab, dass ein Image-Label luegt (lokal gebautes Dev-Image, manuell
ausgetauschter Code im Volume). Bei Abweichung: beide anzeigen, Label gewinnt.

Antwort auf die Ausgangsfrage: **Ja, MQTT - aber nicht als einziger Weg.**
Wer nur MQTT nutzt, kann Mosquitto und die WebUI prinzipiell nicht messen.

### E3 - Der Update-Vergleich laeuft gegen GitHub Releases, nicht gegen die Registry

Zwei Vergleichsmoeglichkeiten:

- **GitHub Releases API** (`/repos/Opnek90/minabox/releases`): liefert
  Versionsnummer *und* Changelog-Text in einem Aufruf, ohne Auth, 60
  Anfragen/Stunde und IP. Genau das, was der Dialog anzeigen soll.
- **GHCR Manifest-API**: liefert Digests, beantwortet "hat sich `latest`
  bewegt", aber kein Changelog und braucht ein (anonymes) Pull-Token.

**Primaer: Releases API.** Der Digest-Vergleich kommt als Zusatzpruefung in
Phase 4 dazu, fuer den Fall "gleiche Versionsnummer, neu gebautes Image".

Damit das ueberhaupt Sinn ergibt, muss der Pi weg von `latest`:
`MINABOX_IMAGE_TAG` wird auf die konkrete Version festgenagelt (`1.4.0`).
Erst dadurch ist ein Update deterministisch und ein Rueckschritt trivial.

### E4 - Ein Update ist ein Versionssprung, kein `git pull`

Heute zieht das Update `origin/main` und dazu `latest`-Images - zwei bewegliche
Ziele, die nicht garantiert zusammenpassen. Kuenftig:

```
git fetch --tags
git checkout tags/v1.4.0        # compose-Datei, Configs, Skripte
.env: MINABOX_IMAGE_TAG=1.4.0   # Images
docker compose pull && up -d
```

Ein Zustand, eine Nummer, umkehrbar. Der bestehende `git pull --ff-only`-Pfad
bleibt fuer den Kanal `dev` erhalten (siehe E5).

### E5 - Drei Kanaele

`MINABOX_UPDATE_CHANNEL` in der `.env`:

- **`stable`** (Standard): nur echte Releases. Fuer alle normalen Boxen.
- **`beta`**: auch GitHub-Prereleases (`v1.5.0-rc.1`). Fuer Tester.
- **`dev`**: folgt `main` und `latest`, kein Versionsvergleich, nur
  "neuer Commit vorhanden". Fuer den Entwicklungs-Pi.

---

## 3. Zielbild

```
Entwicklung                     Release                        Geraet
-----------                     -------                        ------
feature/xyz                     git tag v1.4.0                 Backend prueft (taeglich +
  |  Conventional Commits         |                            auf Knopfdruck):
  v                               v                              GET /releases  ->  1.4.0
main  --------------------->  build-images.yml                   docker inspect ->  1.3.2
  |   latest, sha-abc1234         | version=1.4.0                             ->  Update!
  |                               | Labels + APP_VERSION
  |                               v                            Nutzer sieht Changelog,
  |                          release.yml                       drueckt "Aktualisieren"
  |                               | CHANGELOG-Abschnitt          |
  |                               v                              v
  +---------------------->  GitHub Release v1.4.0            Backup -> checkout v1.4.0
                            (Notes = Changelog)               -> .env-Tag -> pull -> up -d
                                                              -> Verifikation -> fertig
```

---

## 4. Phasen

### Phase 1 - Versionen entstehen und werden sichtbar

*Ergebnis: jeder Container weiss und meldet, welche Version er ist. Noch kein
Update-Check.*

1. **`VERSION`-Datei** im Repo-Wurzelverzeichnis als einzige Quelle
   (`1.4.0`). Alternativ Ableitung aus `git describe` - zu entscheiden.
2. **Alle neun Dockerfiles** bekommen einheitlich:
   ```dockerfile
   ARG APP_VERSION=0.0.0-dev
   ARG GIT_SHA=unknown
   ARG BUILD_DATE
   LABEL org.opencontainers.image.version=$APP_VERSION \
         org.opencontainers.image.revision=$GIT_SHA \
         org.opencontainers.image.created=$BUILD_DATE \
         org.opencontainers.image.source=https://github.com/Opnek90/minabox
   ENV APP_VERSION=$APP_VERSION GIT_SHA=$GIT_SHA
   ```
   Der Default `0.0.0-dev` sorgt dafuer, dass lokal gebaute Images sich
   selbst als Entwicklungsstand ausweisen - ohne Extraschritt.
   Mosquitto laeuft aus einem Fremd-Image; dort setzen wir die Labels ueber
   `docker-compose.yml` (`labels:` am Service), damit die Abfrage einheitlich
   bleibt.
3. **CI** reicht die Build-Args durch (`build-push-action` -> `build-args`)
   und leitet `APP_VERSION` aus dem Git-Tag ab, sonst `0.0.0-dev+<sha>`.
4. **`/health` jedes Dienstes** gibt `version` und `git_sha` aus `os.environ`
   mit zurueck (Schema-Erweiterung in `shared_lib.schemas`, damit alle
   Dienste dieselbe Form liefern).
5. **Retained MQTT-Info** (E2, sekundaer): Basis-Client publiziert beim
   Verbinden `minabox/<device>/<service>/info` mit
   `{service, version, git_sha, started_at}`, `retain=true`.
6. **Backend: `GET /api/v1/system/versions`** - liest per Docker-Socket
   `inspect` fuer alle Container des Compose-Projekts (Label-Filter
   `com.docker.compose.project`), ergaenzt die MQTT-Selbstauskunft, liefert:
   ```json
   {
     "stack_version": "1.3.2",
     "consistent": false,
     "containers": [
       {"service":"backend","image":"ghcr.io/...:1.3.2","version":"1.3.2",
        "digest":"sha256:...","reported_version":"1.3.2","state":"running",
        "started_at":"2026-08-19T20:11:03Z"},
       {"service":"led","version":"1.3.0","state":"running","drift":true}
     ]
   }
   ```
   `stack_version` = haeufigste Version; `consistent=false`, wenn ein
   Container abweicht.
7. **WebUI, Technische Details**: Versions-Chip pro Dienst, Warnhinweis bei
   Drift ("led laeuft noch auf 1.3.0 - Neustart erforderlich").

**Gleichzeitig die gefundenen Luecken schliessen** (klein, aber sie gehoeren
in genau diese Phase, weil das Versionsraster ohnehin alle Container braucht):

- `SERVICE_IDS` um **host-helper** und **media-downloader** erweitern, inkl.
  `SERVICE_HEALTH_URLS` und `CONTAINER_NAMES`.
- Die Liste **profilabhaengig** machen: entweder aus `COMPOSE_PROFILES` lesen
  oder - sauberer - aus `docker inspect` der real existierenden Container des
  Projekts ableiten. Dritter Zustand `not_installed` neben `online`/`offline`,
  damit ein bewusst weggelassener Dienst nicht wie ein Ausfall aussieht.
- **CPU/RAM fuer mqtt** freischalten (den `mqtt`-Ausschluss bei `stats_checks`
  entfernen; `minabox-mqtt` steht bereits in `CONTAINER_NAMES`).

### Phase 2 - Releases mit Changelog

*Ergebnis: `git tag v1.4.0` erzeugt ein GitHub Release mit lesbaren
Aenderungsnotizen.*

1. **`CHANGELOG.md`** nach *Keep a Changelog*, auf Deutsch, weil die Notizen
   im Endkundendialog landen. Abschnitte `Neu` / `Verbessert` / `Behoben`.
2. **`release.yml`**: bei `push` auf `v*` den Abschnitt zur Version aus
   `CHANGELOG.md` schneiden und als Release-Body setzen. Prerelease-Flag bei
   `-rc`/`-beta` im Tag.
3. **Konvention festhalten** in [DEVELOPMENT_INSTRUCTIONS.md](DEVELOPMENT_INSTRUCTIONS.md):
   Conventional Commits (wird bereits gelebt), Bump-Regel, wer taggt.
4. Optional: `release-drafter` oder `git-cliff` erzeugt den Rohentwurf aus den
   Commits, der von Hand redigiert wird. Automatisch generierte Changelogs
   sind fuer Entwickler brauchbar und fuer Nutzer meist nicht - deshalb der
   Redaktionsschritt.

### Phase 3 - Der Pruefknopf

*Ergebnis: "Alles aktuell" oder "Version 1.4.0 verfuegbar - Changelog - Jetzt
aktualisieren?"*

1. **Backend `GET /api/v1/system/update-check`** (`?force=true` umgeht Cache):
   ```json
   {
     "current_version": "1.3.2",
     "latest_version": "1.4.0",
     "update_available": true,
     "channel": "stable",
     "checked_at": "2026-08-20T09:12:00Z",
     "from_cache": false,
     "releases": [
       {"version":"1.4.0","published_at":"...","notes_md":"### Neu\n- ...",
        "prerelease":false},
       {"version":"1.3.3","published_at":"...","notes_md":"..."}
     ],
     "error": null
   }
   ```
   Wichtig: **alle** uebersprungenen Versionen zwischen aktuell und neuester,
   nicht nur die letzte - sonst verliert ein Nutzer, der zwei Releases
   uebersprungen hat, die Haelfte der Information.
2. **Ausfallverhalten**: kein Netz, Rate-Limit oder GitHub down darf nie zu
   "Update verfuegbar" fuehren. Bei Fehler: letzter Cache-Stand plus
   Hinweiszeile, `update_available` bleibt `false`.
3. **Cache** in der DB (Tabelle `update_check` oder `settings`-Zeile), TTL ~6h,
   plus taeglicher Hintergrund-Check mit zufaelligem Versatz (nicht alle Boxen
   um 03:00 gleichzeitig gegen die API).
4. **WebUI, Wartung**: Knopf "Auf Updates pruefen" -> Ergebniskarte. Bei
   verfuegbarem Update ein Dialog mit gerendertem Markdown-Changelog (Sanitize
   nicht vergessen), "Spaeter" / "Jetzt aktualisieren". Dezenter Punkt am
   Wartungs-Menuepunkt, wenn ein Update wartet.
5. **Kanalwahl** in den erweiterten Einstellungen (`stable`/`beta`/`dev`).

### Phase 4 - Das Update selbst wird verlaesslich

*Ergebnis: Update mit Sicherungsnetz, Fortschritt und Rueckweg.*

1. **Host-Helper `POST /system/update-minabox` umbauen** auf den Ablauf aus E4
   (Zielversion als Parameter). Schritte einzeln protokolliert.
2. **Automatisches Backup** vor jedem Update (die Endpunkte existieren), mit
   Aufbewahrung der letzten N Sicherungen.
3. **Fortschritt statt Blockade**: Update laeuft im Hintergrund,
   `GET /system/update-status` liefert Phase (`backup` -> `checkout` ->
   `pull` -> `restart` -> `verify`) und Log-Auszug. Die WebUI verliert
   waehrend `restart` zwangslaeufig die Verbindung - der bestehende
   `ConnectionLostScreen` sollte in diesem Fall "Update laeuft" zeigen und
   selbst wieder anklopfen, statt einen Fehler zu melden.
4. **Verifikation nach dem Update**: alle Container laufen, alle melden die
   Zielversion (`consistent=true` aus Phase 1). Sonst deutliche Warnung.
5. **Rueckweg**: "Zurueck auf 1.3.2" setzt Tag und Checkout zurueck. Dazu
   noetig: **Schema-Version in der DB** (`schema_version`-Zeile, gesetzt von
   `db_manager`), und pro Release die Angabe, ab welcher Schema-Version ein
   Rueckschritt noch gefahrlos ist. Die Migrationen in
   [db_manager.py](../services/backend-service/src/backend_service/core/db_manager.py)
   sind heute idempotente `ALTER TABLE`s ohne Stempel - vorwaerts robust,
   rueckwaerts blind.
6. **Digest-Zusatzpruefung** (E3): erkennt neu gebaute Images bei gleicher
   Versionsnummer - relevant im Kanal `dev`.

### Phase 5 - Entwicklungsseite abrunden

1. **`docker-compose.dev.yml`** als Overlay: baut lokal statt zu ziehen,
   `APP_VERSION=0.0.0-dev`, Quellcode als Bind-Mount fuer schnelle Runden.
2. **CI-Gates vor dem Merge**: `ruff` + `pytest` fuer die Python-Dienste,
   `tsc --noEmit` + Build fuer die WebUI. Ein Release-Tag sollte nur auf
   gruenem `main` gesetzt werden koennen.
3. **`docs/DEPLOYMENT.md` und `install.sh` angleichen**: Installer schreibt
   eine feste Version in `MINABOX_IMAGE_TAG` statt `latest`, plus
   `MINABOX_UPDATE_CHANNEL`.
4. **Ein Testlauf-Pi pro Kanal**, mindestens einer auf `beta`.

---

## 5. Reihenfolge und Aufwand

| Phase | Nutzen fuer sich allein | Groesse |
|---|---|---|
| 1 Versionen sichtbar | hoch - beantwortet sofort "was laeuft hier?" | mittel, breit (9 Dockerfiles, CI, Backend, UI) |
| 2 Releases + Changelog | mittel - Voraussetzung fuer 3 | klein |
| 3 Pruefknopf | hoch - das eigentliche Ziel | mittel |
| 4 Update verlaesslich | hoch - schuetzt vor dem halben Update | gross |
| 5 Dev-Seite | mittel | klein bis mittel |

1, 2 und 3 sind der Kern. Phase 4 ist die groesste und lohnt eine eigene
Ausarbeitung, sobald 1-3 stehen.

---

## 6. Offene Punkte

1. **Versionsquelle**: `VERSION`-Datei im Repo oder `git describe`? Datei ist
   explizit und im Diff sichtbar; `git describe` spart einen Handgriff.
2. **Wer taggt?** Von Hand, oder ein Workflow, der bei einem Label an einem
   Merge automatisch bumpt?
3. **Repo-Sichtbarkeit**: Der Releases-Check gegen ein *privates* Repo braucht
   ein Token auf jedem Pi. Ist `Opnek90/minabox` oeffentlich oder soll es das
   werden? Falls nicht: schlanker oeffentlicher Endpunkt (GitHub Pages mit
   `latest.json`) als Alternative.
4. **Muss der Pi weiter ein Git-Klon sein?** Alternative: `docker-compose.yml`
   und Configs als Release-Asset ziehen. Sauberer, aber ein Umbau am
   Installer.
5. **Automatische Updates** - nie, nur auf Wunsch, oder Sicherheitsupdates
   automatisch? Vorschlag: vorerst nie, nur Hinweis.
6. **Changelog-Sprache**: Deutsch fuer Nutzer, oder zweisprachig (die WebUI
   hat de/en)?
