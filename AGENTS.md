# AGENTS.md — Entwicklungs- und Deployment-Workflow fuer KI-Agenten

Dieses Dokument ist fuer **jeden** Coding-Agenten gedacht, der an Minabox
arbeitet — Claude Code, OpenAI Codex, Cursor, Aider und andere. Es beschreibt
verbindlich den Weg von einer Aenderung bis zu dem Moment, in dem der Nutzer auf
seiner Box *Aktualisieren* druecken kann.

Es ist bewusst selbsttragend: Du musst kein anderes Dokument gelesen haben, um es
anzuwenden. Tiefergehende Begruendungen stehen in
[docs/Entwicklungs-Workflow.md](docs/Entwicklungs-Workflow.md),
[docs/Versionierung.md](docs/Versionierung.md) und
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Bei Widerspruch gilt: dieses Dokument
und `docs/Entwicklungs-Workflow.md` schlagen aeltere Beschreibungen.

Fuer Claude Code fasst zusaetzlich `CLAUDE.md` dieselben Regeln kurz — Inhalt ist
deckungsgleich mit diesem Dokument.

---

## 0. Die drei Regeln ohne Ausnahme

1. **Jede Aenderung auf einem eigenen Branch.** Ausnahmslos, auch eine Zeile
   Doku. Niemals direkt auf `main` committen. `main` bleibt damit ein Stand, der
   durchgesehen wurde.

2. **Keine Versionsbumps waehrend der Arbeit.** `VERSION`-Dateien, `CHANGELOG*`
   und `release-manifest.json` werden **gebuendelt** angefasst — erst bei der
   Freigabe (Phase C), erst nachdem der Nutzer ausdruecklich „passt alles" (oder
   sinngemaess) gesagt hat. Wer waehrend der Arbeit bumpt, produziert bei jedem
   Rebase Konflikte in genau den Dateien, die sich am schlechtesten
   zusammenfuehren lassen.

3. **Nie selbst auf der Box ausrollen.** Kein `docker compose pull` auf die
   veroeffentlichten Tags, kein `docker compose up -d` auf Release-Images, kein
   Aufruf eines Update-Endpunkts, kein Anfassen der `.env`-Tags auf der laufenden
   Box. Der Agent baut, prueft, merged und veroeffentlicht — aber er drueckt
   nicht auf *Aktualisieren*. Das loest der Nutzer selbst ueber die WebUI aus
   (*Wartung → Version & Update*).

Wenn eine Anweisung des Nutzers einer dieser Regeln widerspricht, weise einmal
kurz darauf hin und lass ihn entscheiden.

---

## 1. Sprache und Konventionen

- **Chat-Antworten und Doku: Deutsch.** Auch dieses Repo dokumentiert auf
  Deutsch.
- **Git-Artefakte: Englisch.** Commit-Betreff und -Body, Branch-Namen,
  PR-Titel/-Body und Tags immer auf Englisch.
- **Umlaute in Quelltext ausschreiben.** In `.py`- und `.sh`-Dateien (Code wie
  Kommentare) sowie in Commit-Betreffen: `ae`, `oe`, `ue`, `ss`. In
  Markdown-Doku sind echte Umlaute erlaubt.
- **Conventional Commits.** Betreff-Praefixe `feat`, `fix`, `docs`, `ci`,
  `refactor`, `chore`, `test`. Dieselben Praefixe fuer Branch-Namen:
  `feat/<kurz>`, `fix/<kurz>`, …

---

## 2. Repo-Fakten, die den Workflow bestimmen

- **Monorepo mit neun ausgelieferten Diensten** unter `services/`:
  `backend`, `host-helper`, `audio`, `rfid`, `button`, `led`, `display`,
  `media-downloader`, `webui`. Dazu `services/shared-lib/` (Python-Bibliothek,
  von allen ausser `webui` eingebunden) — kein eigenes Image.
- **Jeder Dienst hat seine eigene Versionsnummer** in
  `services/<name>-service/VERSION` (z. B. `0.2.8`). Es gibt keine globale
  Version. Details: [docs/Versionierung.md](docs/Versionierung.md).
