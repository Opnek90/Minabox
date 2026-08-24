# LED-Service – GoLive-Review

Zeilenweise Durchsicht des LED-Service, Stand 2026-08-24, Version 0.1.1.
Grundlage: `services/led-service/**`, die genutzten Teile von `shared-lib`,
der Compose-Block `led` und das veroeffentlichte Image `minabox-led:0.1.1`.

Der Dienst laeuft heute stabil (32 h Uptime, `healthy`, 10 MB RSS). Nichts in
dieser Liste ist ein Grund, den GoLive zu verschieben – aber die Punkte in
Abschnitt 1 treten im Alltag auf und sollten vorher weg.

Legende: **[H]** hoch · **[M]** mittel · **[N]** niedrig

---

## 1. Funktionale Fehler

### [H] 1.1 `rfid_tag_blocked` wird nie ausgeloest

`core/state_manager.py:35` hat eine Ableitungsregel fuer
`minabox/<id>/rfid/tag-blocked`, und die WebUI bietet den Zustand zur Bindung an
(`routes_config.py:_LED_BINDING_STATES`). Das Topic fehlt aber in
`infrastructure/mqtt_client.py:_build_subscription_topics()`.

Der Backend-RFID-Handler publiziert es tatsaechlich
(`core/handlers/rfid_handler.py:145`). Wer im Admin-Bereich eine LED auf
"gesperrte Karte" bindet, bekommt also stillschweigend nichts. Ein gesperrter
Tag sieht fuer das Kind aus wie ein defekter Tag.

**Fix:** eine Zeile in der Subscription-Liste. Risiko: keins.

### [H] 1.2 Die Idempotenz-Pruefung greift bei `solid`, `off` und `glow` nie

`core/led_controller.py:158`:

```python
if (
    self._current_logical_state == logical_state
    and self._current_task is not None
    and not self._current_task.done()
):
    return
```

`run_solid_pattern()` und `run_off_pattern()` sind nach einem `led.on()` bzw.
`led.off()` sofort fertig. Ihr Task ist also schon `done()`, wenn die naechste
Nachricht eintrifft – die Bedingung ist nie wahr, und das Pattern wird jedes Mal
neu gestartet. Genau die drei Pattern-Typen, fuer die `_PERSISTENT_PATTERN_TYPES`
eingefuehrt wurde, sind ungeschuetzt.

Im Log der laufenden Box sichtbar:

```
21:37:16.880  led_4 Gruen audio_playing solid
21:37:18.408  led_4 Gruen audio_playing solid
21:37:19.407  led_4 Gruen audio_playing solid
21:37:21.044  led_4 Gruen audio_playing solid
21:37:23.260  led_4 Gruen audio_playing solid
```

Der Audio-Service publiziert `audio/status` bei jeder Aenderung, also waehrend
der Wiedergabe im Sekundentakt. Jede Nachricht erzeugt: einen abgebrochenen
Task, einen neuen Task, einen GPIO-Schreibvorgang und **eine INFO-Logzeile**.
Bei einer Stunde Hoerbuch sind das rund 2.500 Zeilen fuer nichts – auf einem
Geraet, dessen Docker-Logs unrotiert auf einer SD-Karte liegen (siehe 2.2).

Ebenfalls sichtbar: `led_5 rfid_scanned solid` zweimal im Abstand von 3 ms,
weil `rfid/presence` (retained) und `rfid/tag-scanned` beide denselben Zustand
liefern.

**Fix:** die Pruefung fuer persistente Pattern von der Task-Lebensdauer
entkoppeln – `_current_logical_state == logical_state` genuegt dort. Risiko:
gering, betrifft nur den Fall "gleicher Zustand nochmal".

### [H] 1.3 Fehler in Pattern-Tasks werden vollstaendig verschluckt

`core/led_controller.py:291`:

```python
def _on_task_done(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is None:
        ...
```

Der `else`-Fall fehlt. Schlimmer noch: der Aufruf von `task.exception()` gilt
fuer asyncio als "Exception abgeholt", also unterbleibt auch die uebliche
Warnung *Task exception was never retrieved*. Ein gescheitertes Pattern
hinterlaesst **keine einzige Logzeile** – die LED bleibt einfach dunkel.

