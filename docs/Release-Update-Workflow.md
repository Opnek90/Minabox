# Release- und Update-Workflow

**Status:** Stand 2026-08-20. Phase 1 ist umgesetzt, Phasen 2-5 sind Entwurf.
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

### E1 - Jeder Dienst hat seine eigene Version

*Entschieden am 2026-08-20. Der erste Entwurf empfahl eine gemeinsame
Stack-Nummer; dagegen sprach das staerkere Argument: eine Korrektur, die nur
Backend und WebUI beruehrt, soll nicht die Nummern von sieben unbeteiligten
Images weiterdrehen. Eine Zahl, die sich bei jeder Kleinigkeit ueberall aendert,
sagt nichts mehr aus.*

Jeder Dienst traegt eine SemVer-Nummer in
`services/<dienst>-service/VERSION`. Sie wird zum Image-Tag und zum OCI-Label.
Details und Bump-Regeln: [Versionierung.md](Versionierung.md).

Was daraus folgt und in den spaeteren Phasen zu loesen ist:

* **Abhaengigkeiten sind Handarbeit.** `shared-lib` und der MQTT-Vertrag
  spannen ueber mehrere Dienste. Wer sie aendert, hebt die Versionen aller
  betroffenen Dienste. Das steht in der Doku; erzwingen laesst es sich nicht.
* **Der Update-Check braucht eine Liste, keine Zahl.** Phase 3 vergleicht
  neun Versionen gegen neun aktuelle Staende, nicht eine gegen eine.
* **Ein Kompatibilitaetsbegriff wird noetig**, sobald Dienste wirklich
  auseinanderlaufen: "Backend ab 0.4 verlangt WebUI ab 0.3". Solange alle
  Dienste zusammen aus main gebaut werden, reicht die Konvention; sobald
  einzeln nachgezogen wird, gehoert das in die Release-Metadaten.

Die Version wird **pro Container erfasst und angezeigt** - sie ist eine
*Beobachtung*, keine Deklaration. Genau dort wird Drift sichtbar: wenn `led`
nach einem Update nicht neu gestartet ist, steht dort weiter die alte Nummer.

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

### Phase 1 - Versionen entstehen und werden sichtbar - **umgesetzt**

*Ergebnis: jeder Container weiss und meldet, welche Version er ist. Noch kein
Update-Check.* Umgesetzt am 2026-08-20, dokumentiert in
[Versionierung.md](Versionierung.md).

Umgesetzt wurde:

1. `VERSION`-Datei je Dienst (neun Images plus shared-lib).
2. Einheitlicher `ARG`/`LABEL`/`ENV`-Block am Ende aller neun Dockerfiles.
3. CI liest die Datei, prueft sie gegen SemVer, reicht sie als Build-Arg
   durch und taggt das Image damit.
4. `/health` jedes Dienstes meldet seine Version (`shared_lib.version`).
5. `container_registry.py` im Backend: Ermittlung aller Container des
   Compose-Projekts ueber den Docker-Socket, mit CPU, RAM und Version.
6. `/system/status` liefert die dynamische Liste; `/system/logs` loest den
   Container-Namen ueber dieselbe Quelle auf.
7. WebUI zeigt die Version je Dienst; "Entwicklungsbuild" statt einer Nummer
   bei lokal gebauten Images.

Nicht umgesetzt und bewusst verschoben:

* **Das retained MQTT-Info-Topic** (Punkt 5 des urspruenglichen Entwurfs).
  Die Docker-Labels decken alle Container ab, die Selbstauskunft ueber
  `/health` deckt den Vergleich "meldet der Prozess dasselbe wie sein Image".
  Das Topic bliebe eine dritte Quelle fuer dieselbe Zahl.
* **Ein eigener `/system/versions`-Endpunkt.** `/system/status` traegt die
  Versionen bereits; ein zweiter Endpunkt waere eine zweite Wahrheit.

Dabei aufgefallen und mitbehoben:

* **host-helper und media-downloader** fehlten in der Dienste-Liste.
* **mqtt** war von der CPU/RAM-Messung ausdruecklich ausgenommen.
* **RAM war nie messbar** auf einem Pi ohne `cgroup_memory=1` - angezeigt
  wurde trotzdem "0.0 MB". Jetzt `null` plus Hinweis, wie man es einschaltet.

### Phase 1a - Nachzieharbeiten aus E1 - **umgesetzt**

*Umgesetzt am 2026-08-21.* Zwei Dinge, die mit einer Nummer je Dienst
zwingend wurden, bevor ein Update-Mechanismus darauf bauen kann:

1. **Die CI baut nur noch geaenderte Dienste** und weigert sich, einen bereits
   vergebenen Versions-Tag zu ueberschreiben. Vorher waere ein unveraenderter
   Dienst bei jedem Push erneut unter seiner alten Nummer gelandet - mit
   anderem Digest, weil `BUILD_DATE` bei jedem Lauf anders war. Derselbe Tag
   haette auf verschiedene Staende gezeigt. Details:
   [Versionierung.md](Versionierung.md).
2. **Ein Image-Tag je Dienst** in `docker-compose.yml`
   (`MINABOX_<DIENST>_TAG`, mit `MINABOX_IMAGE_TAG` und `latest` als
   Rueckfall). Eine einzige globale Variable kann "Backend 0.1.2, Audio 0.1.0"
   nicht ausdruecken - ohne diese Ebene gibt es weder ein gezieltes Update
   noch einen Rueckweg.

### Phase 2 - Release-Manifest mit Changelog - **umgesetzt**

*Umgesetzt am 2026-08-21.* Ergebnis: eine Datei, aus der die Box ablesen kann,
welche Version jedes Dienstes aktuell ist und was sich geaendert hat.