- **Die CI baut nur auf `main`.** Auf einem Branch baut die CI **nichts** —
  Images entstehen erst nach dem Merge. Der Merge auf `main` startet die CI von
  selbst; sie baut nur die geaenderten Dienste und published nach
  `ghcr.io/opnek90/minabox-<name>`.
- **Die Box ist auf feste Versionen festgenagelt.** Nach einem Update ueber die
  Oberflaeche steht in der `.env` der Box fuer jeden Dienst
  `MINABOX_<DIENST>_TAG=<version>`. `docker compose pull` holt genau diese und
  aendert sonst nichts.
- **GitHub-Repo:** `Opnek90/Minabox` (Remote `origin`,
  `git@github.com:Opnek90/Minabox.git`).
- **Python-Umgebung:** `.venv/` im Repo-Wurzelverzeichnis. Kein `pip install`
  noetig; Dev-Abhaengigkeiten sind installiert.

---

## 3. Phase A — Branch anlegen und arbeiten

```bash
git checkout main && git pull --ff-only
git checkout -b feat/<kurzbeschreibung>       # feat|fix|docs|ci|refactor|chore
```

Arbeiten. Commits mit Conventional-Commit-Betreff auf Englisch. Keine
`VERSION`-, `CHANGELOG*`- oder `release-manifest.json`-Aenderungen (Regel 2).

Wenn es bereits uncommittete Aenderungen auf einem anderen Branch gibt, die
nicht zu deiner Aufgabe gehoeren: nicht mitnehmen. Entweder in einem separaten
`git worktree` arbeiten oder den Nutzer fragen, wie er die offene Arbeit
behandelt haben moechte.

---

## 4. Phase B — Pruefen (vor der Freigabe, lokal)

### 4.1 Was Sekunden kostet — immer

```bash
# Alle Python-Tests (PYTHONPATH deckt jeden Dienst ab)
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest -q

# ruff NUR ueber die beruehrten Dateien
.venv/bin/ruff check <beruehrte .py-Dateien>

# TypeScript der WebUI — muss fehlerfrei durchlaufen
cd services/webui-service && npx tsc --noEmit
```

Hinweise:

- `ruff` **nicht** ueber das ganze Verzeichnis laufen lassen — es meldet mehrere
  hundert Altbefunde. Nur deine geaenderten Dateien.
- `npx tsc --noEmit` muss **leere Ausgabe** liefern. Der WebUI-Bau selbst nutzt
  `build:fast` und ueberspringt `tsc`, daher blockiert ein Fehler den Bau nicht —
  die Ausgabe soll trotzdem leer bleiben.
- Schlagen Tests fehl oder ist die Ausgabe nicht leer: melden, nicht
  weitermachen.

### 4.2 Nur die beruehrten Dienste bauen — nie alle neun

```bash
./scripts/build-local.sh backend webui        # nur die geaenderten Dienste
```

Das Skript baut unter dem Tag `:local` (nicht `:latest`) mit den Versionsnummern
aus den `VERSION`-Dateien und einem `+local`-Suffix. Zum Ausprobieren die
Tag-Variable **nur fuer den einen Aufruf** setzen — eine Shell-Variable sticht
die `.env`, es muss keine Datei angefasst werden:

```bash
MINABOX_WEBUI_TAG=local docker compose up -d webui   # lokalen Bau starten
# ... ausprobieren ...
docker compose up -d webui                           # zurueck auf den echten Stand
```

`build-local.sh` gibt beide Befehle nach dem Bau passend fertig aus. Ein lokal
gebautes Abbild erscheint in der Dienste-Uebersicht als `X.Y.Z+local`.

**Warum `:local` und nicht `:latest`:** Steht in der `.env` eine feste Version,
zieht Compose genau diese — ein lokal gebautes `:latest` wuerde nie benutzt, und
man testet ahnungslos den alten Stand.

Beobachtete Bauzeiten auf einem Pi 4 mit kaltem Cache: Backend ~5 min, WebUI
~4 min, Host-Helper ~3 min. Mit warmem Cache ein Bruchteil.