`apply_pattern()` hat zwar einen `try/except` um `_start_pattern()`, aber der
sieht nur Fehler *beim Starten*, nicht im Task selbst.

**Fix:** im `else`-Zweig `logger.error(...)`. Risiko: keins.

### [H] 1.4 Zwei Konfigurationen, die die LED still totlegen

Beide sind ueber die WebUI erreichbar und werden nirgends abgefangen:

| Eingabe | Was passiert |
|---|---|
| `pulse` mit `duration_ms: 0` | `_start_pattern` prueft nur `is None`, `0` geht durch. `run_pulse_pattern()` wirft `InvalidPatternError` – im Task, also unsichtbar (1.3). |
| `glow` mit `min_brightness >= max_brightness` | dito in `run_glow_pattern()`. |

Das Schema laesst beides zu (`duration_ms: NonNegativeInt`, und die beiden
Helligkeiten werden nur einzeln gegen 0.0–1.0 geprueft, nie gegeneinander). Die
WebUI setzt `inputProps={{ min: 0 }}` bzw. erlaubt `min = max = 1.0`.

**Fix:** ein `model_validator` in `LEDPattern`, der die Kombination prueft, plus
1.3 als Sicherheitsnetz. Risiko: gering – aber bestehende `leds.json` muessen
die Validierung ueberleben, sonst startet der Dienst nicht mehr. Deshalb: nur
die tatsaechlich kaputten Kombinationen ablehnen, alles andere durchlassen.

### [M] 1.5 `config/update` schreibt auf ein Read-only-Mount und meldet trotzdem Erfolg

`docker-compose.yml:330` mountet `config` als `:ro` (im laufenden Container
verifiziert: `"RW": false`). `ConfigManager.update_config()` ruft
`Path.write_text()` – das schlaegt mit `OSError` fehl.

Dazu kommt die Reihenfolge in `infrastructure/mqtt_client.py:145`:

```python
self._on_config_update(new_config)      # legt nur einen Task an
await self.resubscribe_retained_topics()
await self._send_config_response(success=True, error=None)
```

Der Callback ist synchron und startet intern `asyncio.create_task(_do_update())`.
Die Erfolgsmeldung geht also **immer** raus, egal was der Task spaeter macht.

Heute faellt das nicht auf, weil das Backend diesen Pfad nicht benutzt: es
schreibt die Datei selbst und schickt nur `config/reload`. Der Weg ist damit
toter Code mit einer Falltuer – wer ihn spaeter benutzt, bekommt "gespeichert"
gemeldet und einen Fehler im Log.

**Fix:** entweder `config/update` ersatzlos entfernen (Subscription, Handler,
Doku) oder den Callback `async` machen und das Ergebnis abwarten. Ich empfehle
Entfernen: das Besitzverhaeltnis "Backend schreibt, Service liest" ist sauber
und wird durch das `:ro`-Mount bereits erzwungen.

### [M] 1.6 Kein Schutz gegen gleichzeitige Zustandswechsel

`main.py:154` startet fuer jede MQTT-Nachricht ein `asyncio.create_task(
led_manager.apply_state(...))`. Zwei kurz aufeinanderfolgende Nachrichten
ergeben zwei Tasks, die in `LEDController.apply_pattern()` an jedem `await`
ineinander laufen koennen: beide brechen ab, beide starten, `_current_task`
zeigt nur auf den letzten. Der erste Task blinkt verwaist weiter, und das
gemeinsame `_cancel_event` wird von `_start_pattern()` wieder `clear()`-t – der
verwaiste Task sieht sein Abbruchsignal also nie.

Dass die Konstellation vorkommt, zeigt der Doppel-Log aus 1.2 (3 ms Abstand).
Bei `solid` ist es harmlos, bei `blink`/`pulse` bliebe eine LED sichtbar
falsch stehen.

Die alte Doku behauptete eine FIFO-Queue – die gibt es nicht. Im neuen
Architecture-Dokument steht das jetzt korrekt.

