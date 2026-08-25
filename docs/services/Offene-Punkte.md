# Dienstuebergreifende offene Punkte

Befunde, die beim Review eines Dienstes aufgetaucht sind, aber **andere oder
alle** Dienste betreffen. Sie stehen hier statt im Review des einzelnen
Dienstes, weil sie dort nur zufaellig gefunden wurden und in einem eigenen
Branch abgearbeitet gehoeren.

Aufgenommen am 2026-08-25 aus dem [LED-Review](led/GoLive-Review.md).
Ergaenzung zu [ServiceReview.md](../ServiceReview.md), das die neun Dienste
insgesamt behandelt.

Legende: `[ ]` offen · `[x]` erledigt · **[H]** hoch · **[M]** mittel ·
**[N]** niedrig

---

## 1. Robustheit & Betrieb

### [ ] [M] 1.1 Vier Dienste veroeffentlichen ungeschuetzte Ports auf allen Interfaces

Stand `docker-compose.yml`:

| Dienst | Port | Was daran haengt |
|---|---|---|
| `rfid` | `8001:8000` | `/health` |
| `button` | `8005:8000` | `/health` |
| `display` | `8006:8000` | `/health` |
| `media-downloader` | `8007:8007` | `/health`, Download-API |

Alle vier binden auf `0.0.0.0` **und** auf IPv6 (`ss -tlnp` zeigt beides). Keiner
verlangt Authentifizierung. Das Backend spricht jeden dieser Dienste ueber das
Compose-Netz an (`http://rfid:8000` usw.), der Host-Port wird dafuer nicht
gebraucht.

Bei `media-downloader` ist es am unangenehmsten, weil dort nicht nur ein
`/health` haengt, sondern die Download-Schnittstelle.

**Fix:** wie bei `audio` und `led` bereits geschehen – `127.0.0.1:` davor. Der
Compose-Kommentar beim Audio-Service (`docker-compose.yml`, Abschnitt `audio`)
enthaelt die Begruendung im richtigen Wortlaut. Diagnose per `curl` auf der Box
bleibt moeglich.

**Risiko:** keins, solange wirklich nur das Backend zugreift. Vorher pruefen, ob
jemand die Ports von aussen fuer Debugging nutzt.

### [ ] [M] 1.2 `degraded` aus `/health` erreicht die WebUI nie

Fuenf Dienste melden in ihrem `/health` einen eigenen Status:

`audio`, `rfid`, `button`, `display`, `led` – alle mit `"status": "healthy"`
oder `"degraded"`.

Ausgewertet wird das nirgends. `backend_service/api/routes_system.py` hat zwei
Pfade, und **keiner** liest das Feld:

- **Normalfall** (`_status_from_docker`): baut die Liste aus der
  Container-Discovery und den Docker-Stats. Die `/health`-Endpunkte werden dabei
  ueberhaupt nicht aufgerufen – nur der Docker-Healthcheck zaehlt, und der prueft
  bloss, ob der Endpunkt mit 2xx antwortet.
- **Fallback ohne Docker-Socket** (`_status_from_probes`): ruft `/health` zwar
  auf, nimmt aus dem Body aber nur `version` und daraus, *ob* geantwortet wurde,
  ein `state: online | offline`.

Ein Dienst kann sich also selbst als `degraded` melden und wird in der WebUI
trotzdem gruen angezeigt. Konkret heisst das aktuell:

- LED: kein einziger GPIO-Pin belegbar (falsche `GPIO_GID` nach einem Update) –
  in der WebUI unsichtbar.
- Jeder Dienst: MQTT-Verbindung weg, waehrend der Container laeuft – ebenfalls
  unsichtbar.

**Fix:** im Fallback-Pfad `health.get("status")` mit uebernehmen, und im
Docker-Pfad zusaetzlich zu den Container-Daten einmal `/health` abfragen (oder
den gemeldeten Status per MQTT einsammeln). Dann in der WebUI als dritter
Zustand neben online/offline darstellen.

**Risiko:** mittel. Der Docker-Pfad ist der normale, und ihn um HTTP-Abfragen zu
erweitern macht `/api/system/status` langsamer. `HEALTH_TIMEOUT` steht auf 2 s
bei bis zu acht Diensten – das gehoert parallelisiert (ist es im Fallback
bereits, `asyncio.gather`).

### [ ] [N] 1.3 Log-Rotation wirkt erst beim Neuerzeugen der Container

Kein Fehler, sondern ein Hinweis zur Anwendung. Der `x-logging`-Anker in
`docker-compose.yml` (10 MB, drei Dateien, alle zehn Dienste) greift nicht durch
ein `docker compose restart`, sondern erst, wenn die Container neu **erzeugt**
werden – also beim naechsten reglaeren Update ueber die WebUI.

Bereits gewachsene Logdateien schrumpfen dadurch nicht von selbst.

**Zu pruefen nach dem naechsten Update:**

