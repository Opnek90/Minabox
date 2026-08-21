# Entwicklungs- und Ausliefer-Workflow

Der Weg von einer Idee bis zu dem Moment, in dem der Nutzer auf seiner Box
*Aktualisieren* drücken kann. Die Kurzfassung steht in [../CLAUDE.md](../CLAUDE.md)
und wird von jeder Claude-Code-Sitzung automatisch gelesen; hier stehen die
Begründungen und die Fälle, in denen es klemmt.

Zwei Dokumente daneben: [Versionierung.md](Versionierung.md) erklärt, warum jeder
Dienst eine eigene Nummer hat und wie sie ins Image kommt.
[Release-Update-Workflow.md](Release-Update-Workflow.md) ist der Entwurf, aus dem
das alles entstanden ist.

---

## Die drei Regeln

**1. Jede Änderung auf einem eigenen Branch.** Ausnahmslos, auch für eine Zeile
Doku. `main` bleibt damit ein Stand, der durchgesehen wurde.

**2. Keine Versionsbumps während der Arbeit.** VERSION, Changelog und Manifest
kommen gebündelt bei der Freigabe. Wer während der Arbeit bumpt, hat bei jedem
Rebase Konflikte in genau den drei Dateien, die sich am schlechtesten
zusammenführen lassen.

**3. Das Update auf der Box löst der Nutzer aus.** Der Assistent baut, prüft,
merged und veröffentlicht — aber er drückt nicht auf *Aktualisieren*. Wer eine
Box aus der Ferne aktualisiert, nimmt ihrem Besitzer die Gelegenheit, den Verlauf
zu sehen und im Zweifel abzubrechen.

---

## Phase A — Arbeiten

```bash
git checkout main && git pull --ff-only
git checkout -b feat/<kurzbeschreibung>
```

Branch-Präfixe wie die Commit-Präfixe: `feat`, `fix`, `docs`, `ci`, `refactor`.
Commits mit Conventional-Commit-Betreff, auf Deutsch, Umlaute in Quelltext und
Commit-Betreff ausgeschrieben (`ae`, `oe`, `ue`).

## Phase B — Prüfen

