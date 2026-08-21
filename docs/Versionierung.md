# Versionierung der Dienste

Jeder Minabox-Dienst traegt seine **eigene** Versionsnummer. Eine Korrektur,
die nur Backend und WebUI beruehrt, hebt auch nur deren Nummern - die uebrigen
sieben Images behalten ihre. Das ist der Grund fuer den Zuschnitt: eine
gemeinsame Stack-Nummer wuerde bei jeder Kleinigkeit alle neun Zahlen
weiterdrehen und damit nichts mehr aussagen.

Dieses Dokument beschreibt Phase 1 aus
[Release-Update-Workflow.md](Release-Update-Workflow.md): woher eine Version
kommt, wie sie ins Image gelangt und wie die Oberflaeche sie liest.

---

## 1. Die Quelle: `services/<dienst>-service/VERSION`

Eine Datei, eine Zeile, SemVer:

```
0.1.0
```

Sie ist die einzige Stelle, an der die Nummer steht. Wer einen Dienst
veroeffentlicht, aendert diese Datei - sonst nichts.

**Bump-Regeln** (SemVer, aus Nutzersicht gedacht):

| Aenderung | Beispiel | Sprung |
|---|---|---|
| Fehler behoben, Verhalten sonst gleich | Wiedergabe haengt nicht mehr | Patch (`0.1.0` → `0.1.1`) |
| Neue Faehigkeit, alles Alte laeuft weiter | Sleep-Timer kommt dazu | Minor (`0.1.1` → `0.2.0`) |
| Bruch: Konfiguration, API oder Daten muessen mit | Config-Feld entfaellt | Major (`0.2.0` → `1.0.0`) |

**Abhaengigkeiten.** `shared-lib` ist kein Image, aber alle Python-Dienste
haengen daran. Eine Aenderung dort wirkt in jedem Dienst, der sie benutzt -
also auch dessen VERSION anheben. Gleiches gilt fuer eine Aenderung am
MQTT-Vertrag: sie betrifft beide Seiten, Sender und Empfaenger.

---

## 2. Der Weg ins Image

Am Ende jedes Dockerfiles steht derselbe Block:

```dockerfile
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="minabox-audio" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/Opnek90/minabox"
ENV APP_VERSION=${APP_VERSION} ...
```

Drei Entscheidungen stecken darin:

1. **Der Default ist `0.0.0-dev`.** Ein lokal gebautes Image soll sich nicht
   als Release ausgeben. Die Oberflaeche zeigt dafuer "Entwicklungsbuild"
   statt einer Nummer.
2. **Der Block steht am Dateiende.** Ein Versionswechsel macht so nur die
   letzten Metadaten-Layer ungueltig, nicht den ganzen Build.
3. **Label *und* Umgebungsvariable.** Das Label liest das Backend von aussen
   ueber den Docker-Socket - das funktioniert auch fuer Container ohne Python
   und fuer solche, deren Prozess haengt. Die Variable liest der Dienst selbst
   und meldet sie in `/health`. Zwei Wege, dieselbe Zahl; weichen sie
   voneinander ab, laeuft im Container etwas anderes als das Image behauptet.

Die WebUI bekommt nur das Label - nginx liest keine dieser Variablen.

---

## 3. Die CI

[build-images.yml](../.github/workflows/build-images.yml) liest pro
Matrix-Eintrag die zugehoerige `VERSION`, prueft sie gegen SemVer und benutzt
sie zweifach:

- als **Build-Arg** → landet in Label und ENV,
- als **Image-Tag** → `ghcr.io/opnek90/minabox-audio:0.1.0` und `:0.1`,
  zusaetzlich zu `latest` und `sha-<commit>`.

Eine kaputte `VERSION`-Datei laesst den Job scheitern, bevor etwas in die
Registry geht.

Die Labels stammen bewusst **nicht** von `docker/metadata-action`: deren
`org.opencontainers.image.version` leitet sich vom Git-Ref ab (bei einem
main-Push also "main") und wuerde das Label aus dem Dockerfile ueberschreiben.

### Gebaut wird nur, was sich geaendert hat

[select_services.py](../.github/scripts/select_services.py) bestimmt vor dem
Bauen, welche Dienste dieser Lauf betrifft:

| Geaendert | Gebaut wird |
|---|---|
| `services/<dienst>-service/**` | dieser Dienst |
| `services/shared-lib/**` | alle Dienste ausser webui |
| Workflow oder Skript | nichts |
| Doku, `docker-compose.yml`, `.env.example` | nichts |
| kein Vergleichspunkt (Force-Push, erster Push) | alle |