**Fix:** ein `asyncio.Lock` pro Controller um `apply_pattern()`, oder – die
kleinere Aenderung – `on_message` den Handler awaiten lassen, statt Tasks zu
streuen. Das serialisiert die Verarbeitung und macht die FIFO-Zusage nachtraeglich
wahr. Risiko: mittel, weil die Reihenfolge sich messbar aendert. Vorher lokal
mit `MINABOX_LED_TAG=local` gegen echte Hardware testen.

### [M] 1.7 `LGPIOFactory` wird bei jedem Reload neu erzeugt, die alte nie geschlossen

`core/led_controller.py:420`:

```python
Device.pin_factory = LGPIOFactory()
```

`initialize_leds()` laeuft bei jedem `config/reload`, also bei jedem Speichern
in der WebUI. Die vorherige Factory verliert nur ihre Referenz; ihr
`gpiochip_open`-Handle bleibt in der lgpio-C-Bibliothek offen, weil `close()`
nie gerufen wird. lgpio hat eine feste Handle-Tabelle.

*Nicht verifiziert* – dazu muesste man auf der Box wiederholt speichern, und
das wollte ich am laufenden System nicht tun. Der Fix ist aber unabhaengig davon
richtig: die Factory einmal beim Start setzen, nicht bei jedem Reload, oder die
alte vorher schliessen.

### [N] 1.8 Der "5-Sekunden-Testblink" dauert 2,5 Sekunden

`run_test_blink(duration_sec=5.0)` rechnet `repeat = max(1, int(5.0)) = 5` bei
`interval_ms = 500`. `run_blink_pattern` zaehlt aber **Flanken**, nicht Zyklen –
5 × 500 ms = 2,5 s. Docstring, API-Docstring und die alte Doku sagten 5 s.

Nebenbei: dieselbe Flanken-Semantik gilt fuer jedes `blink`-Binding. In der
ausgelieferten `leds.json` steht `button_pressed` mit `repeat: 2`, was genau ein
vollstaendiges Blinken ergibt. Im neuen Architecture-Dokument ist das jetzt
beschrieben; in der WebUI-Hilfe steht es noch nicht.

---

## 2. Robustheit und Betrieb

### [H] 2.1 `/health` meldet `healthy`, obwohl keine einzige LED funktioniert

`api/routes.py:69` zaehlt `len(led_manager._controllers)` – das sind die
*konfigurierten*, nicht die *initialisierten* LEDs. Ein Controller, dessen Pin
nicht geclaimt werden konnte (falsche `GPIO_GID`, Pin belegt), zaehlt mit. Der
Status haengt allein an `mqtt_connected`.

Praktische Folge: wenn nach einem Update die Gruppen-ID nicht mehr passt, sind
alle LEDs tot, der Container ist `healthy`, die WebUI zeigt gruen, und im Log
steht nur eine `warning`.

**Fix:** `leds_available` (Controller mit `_gpio_available`) zusaetzlich
ausgeben und `degraded` melden, wenn LEDs konfiguriert, aber keine verfuegbar
ist. Der Docker-Healthcheck prueft nur, dass der Endpunkt antwortet – der
Container wuerde also *nicht* neu starten, die WebUI koennte es aber anzeigen.
Risiko: gering.

### [H] 2.2 Keine Log-Rotation

`docker inspect` zeigt `{"Type":"json-file","Config":{}}` – Docker-Default,
also unbegrenzt. In `docker-compose.yml` gibt es keinen einzigen
`logging:`-Block. Auf einer SD-Karte ist das die Sorte Problem, die nach
Monaten auf einmal die Box lahmlegt.

Betrifft alle neun Dienste, nicht nur LED, wird aber durch 1.2 hier besonders
gefuettert.

**Fix:** in `docker-compose.yml` pro Dienst (oder ueber einen YAML-Anker)

```yaml
logging:
  driver: json-file
  options: { max-size: "10m", max-file: "3" }
```

Risiko: keins, wirkt beim naechsten Container-Neustart.

### [M] 2.3 Port 8004 haengt ohne Authentifizierung auf allen Interfaces