Zuerst das, was Sekunden kostet:

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest -q
.venv/bin/ruff check <berührte .py-Dateien>
cd services/webui-service && npx tsc --noEmit
```

Zu den Ausnahmen: `tsc` meldet acht Fehler, die aus der Zeit vor
diesen Regeln stammen; sie gehören zum Bestand. Der Bau der WebUI benutzt
`build:fast` und überspringt `tsc`, deshalb blockieren sie nichts — neue Fehler
dürfen trotzdem nicht dazukommen. `ruff` läuft nur über die berührten Dateien:
über das ganze Verzeichnis meldet es mehrere hundert Altbefunde.

Dann die berührten Dienste bauen:

```bash
./scripts/build-local.sh webui backend        # nur die geänderten, nie alle neun
```

Beobachtete Bauzeiten auf einem Pi 4, kalter Cache: Backend rund fünf Minuten,
WebUI vier, Host-Helper drei. Mit warmem Cache ein Bruchteil davon. Alle neun zu
bauen dauert entsprechend lange und ist fast nie nötig.

### Warum `:local` und nicht `:latest`

Nach einem Update über die Oberfläche steht in der `.env` für jeden Dienst eine
feste Version (`MINABOX_<DIENST>_TAG`). Compose zieht dann genau diese — ein lokal
gebautes `:latest` würde **nie benutzt**, und man testet ahnungslos den alten
Stand. Deshalb baut das Skript unter `:local`, und der Testaufruf setzt die
Variable nur für diesen einen Befehl. Eine Shell-Variable sticht die `.env`, es
muss also keine Datei angefasst werden:

```bash
MINABOX_WEBUI_TAG=local docker compose up -d webui
# … ausprobieren …
docker compose up -d webui        # zurück auf den veröffentlichten Stand
```

Das Skript gibt beide Befehle nach dem Bau fertig aus. In der Dienste-Übersicht
steht ein lokal gebautes Abbild als `X.Y.Z+local` — daran ist erkennbar, dass dort
kein Release läuft.

## Phase C — Freigabe

**Erst wenn der Nutzer „passt alles" sagt.**

Betroffene Dienste ermitteln:

```bash
git diff --name-only main...HEAD
```

Alles unter `services/<name>-service/` zählt. Zwei Fälle greifen weiter, als der
Pfad vermuten lässt: Änderungen an `services/shared-lib/**` betreffen jeden Dienst,
der sie einbindet (alle außer webui), und eine Änderung am MQTT-Vertrag betrifft
beide Seiten, Sender und Empfänger.

1. **VERSION** je betroffenem Dienst um **0.0.1** anheben. Etwas anderes nur, wenn
   der Nutzer es ausdrücklich sagt — etwa ein neues Major-Release.
2. **Release Notes** in `CHANGELOG.md` *und* `CHANGELOG.en.md`:

   ```markdown
   ## backend

   ### 0.1.7 - 2026-08-22

   #### Behoben
   - Ein Satz aus Nutzersicht, kein Commit-Betreff.
   ```

   Abschnitte: `Neu` / `Verbessert` / `Behoben` bzw. `Added` / `Improved` / `Fixed`.
   Eine Version ohne sichtbare Änderung darf leer bleiben; die Oberfläche zeigt dann
   „keine Änderungsnotizen" statt einer erfundenen Zeile.
3. **`SCHEMA_VERSION`** in
   `services/backend-service/src/backend_service/core/db_manager.py` anheben, falls
   eine Änderung am Datenmodell nicht rückwärtskompatibel ist — Daten ziehen um,
   Spalten oder Tabellen verschwinden, Bedeutung wechselt. Eine neue Spalte allein
   braucht keine Anhebung. Begründung in [Versionierung.md](Versionierung.md).
4. **Manifest erzeugen:** `python3 scripts/build_manifest.py`, das erzeugte
   `release-manifest.json` mitcommitten.
5. Alles als **ein** Release-Commit auf den Branch.

## Phase D — Pull Request

```bash
git push -u origin <branch>
gh pr create --fill
gh pr merge --merge --delete-branch
git checkout main && git pull --ff-only
git remote prune origin
```

`--delete-branch` räumt den Branch remote und lokal weg. Der PR bleibt als
Nachweis stehen, auch wenn er sofort gemergt wird. `git remote prune origin`
entfernt die dann verwaiste Remote-Tracking-Referenz (`origin/<branch>`), die
sonst lokal stehen bleibt.

## Phase E — Bau und Übergabe

Der Merge auf `main` startet die CI **von selbst**; es gibt keinen Schritt
„Images bauen lassen". Gebaut werden nur die geänderten Dienste.

```bash
gh run watch          # bis der Lauf durch ist
```

Danach prüfen, dass die Versions-Tags in GHCR liegen, und dem Nutzer sagen, dass
das Update bereitsteht. **Dann aufhören.** Er drückt selbst.

---

## Die Wächter

Der Ablauf verlässt sich nicht auf Disziplin. Wer einen Schritt vergisst, merkt es:

| Vergessen | Was passiert |
|---|---|
| Versionsbump | Die CI bricht ab: der Versions-Tag ist bereits vergeben, mit Hinweis auf die VERSION-Datei. |
| Changelog-Eintrag | `build_manifest.py --check` läuft in der CI und **verhindert den Bau** — die aktuelle Version jedes Dienstes muss beschrieben sein. |
| Übersetzung | Derselbe Wächter: fehlt ein Eintrag in einer der beiden Sprachen, bricht er ab. |
| Manifest nicht neu erzeugt | Ebenfalls derselbe Wächter. |
| Dienstname vertippt | Der Wächter nennt die gültigen Namen. |

Nicht abgefangen wird: ein Fehler, den erst der laufende Container zeigt. Dagegen
hilft nur Phase B.

---

## Sonderfälle

**Nur Doku geändert.** Kein Bump, kein Changelog, kein Bau — die CI meldet
„Zu bauen: nichts". Der Branch bleibt trotzdem Pflicht.

**`gh` ist nicht angemeldet.** Die einmalige Anmeldung (`gh auth login`) macht der
Nutzer selbst; Zugangsdaten gehören nicht in eine Assistenzsitzung. Solange sie
fehlt, endet der Ablauf mit einem PR-Link zum Anklicken:
`https://github.com/Opnek90/Minabox/compare/main...<branch>?expand=1`

**Etwas ist nach dem Update kaputt.** Es gibt bewusst keinen Rückweg-Knopf
([Versionierung.md](Versionierung.md) erklärt, warum). Der Weg ist: die Sicherung
von vor dem Update über *Wiederherstellen* einspielen und den Tag in der `.env`
von Hand setzen.
