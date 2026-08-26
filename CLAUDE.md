# Minabox — Arbeitsweise

Ausführlich: [docs/Entwicklungs-Workflow.md](docs/Entwicklungs-Workflow.md)

## Drei Regeln ohne Ausnahme

1. **Jede Änderung auf einem eigenen Branch** — auch eine Zeile Doku. Nie direkt
   auf `main` committen.
2. **Keine Versionsbumps während der Arbeit.** VERSION, Changelog und Manifest
   kommen gebündelt, erst wenn der Nutzer „passt alles" sagt.
3. **Nie selbst auf der Box ausrollen.** Kein `docker compose pull`, kein `up -d`
   auf die veröffentlichten Tags, kein Aufruf des Update-Endpunkts. Das Update
   löst der Nutzer über die WebUI aus (*Wartung → Version & Update*).

## Ablauf

```bash
git checkout main && git pull --ff-only
git checkout -b feat/<kurz>          # feat|fix|docs|ci|refactor
```

Arbeiten, Conventional-Commit-Betreffe. Prüfen — erst ohne Container:

```bash
PYTHONPATH=$(ls -d services/*/src | tr '\n' ':') .venv/bin/python -m pytest -q
.venv/bin/ruff check <berührte .py-Dateien>
cd services/webui-service && npx tsc --noEmit     # muss fehlerfrei durchlaufen
```

Dann nur die **berührten** Dienste bauen und ausprobieren (nie alle neun):

```bash
./scripts/build-local.sh webui
MINABOX_WEBUI_TAG=local docker compose up -d webui
docker compose up -d webui           # zurück auf den veröffentlichten Stand
```

## Freigabe — erst auf „passt alles"

Betroffene Dienste ermitteln: `git diff --name-only main...HEAD` → alles unter
`services/<name>-service/`. Änderungen an `services/shared-lib/**` oder am
MQTT-Vertrag betreffen **alle** abhängigen Dienste.

- [ ] `services/<dienst>-service/VERSION` je betroffenem Dienst **+0.0.1**
      (anderes nur, wenn der Nutzer es sagt)
- [ ] Eintrag in `CHANGELOG.md` **und** `CHANGELOG.en.md`, ein Satz aus
      Nutzersicht
- [ ] `SCHEMA_VERSION` in `db_manager.py` anheben, falls eine Änderung am
      Datenmodell nicht rückwärtskompatibel ist
- [ ] `python3 scripts/build_manifest.py`, `release-manifest.json` mitcommitten
- [ ] alles als **ein** Release-Commit

Dann PR anlegen und mergen:

```bash
git push -u origin <branch>
gh pr create --fill
gh pr merge --merge --delete-branch
git checkout main && git pull --ff-only
git remote prune origin
```

Der Merge startet die CI von selbst; sie baut nur die geänderten Dienste
(`gh run watch`). Danach dem Nutzer sagen, dass das Update bereitsteht — **und
es ihm überlassen.**

## Wichtig zu wissen

- Jeder Dienst hat seine **eigene** Versionsnummer: `docs/Versionierung.md`.
- Auf einem Branch baut die CI **nichts** — Images gibt es erst nach dem Merge.
- Die Box ist auf feste Versionen festgenagelt (`MINABOX_<DIENST>_TAG` in `.env`).
  `docker compose pull` holt genau diese und ändert sonst nichts.
- Antworten auf Deutsch, Code-Kommentare und Doku ebenso (Umlaute in `.py`/`.sh`
  ausgeschrieben: `ae`, `oe`, `ue`).