`ss -tlnp` zeigt `0.0.0.0:8004` und `[::]:8004`. `POST /test` ist ungeschuetzt –
jeder im WLAN kann die LEDs der Box blinken lassen. Das Backend braucht den
Host-Port nicht, es spricht `http://led:8000` ueber das Compose-Netz an.

Fuer den Audio-Service ist genau das schon geloest, samt Begruendung im
Compose-Kommentar (`docker-compose.yml:200`): `127.0.0.1:8003:8003`.

**Fix:** `- "127.0.0.1:8004:8000"`. Diagnose per `curl` auf der Box bleibt
moeglich. Risiko: keins fuer LED. (Gleiches gilt fuer button/display/rfid auf
8005–8007.)

### [M] 2.4 Eine deaktivierte LED belegt ihren Pin weiterhin

`enabled` wird nur in `apply_pattern()` geprueft (`led_controller.py:133`).
`LEDController.__init__` legt das `LED`/`PWMLED`-Objekt trotzdem an. Wer eine
LED in der WebUI abschaltet, um den Pin anderweitig zu nutzen, bekommt ihn
nicht frei.

**Fix:** die `enabled`-Pruefung nach vorn in `__init__` ziehen. Risiko: gering.

### [M] 2.5 Keine Validierung von GPIO-Nummer, Doppelbelegung und doppelter ID

`gpio: PositiveInt` akzeptiert `999`. Zwei LEDs auf demselben Pin sind erlaubt –
die zweite scheitert dann mit `GPIOPinInUse`, was als `warning` untergeht (1.3
in Gruen: hier wird wenigstens geloggt). Zwei LEDs mit derselben `id`
ueberschreiben sich in `self._controllers[config.id]`, der erste Controller
wird nie geschlossen.

Die WebUI prueft nichts (`inputProps={{ min: 0 }}`), das Backend nur die
Grobstruktur (`_validate_config_shape`: "`leds` ist eine Liste").

**Fix:** im Pydantic-Schema – GPIO auf 2–27 begrenzen, `id` und `gpio` ueber
alle Eintraege auf Eindeutigkeit pruefen. **Achtung:** eine strengere
Validierung kann eine bestehende `leds.json` unbrauchbar machen, und
`load_app_config()` laesst den Dienst dann nicht starten. Vorher gegen die
echte Datei der Box testen.

### [N] 2.6 Tasks ohne Referenz

`main.py:154`, `:175`, `:192` starten Tasks mit `asyncio.create_task(...)`, ohne
das Ergebnis irgendwo zu halten. Der Garbage Collector darf einen solchen Task
mitten im Lauf einsammeln. In der Praxis selten, aber es ist ein dokumentierter
Fallstrick.

---

## 3. Code-Qualitaet

### [M] 3.1 Deutsche Kommentare im Dockerfile

`services/led-service/Dockerfile:64-67` – der Versions-Block ist noch deutsch,
inklusive "ungueltig". Der Rest der Datei ist englisch. Der Host-Helper hat den
Block bereits uebersetzt; der Text kann von dort uebernommen werden.

Der Python-Quellcode ist ansonsten durchgaengig englisch – Bezeichner,
Docstrings und Kommentare. Ausnahme sind Werte, keine Sprache: die LED-Namen
in `config/leds.json` ("Blau", "Gelb", "Gruen") sind Nutzerdaten und bleiben.
Auffaellig nur, dass die getrackte `leds.json.example` "Gruen" schreibt, die
lokale `leds.json` aber "Grün" – die Umlaut-Regel des Projekts gilt fuer
`.py`/`.sh`, insofern in Ordnung.

### [M] 3.2 66 ruff-Befunde, 8 von 16 Dateien nicht formatiert

```
26 W293  Leerzeichen in Leerzeilen
 7 E501  Zeile laenger als 88
 7 UP041 asyncio.TimeoutError -> TimeoutError
 6 UP006  Dict/List -> dict/list
 6 UP035  veraltete typing-Importe
 5 I001   Importreihenfolge
 3 E402   Import nicht am Dateianfang (api/routes.py)
 2 F401   ungenutzt: logging, GPIOInitError
 2 UP037  ueberfluessige Quotes in Annotationen
 1 F821   undefinierter Name PWMLED
 1 UP017  datetime.timezone.utc -> datetime.UTC
```