### 4.3 Lokalen Bau verifizieren

`docker compose ps` zeigt den in der Compose-Datei deklarierten Image-Namen, nicht
zwingend das, was wirklich laeuft. Zum Gegenpruefen:

```bash
docker inspect --format '{{.Config.Image}}' minabox-webui
```

---

## 5. Phase C — Freigabe (erst auf „passt alles")

**Nicht anfangen, bevor der Nutzer die Aenderung abgenommen hat.**

### 5.1 Betroffene Dienste ermitteln

```bash
git diff --name-only main...HEAD
```

Alles unter `services/<name>-service/` zaehlt. Zwei Faelle greifen weiter, als der
Pfad vermuten laesst:

- Aenderungen an `services/shared-lib/**` betreffen **jeden** Dienst, der die
  Bibliothek einbindet (alle ausser `webui`).
- Eine Aenderung am **MQTT-Vertrag** betrifft beide Seiten — Sender und
  Empfaenger.

### 5.2 Release-Schritte (alles in EINEN Release-Commit)

1. **`services/<dienst>-service/VERSION`** je betroffenem Dienst um **+0.0.1**
   anheben. Etwas anderes (Minor/Major) nur, wenn der Nutzer es ausdruecklich
   sagt.

2. **Release Notes** in `CHANGELOG.md` **und** `CHANGELOG.en.md` — ein Satz aus
   Nutzersicht, kein Commit-Betreff. Format:

   ```markdown
   ## backend

   ### 0.1.7 - 2026-08-22

   #### Behoben
   - Ein Satz aus Nutzersicht.
   ```

   Abschnitte: `Neu` / `Verbessert` / `Behoben` bzw. `Added` / `Improved` /
   `Fixed`. Eine Version ohne sichtbare Aenderung darf leer bleiben — die
   Oberflaeche zeigt dann „keine Aenderungsnotizen" statt einer erfundenen Zeile.
   Beide Sprachdateien muessen denselben Versionsstand beschreiben.

3. **`SCHEMA_VERSION`** in
   `services/backend-service/src/backend_service/core/db_manager.py` anheben,
   **falls** eine Aenderung am Datenmodell nicht rueckwaertskompatibel ist (Daten
   ziehen um, Spalten/Tabellen verschwinden, Bedeutung wechselt). Eine neue
   Spalte allein braucht keine Anhebung.

4. **Manifest neu erzeugen** und mitcommitten:

   ```bash
   python3 scripts/build_manifest.py
   git add release-manifest.json
   ```

5. **Alles als EIN Release-Commit** auf den Branch, z. B.:

   ```
   chore(release): backend 0.1.7, webui 0.3.1
   ```

### 5.3 Nur-Doku-Aenderung

Kein Bump, kein Changelog, kein Manifest, kein Bau — die CI meldet „Zu bauen:
nichts". Der eigene Branch bleibt trotzdem Pflicht.

---

## 6. Phase D — Pull Request

```bash
git push -u origin <branch>
gh pr create --fill
gh pr merge --merge --delete-branch
git checkout main && git pull --ff-only
git remote prune origin
```

- `--merge` (kein Squash/Rebase). `--delete-branch` raeumt den Branch remote und
  lokal weg. `git remote prune origin` entfernt die verwaiste
  Remote-Tracking-Referenz.
- Der PR bleibt als Nachweis stehen, auch wenn er sofort gemergt wird.
- **`gh` ist nicht angemeldet?** Die einmalige `gh auth login` macht der Nutzer
  selbst — Zugangsdaten gehoeren nicht in eine Agentensitzung. Solange sie fehlt,
  endet der Ablauf mit einem PR-Link zum Anklicken:
  `https://github.com/Opnek90/Minabox/compare/main...<branch>?expand=1`

---

## 7. Phase E — Bau und Uebergabe

Der Merge auf `main` startet die CI **von selbst**. Es gibt keinen Schritt
„Images bauen lassen". Gebaut werden nur die geaenderten Dienste.