* `CHANGELOG.md` und `CHANGELOG.en.md` - je Dienst, je Version, gleiche
  Struktur. Quelle der Wahrheit.
* `scripts/build_manifest.py` erzeugt daraus `release-manifest.json` und
  prueft mit `--check`, ob beides zusammenpasst.
* Die CI laesst nichts bauen, solange die aktuelle Version eines Dienstes
  nicht beschrieben oder eine Uebersetzung nicht nachgezogen ist.

Offen fuer Phase 3: das Manifest wird mit dem Commit veroeffentlicht, die
Images erst wenn die CI durch ist. In diesem Fenster von wenigen Minuten
kennt es eine Version, die noch nicht in der Registry liegt. Der Update-Check
muss daher pruefen, ob der Image-Tag wirklich existiert, bevor er ein Update
anbietet.

Mit E1 passt "ein Release = eine Version" nicht mehr: neun Dienste haben neun
Nummern, die sich unabhaengig bewegen. Deshalb steht am Ende kein
Release-Body, sondern ein **Manifest**:

```json
{
  "schema": 1,
  "generated_at": "2026-09-01T10:00:00Z",
  "services": {
    "backend": {
      "latest": "0.2.0",
      "releases": [
        {"version": "0.2.0", "date": "2026-09-01",
         "notes": {"de": ["Sleep-Timer haelt jetzt..."],
                   "en": ["The sleep timer now holds..."]}}
      ]
    }
  }
}
```

1. **`CHANGELOG.md`** nach *Keep a Changelog*, gegliedert **nach Dienst**,
   Abschnitte `Neu` / `Verbessert` / `Behoben`. **Zweisprachig** (de/en), weil
   die WebUI beides hat und die Notizen im Endkundendialog landen.
2. **`release.yml`** erzeugt aus dem Changelog das Manifest und legt es als
   Release-Asset ab - eine Datei, ein Abruf, kein Rate-Limit-Risiko.
3. **Konvention festhalten** in [DEVELOPMENT_INSTRUCTIONS.md](DEVELOPMENT_INSTRUCTIONS.md):
   Conventional Commits (wird bereits gelebt), Patch-Bump je geaendertem
   Dienst, wer veroeffentlicht.
4. Optional: ein Werkzeug erzeugt den Rohentwurf aus den Commits, der von Hand
   redigiert wird. Automatisch erzeugte Changelogs sind fuer Entwickler
   brauchbar und fuer Nutzer meist nicht - deshalb der Redaktionsschritt.

*Alternative, die jetzt offensteht:* Seit die GHCR-Pakete oeffentlich sind,
liesse sich "gibt es was Neueres" auch direkt aus der Tag-Liste jedes Images
beantworten, ohne jede Release-Infrastruktur. Das liefert aber keinen
Changelog - und genau der ist der Punkt des Knopfes.

### Phase 3 - Der Pruefknopf

*Ergebnis: "Alles aktuell" oder "Version 1.4.0 verfuegbar - Changelog - Jetzt
aktualisieren?"*

1. **Backend `GET /api/v1/system/update-check`** (`?force=true` umgeht Cache).
   Mit E1 vergleicht der Check **je Dienst**: neun laufende Versionen gegen
   neun aktuelle Staende. Die Antwort ist entsprechend eine Liste, und die
   Oberflaeche sagt nicht "Update verfuegbar", sondern welche Dienste betroffen
   sind:
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

### Phase 4 - Das Update selbst wird verlaesslich - **weitgehend umgesetzt**

*Umgesetzt am 2026-08-21.*

* **Gezieltes Update**: nur die Dienste mit neuer Version werden bewegt, alle
  uebrigen dabei auf ihrem laufenden Stand festgenagelt.
* **Sicherung vor jedem Update** unter `data/backups/`, die letzten fuenf
  bleiben. Schlaegt sie fehl, laeuft kein Update.
* **Fortschritt** in fuenf Schritten, mit aufklappbarer Ausgabe; das Update
  laeuft als systemd-Unit auf dem Host und ueberdauert den Neustart der
  Container.
* **Verifikation**: nach dem Neustart wird geprueft, ob jeder betroffene
  Dienst wirklich die Zielversion faehrt - nicht nur, ob er laeuft.
* **Kein Rueckweg-Knopf.** Er war gebaut und wurde am 2026-08-21 wieder
  entfernt: ein Rueckschritt ist nur harmlos, wenn die aeltere Fassung alles
  lesen kann, was die neuere geschrieben hat, und das laesst sich ohne
  Schemastempel in der Datenbank nicht zusagen. Der ehrliche Weg bleibt die
  Sicherung von vor dem Update plus ein von Hand gesetzter Tag.

Offen geblieben:

* ~~**Schemaversion in der Datenbank.**~~ **Umgesetzt am 2026-08-21**:
  `SCHEMA_VERSION` in `db_manager`, gespeichert in `PRAGMA user_version`. Eine
  Datenbank, die neuer ist als der laufende Code, wird erkannt und ueber den
  Hinweisbalken gemeldet, statt stillschweigend Daten als verschwunden
  erscheinen zu lassen. Siehe [Versionierung.md](Versionierung.md).
* **Digest-Zusatzpruefung** fuer den Fall gleicher Nummer bei neuem Bau.

Urspruengliche Planung:

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
6. ~~**Changelog-Sprache**~~ - **entschieden am 2026-08-21: zweisprachig.**
   Die WebUI hat de und en, also braucht auch der Changelog beide. Das faellt
   auf das Release-Manifest zurueck: die Notizen je Dienst und Version stehen
   dort pro Sprache (`notes: {de: ..., en: ...}`), und der Dialog zeigt die
   Sprache, die der Nutzer eingestellt hat - mit Deutsch als Rueckfall, falls
   eine Uebersetzung fehlt.