`F821` ist der einzige mit Substanz: `led_patterns.py:206` annotiert
`led: "PWMLED"`, aber `PWMLED` ist nirgends importiert – auch nicht im
`TYPE_CHECKING`-Block, der nur `LED` holt. Zur Laufzeit harmlos (`from __future__
import annotations`), fuer mypy und jeden Leser aber falsch.

44 der 66 sind mit `ruff check --fix` erledigt, der Rest ist Handarbeit.
`ruff format` wuerde 8 Dateien anfassen – ein grosser, aber rein mechanischer
Diff. Ich wuerde das in einen eigenen Commit legen, damit die inhaltlichen
Fixes lesbar bleiben.

### [N] 3.3 Toter Code

| Stelle | Befund |
|---|---|
| `src/led_service/models/` | `__init__.py` und `schemas.py` sind beide 0 Byte |
| `requirements.txt:13`, `pyproject.toml:16` | `tenacity` wird nirgends importiert |
| `exceptions.py` | `HardwareError`, `GPIOInitError`, `UnknownStateError` werden nie geworfen; `GPIOInitError` wird importiert und nicht benutzt |
| `mqtt_client.py:171` | `_handle_config_get()` bestaetigt nur, liefert die Config nie |
| `core/__init__.py` | exportiert `run_*_pattern`, aber nicht `run_glow_pattern` – inkonsistent |

### [N] 3.4 Drei verschiedene Versionsnummern

`VERSION` sagt `0.1.1`, `pyproject.toml:7` sagt `0.1.0`, und
`api/routes.py:45` traegt `version="0.1.0"` fest in die FastAPI-App ein –
waehrend `/health` daneben korrekt `get_version()` aus den Build-Args liest.
Die OpenAPI-Seite unter `/docs` zeigt damit dauerhaft eine falsche Version.

**Fix:** `version=get_version()` in `create_app()`, und `pyproject.toml`
entweder pflegen oder das Feld auf die VERSION-Datei zeigen lassen.

### [N] 3.5 Kleinigkeiten mit Typ-Bezug

- `state_manager.py:25`: `Dict[str, callable]` – `callable` ist die eingebaute
  Funktion, kein Typ. Gemeint ist `Callable[[bytes], str]`.
- `api/routes.py:69`: `led_manager._controllers` greift von aussen auf ein
  privates Attribut zu. Eine `led_count`-Property waere sauberer.
- `led_controller.py:65` und `:415` lesen `DISABLE_GPIO` zweimal direkt per
  `os.getenv`, statt es einmal ueber `EnvConfig` zu fuehren wie alle anderen
  Einstellungen.

### [H] 3.6 Null Tests

`services/led-service/` hat kein `tests/`-Verzeichnis. Zum Vergleich: backend 15
Dateien, rfid 4, audio 3, display 1, host-helper 1.

Das ist fuer den GoLive der wichtigste Punkt in diesem Abschnitt, weil jeder
Fix aus Abschnitt 1 sonst ungeprueft auf die Box geht. Testbar ohne Hardware
sind die Teile, in denen die Fehler stecken:

- `StateManager.derive_state()` – reine Funktion ueber Topic + Payload
- `LEDPattern`-Validierung – die Faelle aus 1.4
- die Pattern-Coroutinen gegen ein Fake-LED-Objekt (`led.on/off/value`)
- `LEDController.apply_pattern()` mit `DISABLE_GPIO=true`

---

## 4. Docker-Image

Ist-Zustand `minabox-led:0.1.1` (arm64): **297 MB** auf der Platte, 64,7 MB
komprimiert. Aufteilung laut `docker history` und Messung im Container:

| Schicht | Groesse |
|---|---|
| Debian trixie Basis | 109 MB |
| CPython 3.13 Build | 48,7 MB |
| `site-packages` | 58,8 MB |
| `curl` + Abhaengigkeiten | 14,5 MB |
| `liblgpio.so` | 0,3 MB |
| Anwendungscode + Config | 0,15 MB |

`site-packages` im Detail (63 MB gemessen):