Dass eine Aenderung am Workflow *keinen* Rebuild ausloest, ist Absicht: sie
aendert keinen Image-Inhalt. Was ein Image wirklich veraendert - Dockerfile,
Quelltext, Requirements - liegt unter `services/<dienst>-service/` und wird
dadurch ohnehin erfasst. Wuerde eine Workflow-Aenderung alle neun Dienste neu
bauen, landeten unveraenderte Dienste erneut unter ihrer bereits
veroeffentlichten Nummer.

### Ein Versions-Tag ist unveraenderlich

Vor dem Push prueft der Lauf, ob der Versions-Tag in der Registry schon
existiert. Wenn ja und er stammt aus einem **anderen** Commit, bricht der Job
ab:

```
Version 0.1.1 von backend ist bereits vergeben (aus Commit a24b276...).
Bitte services/backend-service/VERSION anheben.
```

Damit erzwingt die CI die Bump-Regel, statt sich auf Disziplin zu verlassen.
Zwei Ausnahmen: derselbe Commit darf durchlaufen (ein Neulauf desselben
Standes), und ein Lauf von Hand (`workflow_dispatch`) warnt nur, statt
abzubrechen.

`BUILD_DATE` kommt aus dem Commit-Zeitstempel, nicht aus der Uhr des Runners -
ein Neulauf desselben Commits erzeugt sonst allein deshalb ein anderes Image.

---

## 4. Wie die Oberflaeche es liest

`GET /api/v1/system/status` liefert einen Eintrag **pro real vorhandenem
Container**:

```json
{
  "device_id": "box1",
  "docker_available": true,
  "memory_stats_available": false,
  "services": [
    {
      "service": "backend",
      "container": "minabox-backend",
      "state": "online",
      "docker_status": "running",
      "health": "healthy",
      "version": "0.1.0",
      "git_sha": "49427d3",
      "image": "ghcr.io/opnek90/minabox-backend:0.1.0",
      "restart_count": 0,
      "cpu_percent": 4.2,
      "memory_mb": null,
      "memory_percent": null
    }
  ]
}
```

### Die Liste ist dynamisch

Frueher stand im Backend eine feste Liste aus acht Namen. Sie war unvollstaendig
(**host-helper** und **media-downloader** fehlten) und blind fuer die Profile:
eine Box ohne LED-Profil zeigte dauerhaft "led: offline", obwohl dort nie ein
LED-Container existiert hat.

Jetzt fragt das Backend Docker nach allen Containern mit dem Label
`com.docker.compose.project` des eigenen Projekts. Was da ist, wird angezeigt;
was ein Profil nie gestartet hat, taucht nicht auf.

> **Fallstrick:** Compose schreibt `project` und `service` nicht nur auf den
> Container, sondern auch in das **Image**, das es baut. Jeder von Hand
> gestartete Container aus einem Minabox-Image bringt diese Labels also mit und
> erschiene als zweiter Eintrag desselben Dienstes - beobachtet mit einem
> `docker run` des Backend-Images, das prompt als zweites "backend" in der
> Liste stand. Deshalb zaehlt zusaetzlich das Label
> `com.docker.compose.container-number`: das schreibt Compose erst, wenn es
> einen Container wirklich anlegt. `docker compose run`-Wegwerfcontainer
> (`oneoff=True`) fallen ebenfalls heraus. Der alte Katalog in
`routes_system.py` bleibt als **Anzeigereihenfolge** und als **Rueckfallebene**
erhalten, wenn der Docker-Socket nicht nutzbar ist. Auf dieser Rueckfallebene
gibt es keine CPU- und RAM-Werte; die Oberflaeche sagt das dann auch
(`docker_available: false`).

### Zustaende

| Docker-Status | Health | Anzeige |
|---|---|---|
| running | healthy / keiner | online |
| running | starting | online |
| running | unhealthy | Fehler |
| restarting / exited / dead | - | Fehler |
| created / paused | - | offline |

`starting` gilt bewusst als online: waehrend der `start_period` laeuft der
Container und tut das Richtige. Ihn offline zu nennen liesse jeden Neustart
wie einen Ausfall aussehen.

### CPU, RAM und Logs fuer alle

Alle drei Werte kommen jetzt fuer **jeden** Container, auch fuer `mqtt` (frueher
ausdruecklich ausgenommen) und die beiden neu aufgenommenen Dienste. Die Logs
werden ueber den Container-Namen aufgeloest, den Docker meldet, nicht mehr ueber
eine feste Tabelle.

### RAM ist nicht ueberall messbar