```bash
docker inspect minabox-led --format '{{json .HostConfig.LogConfig}}'
```

Erwartet: `{"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}`

---

## 2. Angrenzendes, das sonst verloren geht

Kein Robustheitsthema, aber beim selben Review aufgefallen.

### [ ] [H] 2.1 Die `lg`-Quelle wird unversioniert und ungeprueft gebaut

Betrifft **`led` und `button`** – beide bauen die C-Bibliothek `lgpio` beim
Image-Build aus dem Netz, ohne Tag und ohne Pruefsumme:

```dockerfile
# led-service/Dockerfile
RUN wget -q https://github.com/joan2937/lg/archive/refs/heads/master.tar.gz ...

# button-service/Dockerfile
RUN git clone --depth 1 https://github.com/joan2937/lg /tmp/lg ...
```

`master` ist ein bewegliches Ziel: kein CI-Build ist reproduzierbar, und ein
kompromittiertes Upstream-Repo landet ungeprueft in einem Image, das als root
baut und danach GPIO-Zugriff bekommt.

Der Bau aus Quellen selbst bleibt noetig: PyPI liefert `lgpio` 0.2.2.0 nur als
Wheel fuer cp39–cp312, **nicht fuer cp313**.

**Fix:** auf einen Tag oder Commit-SHA festnageln und die Pruefsumme mitgeben.
Fuer den LED-Teil steht das auch im
[LED-Review, Abschnitt 4.4](led/GoLive-Review.md).

### [ ] [M] 2.2 Deutsche Kommentare in fuenf Dockerfiles

Der Versions-Block am Dateiende ist noch deutsch in:

`button`, `audio`, `media-downloader`, `webui`, `display`

`host-helper` und `led` sind bereits uebersetzt – der Wortlaut kann von dort
uebernommen werden. Reine Textaenderung, kein Risiko, aber sie invalidiert die
letzten Metadaten-Layer und loest damit einen Rebuild aus.

### [ ] [N] 2.3 Die Version in `pyproject.toml` ist repo-weit veraltet

| Dienst | `pyproject.toml` | `VERSION` |
|---|---|---|
| audio | 0.1.0 | 0.2.0 |
| backend | 0.1.0 | 0.2.1 |
| button | 0.1.0 | 0.1.2 |
| display | 0.1.0 | 0.1.1 |
| led | 0.1.0 | 0.1.1 |
| media-downloader | 0.1.0 | 0.1.2 |
| rfid | 0.1.0 | 0.2.0 |

`host-helper` hat gar keine `pyproject.toml` – der Dienst kommt ohne aus.

Das Feld wird nirgends gelesen: die Dockerfiles installieren die Dienste nicht
als Paket, und `shared_lib.version.get_version()` liest die Build-Args. Es ist
also folgenlos – aber es steht in jeder Datei falsch da.

**Fix:** repo-weit auf einmal, entweder Feld pflegen oder

```toml
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {file = "VERSION"}
```

Einen einzelnen Dienst umzustellen waere schlechter als die einheitliche Luege.

### [ ] [N] 2.4 Die WebUI erklaert `repeat` nicht

Seit der Korrektur zaehlt `repeat` bei allen LED-Patterns **ganze Zyklen** – ein
Blinken ist an *und* wieder aus. Im Admin-Bereich
(`LEDConfigPanel.tsx`) steht dazu nichts; das Feld ist ein nacktes Zahlenfeld
mit `min: 0`.

Dasselbe gilt fuer `0` = unendlich, was man dem Feld ebenfalls nicht ansieht.

**Fix:** `helperText` an den drei Stellen, analog zu `leds.fields.gpio_hint`.

### [ ] [M] 2.5 Button-Service: 10 % CPU im Leerlauf

Gemessen im Vergleich (drei `docker stats`-Durchlaeufe): `button` 9,6–10,5 %,
`led` und `rfid` je rund 3 %. Steht bereits als offener Punkt in
[ServiceReview.md](../ServiceReview.md) und ist hier nur als Querverweis
aufgenommen, damit die Messung nicht verlorengeht.

---

## Nicht uebernommen

Zwei Verdachtsmomente aus dem LED-Review haben sich beim Nachsehen **nicht**
bestaetigt und stehen hier nur, damit sie niemand ein zweites Mal aufmacht:

- **`config/update` im Button-Service.** Sieht aus wie derselbe tote Pfad wie
  beim LED-Service, ist es aber nicht: `services/button-service/config` ist
  **schreibbar** gemountet (kein `:ro`), und die Callbacks in
  `button_service/main.py` sind synchron und werfen weiter, sodass
  `config/response` das echte Ergebnis meldet. Kein Fehler.
- **Test-Button bei deaktivierten LEDs.** Ist in der WebUI bereits ausgegraut
  (`LEDConfigPanel.tsx`, `disabled={... || !isEnabled}`).