| Paket | MB | gebraucht? |
|---|---|---|
| `uvloop` | 17 | **nein** |
| `pip` | 12 | **nein** |
| `setuptools` | 7 | **nein** |
| `pydantic_core` | 5 | ja |
| `yaml` | 4 | **nein** |
| `pydantic` | 4 | ja |
| `websockets` | 2 | **nein** |
| `watchfiles` | 2 | **nein** |
| `httptools` | 2 | **nein** |
| `gpiozero`, `fastapi`, `anyio`, Rest | ~8 | ja |

### [M] 4.1 `uvicorn[standard]` → `uvicorn` (≈ 27 MB)

Das `[standard]`-Extra zieht `uvloop`, `httptools`, `websockets`, `watchfiles`,
`PyYAML` und `python-dotenv`. Keins davon wird benutzt:

- `uvloop` wird gar nicht aktiv – `main.py` startet die Schleife selbst mit
  `asyncio.run()` und uebergibt die App an `Server.serve()` *innerhalb* dieser
  Schleife. `Config.setup_event_loop()` laeuft dabei nie.
- `PyYAML` braeuchte nur `log_config` – das steht auf `None`.
- `httptools` und `websockets` sind `auto`-Optionen mit Fallback (`h11` bzw.
  gar kein WS-Protokoll); der Dienst hat keine WebSockets.
- `watchfiles` und `python-dotenv` sind `--reload` und `--env-file`.

**Risiko:** gering, aber es ist die Aenderung, bei der ein Irrtum am teuersten
waere – wenn `/health` nicht mehr antwortet, meldet der Healthcheck `unhealthy`.
Vor dem Release lokal bauen und starten:
`./scripts/build-local.sh led && MINABOX_LED_TAG=local docker compose up -d led`,
dann `curl` gegen `/health` und `/test`.

### [M] 4.2 `pip` und `setuptools` nicht ins Runtime-Image kopieren (≈ 19 MB)

`COPY --from=builder /usr/local/lib/python3.13/site-packages ...` nimmt die
Build-Werkzeuge mit. Zur Laufzeit installiert niemand etwas nach.

`gpiozero` 2.x sucht seine Pin-Factories ueber `importlib.metadata` (stdlib),
nicht ueber `pkg_resources` – und der Code importiert `LGPIOFactory` ohnehin
direkt. **Trotzdem der Punkt mit dem hoechsten Restrisiko in diesem Abschnitt**,
weil ein fehlendes `pkg_resources` sich erst zur Laufzeit zeigt. Gleicher
Testlauf wie bei 4.1.

Nebenbei landen ueber `COPY --from=builder /usr/local/bin` auch `rgpiod`, `rgs`,
`idle`, `pydoc` und `pinout` im Image – zusammen nur ~200 kB, aber sie gehoeren
da nicht hin.

### [M] 4.3 `curl` durch einen Python-Healthcheck ersetzen (≈ 14,5 MB)