Raspberry Pi OS liefert den memory-cgroup-Controller standardmaessig
abgeschaltet aus. Dann gibt es **gar keinen** Speicherwert pro Container -
auch `docker stats` zeigt auf so einem Host `0B / 0B`. Vorher wurde daraus in
der Oberflaeche "0.0 MB", eine Luecke im Kostuem einer Messung.

Jetzt meldet die API in diesem Fall `null` statt `0`, setzt
`memory_stats_available: false`, und die Oberflaeche schreibt hin, woran es
liegt. Abhilfe auf dem Pi:

```bash
sudo sed -i '1s/$/ cgroup_memory=1 cgroup_enable=memory/' /boot/firmware/cmdline.txt
```

Danach neu starten. (Der Hinweis in `docker-compose.yml` zu den
Ressourcen-Limits beschreibt denselben Schalter.)

**Worauf sich der Prozentwert bezieht**, haengt vom Aufbau ab: Docker meldet
das Speicherlimit des Containers, und wo keines gesetzt ist - der Normalfall
hier - ist das der gesamte Arbeitsspeicher des Hosts. "129 MB · 3.4 %" heisst
also heute "3,4 % des Systemspeichers". Werden spaeter Limits je Container
gesetzt, wird daraus "3,4 % des Budgets dieses Containers".

---

## 5. Welches Image auf der Box laeuft

`docker-compose.yml` loest den Tag jedes Dienstes von fein nach grob auf:

```yaml
image: ghcr.io/opnek90/minabox-backend:${MINABOX_BACKEND_TAG:-${MINABOX_IMAGE_TAG:-latest}}
```

1. `MINABOX_<DIENST>_TAG` - gilt nur fuer diesen Dienst,
2. `MINABOX_IMAGE_TAG` - gilt fuer alle ohne eigenen Eintrag,
3. `latest` - folgt dem main-Branch.

Mit einer Nummer pro Dienst reicht eine einzige globale Variable nicht mehr
aus: "Backend 0.1.2, Audio 0.1.0" laesst sich darin nicht ausdruecken. Erst
die Ebene je Dienst macht ein gezieltes Update moeglich - und den Weg zurueck,
wenn eine Version Aerger macht:

```bash
# Nur das Backend auf die vorige Version zurueckdrehen
echo "MINABOX_BACKEND_TAG=0.1.1" >> .env
docker compose up -d backend
```

### Was das Update in der .env aendert

Ein gezieltes Update (der Knopf unter *Wartung*) schreibt diese Zeilen selbst.
Dabei setzt es **alle** Dienste auf eine feste Nummer, nicht nur die, die es
anfasst: die betroffenen auf ihre neue Version, die uebrigen auf die, die sie
gerade fahren.

Das ist Absicht. Bliebe der Rest auf `latest`, wuerde der naechste
`docker compose up -d` sie beilaeufig mitziehen - und ein gezieltes Update
waere keins. Nach dem ersten Update laeuft eine Box also auf festen Nummern
statt auf `latest`; was sie faehrt, steht in der `.env` und ist damit
nachlesbar und umkehrbar.

### Sicherung

Vor jedem Update legt der Host-Helper eine Sicherung unter `data/backups/`
ab (Datenbank, Einstellungen, Dienst-Zustaende); die letzten fuenf bleiben
erhalten. Schlaegt sie fehl, wird nicht aktualisiert.

### Die Datenbank hat eine eigene Nummer

Beim Update werden die Container ausgetauscht, die Datenbank nicht:
`data/minabox.db` liegt auf der Karte und ueberlebt jedes Update. Neuer Code
trifft also auf alte Daten - und beim Zurueckdrehen alter Code auf neue.

Vorwaerts ist das loesbar. `db_manager` ergaenzt beim Start, was fehlt:

```sql
ALTER TABLE tracks ADD COLUMN cover_art_url VARCHAR(512)
```

Eine aeltere Fassung, die diese Spalte spaeter vorfindet, ignoriert sie
einfach. Harmlos in beide Richtungen.

Nicht harmlos ist der zweite Fall. `_migrate_stream_tracks_to_streams`
verschiebt Radiostreams aus der Tabelle `tracks` in die Tabelle `streams` -
**und loescht sie in `tracks`**. Eine Fassung von davor sucht Streams weiter in
`tracks`, findet nichts und meldet sie als verschwunden. Die Daten sind nicht
zerstoert, aber sie liegen an einer Stelle, an der diese Fassung nie
nachschaut. Legt der Nutzer sie daraufhin neu an, stehen sie danach doppelt da.