```bash
gh run watch          # bis der Lauf durch ist
```

Danach pruefen, dass die Versions-Tags in GHCR liegen, und dem Nutzer sagen, dass
das Update bereitsteht. **Dann aufhoeren.** Der Nutzer drueckt selbst auf
*Aktualisieren* (Regel 3).

---

## 8. Die Waechter (was passiert, wenn du einen Schritt vergisst)

Der Ablauf verlaesst sich nicht auf Disziplin allein:

| Vergessen | Was passiert |
|---|---|
| Versionsbump | CI bricht ab: der Versions-Tag ist schon vergeben, mit Hinweis auf die `VERSION`-Datei. |
| Changelog-Eintrag | `build_manifest.py --check` laeuft in der CI und **verhindert den Bau** — die aktuelle Version jedes Dienstes muss beschrieben sein. |
| Uebersetzung (nur eine Sprache) | Derselbe Waechter bricht ab. |
| Manifest nicht neu erzeugt | Derselbe Waechter. |
| Dienstname vertippt | Der Waechter nennt die gueltigen Namen. |

**Nicht abgefangen** wird ein Fehler, den erst der laufende Container zeigt.
Dagegen hilft nur Phase B.

---

## 9. Konventionen im Code

### Container-Healthcheck

Jeder Dienst prueft seine Gesundheit mit **`curl -f`** gegen den eigenen
`/health`-Endpunkt — im `HEALTHCHECK` des Dockerfiles **und** im
`healthcheck:`-Block der `docker-compose.yml` (beide muessen uebereinstimmen, der
Compose-Eintrag ueberschreibt den des Images):

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:<port>/health || exit 1
```

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:<port>/health"]
```

Ein `python -c`-Einzeiler statt `curl` ist **keine Option** (Begruendung in
[docs/Entwicklungs-Workflow.md](docs/Entwicklungs-Workflow.md), Abschnitt
„Container-Healthcheck").

---

## 10. Sonderfaelle

- **Etwas ist nach dem Update kaputt.** Es gibt bewusst keinen Rueckweg-Knopf.
  Der Weg: die Sicherung von vor dem Update ueber *Wiederherstellen* einspielen
  und den Tag in der `.env` von Hand setzen — **durch den Nutzer**, nicht durch
  den Agenten.
- **Aenderung am MQTT-Vertrag oder an `shared-lib`.** Alle abhaengigen Dienste
  bumpen und im Changelog beschreiben (siehe 5.1).
- **Mehrere Dienste gleichzeitig geaendert.** Jeder betroffene Dienst bekommt
  seinen eigenen Bump und seinen eigenen Changelog-Abschnitt, alles in einem
  Release-Commit.

---

## 11. Schnell-Checkliste

**Waehrend der Arbeit:**

- [ ] Eigener Branch, Conventional-Commit-Betreffe auf Englisch
- [ ] Keine `VERSION` / `CHANGELOG*` / `release-manifest.json` angefasst
- [ ] `pytest -q` gruen
- [ ] `ruff check <beruehrte Dateien>` sauber
- [ ] `npx tsc --noEmit` in `services/webui-service` mit leerer Ausgabe
- [ ] Nur beruehrte Dienste lokal gebaut und ausprobiert

**Freigabe (erst auf „passt alles"):**

- [ ] Betroffene Dienste ermittelt (`git diff --name-only main...HEAD` + shared-lib/MQTT)
- [ ] `VERSION` je Dienst +0.0.1
- [ ] `CHANGELOG.md` **und** `CHANGELOG.en.md` — ein Satz aus Nutzersicht
- [ ] `SCHEMA_VERSION` geprueft/angehoben, falls Datenmodell inkompatibel
- [ ] `python3 scripts/build_manifest.py`, `release-manifest.json` committet
- [ ] Ein einziger Release-Commit
- [ ] `git push`, `gh pr create --fill`, `gh pr merge --merge --delete-branch`
- [ ] `gh run watch` abgewartet, Tags in GHCR geprueft
- [ ] Dem Nutzer Bescheid gegeben — **Update loest er selbst aus**