`curl` ist die einzige apt-Installation im Runtime-Stage und existiert nur fuer
den Healthcheck. Python ist ohnehin da:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"
```

**Wichtig:** `docker-compose.yml:342` ueberschreibt den Healthcheck mit
`["CMD","curl",...]`. Beide Stellen muessen zusammen geaendert werden, sonst ist
der Container dauerhaft `unhealthy`.

### [H] 4.4 Die `lg`-Quelle ist unversioniert und ungeprueft

```dockerfile
RUN wget -q https://github.com/joan2937/lg/archive/refs/heads/master.tar.gz ...
```

`master` ist ein bewegliches Ziel, und es gibt keine Pruefsumme. Jeder CI-Build
kann eine andere C-Bibliothek einbacken als der vorige, ohne dass sich im Repo
etwas aendert – und ein kompromittiertes Upstream-Repo landet ungeprueft im
Image, das als root baut und danach GPIO-Zugriff hat.

Fuer einen GoLive ist das der wichtigste Dockerfile-Punkt. Auf einen Tag oder
Commit-SHA festnageln und die Pruefsumme mitgeben.

Der Build aus Quellen selbst bleibt noetig: PyPI liefert `lgpio` 0.2.2.0 nur als
Wheel fuer cp39–cp312, **nicht fuer cp313**. Der Builder-Stage kann also nicht
entfallen. (Der Button-Service macht dasselbe mit `git clone --depth 1` – dort
gilt derselbe Befund.)

### [N] 4.5 Kleinigkeiten im Dockerfile

- `PYTHONDONTWRITEBYTECODE=1` und `PYTHONUNBUFFERED=1` fehlen; der Host-Helper
  hat beide.
- `RUN useradd` und `RUN chown -R` sind zwei Schichten; `COPY --chown=` spart
  die 139 kB Duplikat.
- Der Builder nutzt `build-essential`, wo `gcc libc6-dev make` genuegt (so macht
  es der Button-Service). Betrifft nur Buildzeit und CI-Cache, nicht das Image.
- `python:3.13-slim` ist ein beweglicher Tag. Ein Digest-Pin waere fuer
  reproduzierbare Releases konsequent – aber er will gepflegt werden, sonst
  bleiben Sicherheitsupdates der Basis aus. Bewusste Entscheidung, kein Fehler.

### Summe

4.1 + 4.2 + 4.3 sparen zusammen rund **60 MB von 297 MB (−20 %)**, ohne eine
Zeile Anwendungscode anzufassen. Die gleichen Aenderungen greifen bei
button/display/rfid, die aus demselben Muster gebaut sind.

---

## 5. Laufzeitverbrauch

Gemessen ueber drei `docker stats`-Durchlaeufe am laufenden System:

| Container | CPU | RSS |
|---|---|---|
| minabox-led | 2,9 – 3,4 % | 10,1 MB |
| minabox-rfid | 3,3 – 4,3 % | 11,3 MB |
| minabox-button | 9,6 – 10,5 % | 10,7 MB |

Der Speicherverbrauch ist unauffaellig. Die 3 % CPU im Leerlauf stammen sehr
wahrscheinlich aus dem `glow`-Pattern der Ring-LED: `rfid_removed` ist mit
`repeat: 0` gebunden, laeuft also dauerhaft, solange keine Karte aufliegt – und
das ist der Normalzustand. Bei `cycle_ms: 2000` und `_GLOW_STEPS = 50` sind das
25 Schleifendurchlaeufe pro Sekunde, jeder mit einem `asyncio.wait_for()`, das
intern einen Task anlegt.

*Nicht verifiziert* – dazu muesste man die Bindung auf der Box umkonfigurieren.
Falls es stoert, waeren die Ansaetze: `_GLOW_STEPS` bei langen Zyklen
reduzieren, die Helligkeitswerte einmal vorberechnen statt `math.cos()` pro
Schritt, oder `asyncio.timeout()` statt `wait_for()`. Das sind Mikro-
Optimierungen – 3 % auf einem Pi rechtfertigen keine riskante Aenderung an
einem Pattern, das sichtbar korrekt laeuft.

`minabox-button` mit 10 % ist der auffaelligere Wert und steht bereits als
offener Punkt in [ServiceReview.md](../../ServiceReview.md).

---

## 6. Was ich nicht anfassen wuerde

- **Die Pattern-Coroutinen selbst.** `run_blink/pulse/glow` sind korrekt, haben
  ihr `led.off()` im `finally` und reagieren sauber auf das Abbruch-Event. Die
  Flanken-Semantik aus 1.8 ist ungluecklich benannt, aber jede bestehende
  `leds.json` ist darauf eingestellt. Wer `repeat` "repariert", aendert das
  Blinkverhalten jeder ausgelieferten Box.
- **Den `lg`-Build durch ein PyPI-Wheel ersetzen.** Geht nicht, siehe 4.4.
- **`python:3.13-slim` gegen Alpine.** `lgpio` und `gpiozero` gegen musl zu
  bauen ist eine eigene Baustelle, und der Gewinn ist nach 4.1–4.3 klein.
- **Den Pin-Cleanup beim Shutdown** (`led_controller.py:336`). Sieht auf den
  ersten Blick nach einem Fremdgriff in `Device.pin_factory` aus, verhindert
  aber, dass eine LED nach `docker compose down` glimmt. Laeuft, bleibt.