`SCHEMA_VERSION` in [db_manager.py](../services/backend-service/src/backend_service/core/db_manager.py)
macht diesen Unterschied sichtbar. Der Stand steht in `PRAGMA user_version` -
ein Feld im Dateikopf, das SQLite selbst mitbringt; es braucht also keine
eigene Tabelle, und eine Datenbank aus der Zeit davor liefert schlicht 0.

| Datenbank | Code erwartet | Was passiert |
|---|---|---|
| 0 oder aelter | 1 | Migrationen laufen, danach wird gestempelt |
| 1 | 1 | nichts zu tun |
| 2 | 1 | **erkannt**: Hinweisbalken, `/health` meldet `unhealthy` |

Im dritten Fall wird **nicht** abgebrochen. Eine Box, die gar nicht mehr
startet, laesst sich auch nicht mehr diagnostizieren - und der Hinweis waere
dann nirgends zu lesen. Stattdessen laeuft sie an und sagt unuebersehbar, was
los ist. Der Stempel wird dabei nicht zurueckgesetzt: sonst waere aus einer
erkannten Lage beim naechsten Start wieder eine unbemerkte geworden.

**Wann die Zahl steigt:** sobald eine Aenderung nicht mehr
rueckwaertskompatibel ist - Daten ziehen um, Spalten oder Tabellen
verschwinden, oder ihre Bedeutung wechselt. Eine neue Spalte, die aeltere
Fassungen einfach ignorieren, braucht keine Anhebung.

Der Nutzen liegt nicht nur beim Zurueckdrehen. Dieselbe Pruefung greift, wenn
eine Sicherung eingespielt wird, die neuer ist als der laufende Code, oder
wenn ein Container beim Update nicht durchgestartet ist und weiter die alte
Fassung faehrt.

### Warum es keinen Knopf "zurueck auf die vorige Version" gibt

Technisch waere er einfach - derselbe Vorgang mit aelteren Nummern. Er wurde
bewusst wieder entfernt.

Ein Rueckschritt ist nur dann harmlos, wenn die aeltere Fassung alles lesen
kann, was die neuere geschrieben hat. Seit es `SCHEMA_VERSION` gibt, laesst
sich das immerhin *erkennen* - aber erkennen heisst nicht reparieren: bei
einem Sprung ueber eine unvertraegliche Aenderung hinweg bliebe nur die
Meldung, dass es nicht geht. Ein Knopf, der einen Rueckweg verspricht und ihn
dann in genau den Faellen verweigert, in denen man ihn braucht, hilft
niemandem - und er wuerde ausgerechnet in dem Moment gedrueckt, in dem ohnehin
etwas schiefgegangen ist.

Wer wirklich zurueck muss, hat den ehrlichen Weg: die Sicherung von vor dem
Update ueber *Wiederherstellen* einspielen und den Tag in der `.env` von Hand
setzen. Das ist ein bewusster Eingriff mit einem passenden Datenstand - kein
Knopf, der Einfachheit vortaeuscht.

## 6. Einen Dienst veroeffentlichen

```bash
# 1. Version anheben
echo "0.2.0" > services/audio-service/VERSION

# 2. Changelog-Eintrag in BEIDEN Sprachen
#    CHANGELOG.md und CHANGELOG.en.md, Abschnitt "## audio"

# 3. Manifest neu erzeugen
python3 scripts/build_manifest.py

# 4. Commit und Push auf main - die CI baut und schiebt :0.2.0, :0.2, :latest
git commit -am "feat(audio): Sleep-Timer, Version 0.2.0"
```

Schritt 2 und 3 sind nicht optional: die CI prueft mit
`build_manifest.py --check`, ob `release-manifest.json` zu den Changelogs
passt und ob die aktuelle Version jedes Dienstes dort beschrieben ist.
Fehlt etwas, wird gar nicht erst gebaut.

Die Changelogs sind die einzige Quelle; das Manifest wird daraus erzeugt und
mitcommittet. Es liegt bewusst im Repo und wird nicht von der CI
zurueckgeschrieben - das spart Schreibrechte fuer den Workflow und einen
Commit-Kreislauf, und die Datei ist im Diff sichtbar wie jede andere.

Auf der Box wird die neue Nummer sichtbar, sobald der Container mit dem neuen
Image laeuft. Zeigt ein Dienst nach einem Update noch die alte Version, ist
sein Container nicht neu gestartet worden - genau diese Abweichung soll die
Anzeige sichtbar machen.

## 7. Lokal entwickeln

`docker compose build` setzt keine Build-Args. Alle so gebauten Images melden
`0.0.0-dev`, und die Oberflaeche zeigt "Entwicklungsbuild". Wer eine Nummer
sehen will, reicht sie durch:

```bash
docker compose build --build-arg APP_VERSION=0.2.0-test audio
```
