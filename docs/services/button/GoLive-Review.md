# Button-Service – GoLive-Review

Zeilenweise Durchsicht des Button-Service, Stand 2026-08-25, Version 0.1.2.
Grundlage: `services/button-service/**` (alle 17 Quelldateien, 1698 Zeilen), die
genutzten Teile von `shared-lib`, der Compose-Block `button`, das
veroeffentlichte Image `minabox-button:0.1.2` und Messungen am laufenden System
(Raspberry Pi 4 Model B, 4 Kerne, 2 d 11 h Uptime).

Der Dienst laeuft heute stabil und tut, was er soll: Tastendruecke und
Encoder-Drehungen kommen als Aktionen am Backend an. **Nichts in dieser Liste
ist ein Grund, den GoLive zu verschieben.** Die Punkte in Abschnitt 1 sind
allerdings Zustaende, in die die Box im Alltag geraten kann – und aus denen sie
ohne Container-Neustart nicht mehr herausfindet.

**Umgesetzt auf dem Branch `fix/button-go-live`:** Abschnitt 1.1-1.4,
Abschnitt 4 vollstaendig und Abschnitt 5 (CPU). Das Image ist von 297 auf
229 MB geschrumpft (-23 %), der Leerlaufverbrauch von 8,2 % auf 3,1 %, und der
Dienst hat jetzt 22 eigene Tests plus 37 im Backend fuer die Config-Pruefung
(Gesamtsuite 500 -> 559, alle gruen).

**Offen geblieben** und bewusst nicht angefasst: 1.5, 1.6, 1.7, 2.1, 2.2 und
der Rest von Abschnitt 3. 1.5 und 1.6 aendern das Bedienverhalten und gehoeren
mit echten Tasten ausprobiert, nicht nebenbei erledigt.

[Architecture.md](Architecture.md) ist neu geschrieben, vollstaendig englisch
und auf den tatsaechlichen Stand gebracht; die README des Dienstes ebenso.

Legende: **[H]** hoch · **[M]** mittel · **[N]** niedrig ·
`[x]` umgesetzt · `[~]` teilweise · `[ ]` offen

Was hier auffiel, aber **andere Dienste** betrifft – offene Ports, der nie
ausgewertete `degraded`-Status, deutsche Dockerfile-Kommentare, die ungepinnte
`lg`-Quelle, `.dockerignore` – steht bereits in
[../Offene-Punkte.md](../Offene-Punkte.md) und wird hier nur referenziert.

---

## Kurzfassung

| # | Befund | Stufe | Stand |
|---|---|---|---|
| 1.1 | Ein einziger belegter Pin legt **alle** Buttons still – und die Pins bleiben belegt | **H** | `[x]` |
| 1.2 | `/health` meldet `healthy`, obwohl kein einziger Button funktioniert | **H** | `[x]` |
| 1.3 | Eine ungueltige `buttons.json` schickt den Container in die Neustart-Schleife | **H** | `[x]` |
| 1.4 | Eine fehlerhafte Config wird in der WebUI als "gespeichert" quittiert | **H** | `[x]` |
| 1.5 | Jeder kurze Tastendruck ist grundsaetzlich 400 ms verzoegert | **M** | `[ ]` |
| 1.6 | Der Encoder-Taster hat keinerlei Entprellung | **M** | `[ ]` |
| 1.7 | Pending-Timer werden beim Herunterfahren nicht abgebrochen | **N** | `[x]` |
| 2.1 | Kein Last Will – eine tote Box bleibt am Broker "da" | **N** | `[ ]` |
| 2.2 | `config/update` und `config/get` sind toter Code | **N** | `[ ]` |
| 3.x | 54 ruff-Befunde, leere Dateien, ungenutzte Exceptions, Versionsnummern, null Tests | **M** | teilweise |
| 4.x | Image 297 MB → **229 MB** | **M** | `[x]` |
| 5.x | 8,2 % CPU im Leerlauf → **3,1 %** | **M** | `[x]` |

---

## 1. Funktionale Fehler

### [x] [H] 1.1 Ein einziger belegter Pin legt alle Buttons still – und die Pins bleiben belegt

Das ist der schwerwiegendste Befund, und er ist reproduziert.

`core/gpio_input_manager.py:61-72` legt die Geraete nacheinander an und haengt
jedes sofort an `self._devices`. Schlaegt das *n*-te fehl, fliegt ein
`GPIOInitError` – die *n-1* bereits erzeugten `gpiozero`-Geraete bleiben
erzeugt. In `main.py:83-89` wird der Fehler gefangen:

```python
except Exception as exc:
    logger.warning("gpio_init_skipped", ...)
    self._gpio_manager = None      # <- ohne close()
```

Der Manager wird weggeworfen, aber `close()` wird nie gerufen. Die Folgen sind
alle drei unangenehm:

1. **Alle** Buttons sind tot, nicht nur der fehlerhafte.
2. Die bereits erzeugten Pins bleiben belegt – ein spaeterer `config/reload` mit
   korrigierter Config kann sie nie wieder beanspruchen (`GPIO busy`).
3. Der Alert-Thread von `lgpio` laeuft fuer die verwaisten Pins weiter und
   verbraucht weiter CPU (siehe Abschnitt 5).

Nachgestellt auf der Box, mit einer Config aus GPIO 6 (frei) und GPIO 5
(absichtlich belegt):

```text
gpio_input_init_failed   button_id=b  error='GPIO busy'
gpio_init_skipped        message="Running without button hardware; ..."
```

Danach ein zweiter Container, der **nur** GPIO 6 anfordert:

```text
gpio_input_init_failed   button_id=c  error='GPIO busy'
```

GPIO 6 gehoert also weiterhin dem Container, der sich fuer "ohne
Button-Hardware" haelt. Gemessener CPU-Verbrauch dieses Containers: **8,03 %** –
fuer null funktionierende Buttons.

Der praktische Ausloeser dafuer steht in der README des Dienstes: ein Pin, der
sowohl in `leds.json` als auch in `buttons.json` steht. Wer im Admin-Bereich
einen Button auf GPIO 17 legt, hat genau diesen Fall.

**Erledigt:**

- `_init_device()` sammelt die Geraete eines Buttons erst lokal und uebergibt
  sie nur, wenn der ganze Button steht. Ein Encoder, dessen `sw`-Pin belegt
  ist, gibt CLK und DT wieder her.
- `start()` ueberspringt einen fehlgeschlagenen Button und macht weiter, statt
  abzubrechen. Fatal ist nur noch eine unbrauchbare Pin-Factory (Image ohne
  lgpio) – die kann ohnehin nichts ansteuern.
- Neu: `available_count` und `configured_count`, plus eine `no_buttons_available`-
  Warnung im Wortlaut des LED-Service, wenn kein einziger Pin kam.
- `main.py` ruft im Fehlerfall `manager.close()`, bevor es den Manager
  wegwirft – an beiden Stellen (`_start_gpio()`, aus `start()` und
  `_reinit_gpio()` heraus).

**Nachgewiesen auf der Box** mit dem lokal gebauten Image und einer Config aus
GPIO 5 (frei), GPIO 17 (gehoert dem LED-Dienst) und GPIO 6 (frei):

```text
gpio_input_init_failed  button_id=busy  error="'GPIO busy'"
                        hint='Pin is unavailable; check for an overlap with config/leds.json.'
gpio_inputs_started     available=2  configured=3  devices=2
button_service_started
```

Vorher waren in genau diesem Fall alle drei Buttons tot. Der LED-Dienst blieb
unbeeintraechtigt (`leds_available: 5`).

Sieben Tests in `tests/test_gpio_input_manager.py` halten das fest, darunter
der Encoder-Fall und "nach `close()` lassen sich dieselben Pins wieder
beanspruchen" – das ist der Weg, den ein `config/reload` geht.

### [x] [H] 1.2 `/health` meldet `healthy`, obwohl kein einziger Button funktioniert

`api/routes.py:49-57` kennt genau eine Fehlerquelle:

```python
"status": "healthy" if mqtt_client.is_connected else "degraded",
...
"buttons_configured": get_buttons_count(),
```

`buttons_configured` zaehlt die Eintraege in der JSON-Datei – nicht die
Geraete, die wirklich einen Pin halten. Der Zustand aus 1.1 (GPIO komplett tot,
MQTT in Ordnung) meldet damit sauber `healthy`. Der Docker-Healthcheck fragt
ohnehin nur, ob der Endpunkt antwortet.

Gemessen am nachgestellten Container:

```json
{"status":"degraded","service":"button","buttons_configured":3,"mqtt_connected":false, ...}
```

`degraded` steht dort nur wegen des fehlenden Brokers. Mit erreichbarem Broker
waere die Antwort `healthy` gewesen – bei drei konfigurierten und null
funktionierenden Buttons.

Der LED-Service hatte denselben Fehler und hat ihn bereits behoben
([LED-Review 2.1](../led/GoLive-Review.md)). Der Wortlaut dort passt eins zu
eins:

```python
buttons_usable = buttons_available > 0 or buttons_configured == 0
"status": "healthy" if mqtt_connected and buttons_usable else "degraded",
```

**Erledigt:** `/health` meldet jetzt `buttons_available`, `gpio_enabled` und
`config_error` mit. Die Regel steckt in `models/schemas.py:HealthState` und ist
eine Spur strenger als beim LED-Service: `degraded`, sobald **ein** Button
seinen Pin nicht bekommt, nicht erst wenn alle ausfallen. Fuer Buttons gibt es
keinen legitimen Grund, unter der konfigurierten Zahl zu bleiben.

`DISABLE_GPIO=true` bleibt `healthy` – das ist eine Einstellung, kein Defekt.

Am lokal gebauten Image gemessen, Config wie in 1.1:

```json
{"status": "degraded", "buttons_configured": 3, "buttons_available": 2,
 "gpio_enabled": true, "config_error": null, ...}
```

Sechs Tests in `tests/test_health_and_startup.py` decken die Faelle ab.

**Weiterhin zu beachten:** solange der `degraded`-Status nirgends ausgewertet
wird ([Offene-Punkte 1.2](../Offene-Punkte.md)), bleibt der Befund in der WebUI
unsichtbar – er steht jetzt aber im Diagnose-Paket und in `curl`-Reichweite.

### [x] [H] 1.3 Eine ungueltige `buttons.json` schickt den Container in die Neustart-Schleife

`main.py:204` ruft `load_app_config()` **vor** dem `try`. Ist die Datei
syntaktisch kaputt oder verletzt sie das Pydantic-Schema, wirft
`shared_lib.config.loader` einen `ConfigError`, der ungebremst durch `main()`,
`asyncio.run()` und `run()` bis zum Prozessende durchschlaegt. Compose steht auf
`restart: unless-stopped` – der Container startet, faellt um, startet, faellt
um.

Das ist kein theoretischer Fall, siehe 1.4: die WebUI kann eine Datei erzeugen,
die das Schema verletzt. Solange der Container laeuft, faellt das nicht auf
(die alte Config bleibt im Speicher). Beim naechsten Update oder Stromausfall
kommt der Dienst dann nicht mehr hoch.

Die [Architecture.md](Architecture.md) beschrieb bisher (Abschnitt 7.2) genau
das gewuenschte Verhalten – "Service geht in einen Fehlerzustand, es werden
keine Action-Events publiziert" –, implementiert war es nie.

**Erledigt:** `load_app_config()` fasst `buttons.json` gar nicht mehr an – es
laedt nur noch die Umgebung. Zustaendig ist allein der `ConfigManager`, und
`ButtonService._load_buttons_config()` faengt einen Ladefehler ab: `ERROR` ins
Log, weiter mit null Buttons, `config_error` auf `/health`. Die kaputte Datei
wird **nicht** ueberschrieben – sie ist ja das, was der Nutzer reparieren muss.

Nebenbei erledigt das den doppelten Ladevorgang aus 3.5: `AppConfig.buttons`
gab es nur noch, um beim Start dieselbe Datei ein zweites Mal zu lesen und
danach einen veralteten Stand zu halten. Das Feld ist weg.

Am lokal gebauten Image gegen 0.1.2 gehalten, dieselbe kaputte Config
(Push-Button ohne `gpio`):

```text
0.1.2 : pydantic_core.ValidationError: gpio must be set for push buttons
        -> Prozess beendet -> restart: unless-stopped -> Schleife

local : config_load_failed  message="Starting without buttons. Fix
                                     config/buttons.json via the WebUI"
        button_service_started
        /health -> degraded, config_error gesetzt
```

Das ist die bewusste Verhaltensaenderung "still weiterlaufen statt laut
sterben" – sie traegt nur zusammen mit 1.2, und 1.2 ist mit drin.

### [x] [H] 1.4 Eine fehlerhafte Config wird in der WebUI als "gespeichert" quittiert

Die Kette hat drei Stellen, an denen niemand hinsieht:

1. **WebUI** (`ButtonConfigPanel.tsx:148`): `isStep0Valid` verlangt nur `name`
   und `id`. Ein Push-Button ohne GPIO-Nummer oder ein Basic-Button ohne
   `action` laesst sich anlegen und speichern.
2. **Backend** (`routes_config.py:_validate_config_shape`): prueft nur, ob
   `body["buttons"]` eine Liste ist. Der Inhalt wird nicht gegen das Schema des
   Button-Service geprueft. `write_json_atomic()` schreibt die Datei, danach
   geht `config/reload` raus, und die Route antwortet `200`.
3. **Button-Service**: `reload_config()` wirft, die alte Config bleibt im
   Speicher (gut), und `_send_config_response(success=False, ...)` geht auf
   `.../button/config/response` – **ein Topic, das kein Dienst abonniert.**

Ergebnis: die WebUI zeigt `buttons.save_success`, auf der Platte liegt eine
Config, die der Dienst nicht laden kann, im Speicher laeuft noch die alte, und
beim naechsten Neustart greift 1.3.

**Erledigt, alle drei Stufen:**

- **WebUI** (`ButtonConfigPanel.tsx`): die Pin-Felder sind Pflicht und werden
  rot, solange sie leer sind; "Weiter" bleibt gesperrt. Im zweiten Schritt
  weist ein Hinweis auf die fehlende Aktion hin, und "Speichern" ist gesperrt,
  bis eine gesetzt ist. Zwei neue Texte in `de/admin.json` und `en/admin.json`.
- **Backend** (`routes_config.py:_validate_buttons_config`): prueft vor dem
  Schreiben genau die Regeln, die der Button-Service prueft, und antwortet
  sonst `422` mit Button-ID und Feldname.
- **WebUI-Rueckmeldung**: der `catch`-Block reichte bisher nur ein nacktes
  "Speichern fehlgeschlagen" durch. Jetzt haengt das `detail` des Backends
  dran, sodass die Meldung sagt, *welcher* Button klemmt.

**Zum Risiko "zu streng":** genau das faengt
`tests/test_button_config_validation.py` ab. 37 Tests, davon 24, die jede
Beispiel-Config **beiden** Seiten vorlegen und verlangen, dass das Urteil
gleich ausfaellt. Der Test hat sofort eine echte Abweichung gefunden: bei
`action: "   "` war meine Backend-Pruefung strenger als Pydantic (`.strip()`
gegen blosse Wahrheitspruefung). Haesslich, aber legal – die Backend-Regel ist
angeglichen, statt dem Nutzer eine Config zu verbieten, die der Dienst laedt.

Der Test laeuft im Repo-venv gegen beide Pakete und ueberspringt sich selbst im
Backend-Image, das den Button-Service nicht kennt.

### [ ] [M] 1.5 Jeder kurze Tastendruck ist grundsaetzlich 400 ms verzoegert

`core/state_machine.py:74-85`: beim Loslassen wird immer erst ein
`threading.Timer(DOUBLE_PRESS_WINDOW_S = 0,4 s)` gestartet, und erst wenn der
ablaeuft, entsteht das `short_press`. Das ist fuer die Doppelklick-Erkennung
noetig – aber nur dann, wenn fuer diesen Button ueberhaupt ein `double_press`
abgebildet ist.

In der ausgelieferten `buttons.json.example` ist das bei **keinem** Button der
Fall: die Push-Buttons stehen auf `mode: "basic"`, dort fuehrt jedes Event zur
selben Aktion. Der Doppelklick wird also erkannt, um dann dasselbe auszuloesen
wie ein Einfachklick – und dafuer wartet jeder normale Tastendruck 400 ms.

Fuer ein Geraet, das Kinder bedienen, ist das der Unterschied zwischen "reagiert
sofort" und "haengt kurz".

**Vorschlag:** den Timer nur setzen, wenn der Button ein `double_press`-Mapping
hat (`mode == "advanced" and "double_press" in actions`). Sonst das
`short_press` direkt beim Loslassen emittieren. Der `PressClassifier` braucht
dafuer ein Flag aus der Button-Config.

**Risiko:** gering und gut testbar (reine Logik, keine Hardware noetig). Sie
aendert das Zeitverhalten sichtbar – deshalb gehoert sie mit echten Tasten
ausprobiert, nicht nur mit Unit-Tests.

### [ ] [M] 1.6 Der Encoder-Taster hat keinerlei Entprellung

`core/event_processor.py:20-23`:

```python
DEBOUNCE_CONFIG = {
    "push": 300,    # 300ms cooldown for push buttons
    "rotary": 0,    # No debounce for rotary encoders
}
```

Die Sperre haengt am **Typ** des Eintrags, nicht am Event. Fuer die Drehung ist
das richtig – die soll ungebremst durchgehen. Der Taster des Encoders (`sw`)
gehoert aber zum selben Eintrag vom Typ `rotary` und faellt damit ebenfalls auf
`0 ms`. Sein `press` wird nur von `bounce_time=0.05` in gpiozero gehalten;
prellt der Taster laenger, geht `mute_toggle` doppelt raus – und schaltet damit
wieder zurueck.

Das ist genau die Konfiguration, die auf der Box laeuft (`btn_1`, `press` →
`mute_toggle`).

**Vorschlag:** die Sperre am `event_type` festmachen statt am Typ des Eintrags:
`rotate_cw`/`rotate_ccw` → 0 ms, alles andere → 300 ms.

**Risiko:** gering. Wichtig ist nur, dass die Drehung wirklich bei 0 ms bleibt,
sonst wird die Lautstaerkeregelung ruckelig.

### [x] [N] 1.7 Pending-Timer werden beim Herunterfahren nicht abgebrochen

`GPIOInputManager.close()` schliesst die gpiozero-Geraete, kennt die
`PressClassifier` aber nicht. Ein laufender `_pending_short_timer` feuert danach
weiter und ruft `loop.call_soon_threadsafe()` auf einem Loop, den es dann
womoeglich nicht mehr gibt – in dem Fall ein `RuntimeError` in einem
Timer-Thread, den niemand faengt.

Dasselbe beim `config/reload`: der alte Classifier feuert nach dem Neuaufbau
noch ein Event mit einer `source_id`, die es in der neuen Config vielleicht gar
nicht mehr gibt (`event_processor_unknown_source`).

Praktisch fast harmlos – das Fenster ist 400 ms breit und der Fehler landet nur
im Log.

**Erledigt**, weil 1.1 den Fall haeufiger macht: `_reinit_gpio()` schliesst und
baut jetzt zuverlaessig neu auf, damit wird der veraltete Timer erreichbarer.
Der `GPIOInputManager` fuehrt seine `PressClassifier` mit und ruft in `close()`
deren neues `cancel_pending()`. `_emit_threadsafe()` faengt zusaetzlich den
`RuntimeError` eines geschlossenen Loops ab – ein gpiozero-Callback-Thread darf
nicht werfen.

---

## 2. Robustheit und Betrieb

### [ ] [N] 2.1 Kein Last Will

`rfid` und `audio` setzen ueber `BaseMQTTClient.set_will()` eine Nachricht, die
der Broker veroeffentlicht, wenn der Dienst ohne Abmeldung verschwindet. Der
Button-Service publiziert beim Start ein `system/service-started` (mit
`remember=True`, wird also nach jedem Reconnect wiederholt) – aber nichts, was
das Gegenteil sagt.

Wer den Zustand ueber MQTT beobachtet, sieht einen abgestuerzten Button-Service
nie. Da der Zustand aktuell ohnehin ueber Docker ermittelt wird, ist das kein
akutes Problem, sondern eine Inkonsistenz zwischen den Diensten.

### [ ] [N] 2.2 `config/update` und `config/get` sind toter Code

Der Dienst abonniert vier Topics (`infrastructure/mqtt_client.py:55-62`). Zwei
davon spricht niemand an:

- `button/config/update`: der einzige moegliche Absender waere
  `backend_service.core.mqtt_client.publish_config_update()` – **diese Methode
  wird nirgends aufgerufen.** Das Backend schreibt `buttons.json` direkt und
  schickt danach `config/reload`.
- `button/config/get`: kein Absender im Repo. Der Handler ist ausserdem
  wirkungslos – `_handle_config_get()` schickt nur
  `{"success": true, "error": null}` zurueck, **ohne die Konfiguration**. Wer
  ihn benutzen wollte, bekaeme keine Antwort auf die gestellte Frage.

In [Offene-Punkte.md](../Offene-Punkte.md) steht unter "Nicht uebernommen", dass
`config/update` beim Button-Service *kein* toter Pfad sei. Das bezog sich auf
eine andere Frage – dort ging es darum, ob der Pfad *funktionieren wuerde*
(beim LED-Service scheitert er am Read-only-Mount). Er funktioniert; er wird nur
von niemandem benutzt. Beides stimmt.

**Vorschlag:** `config/get` entweder vervollstaendigen (Config in die Antwort
legen) oder mit `config/update` zusammen entfernen. Die dritte Moeglichkeit –
alles stehen lassen – ist auch vertretbar, dann sollte es aber in der
Architektur als "vorgesehen, ungenutzt" markiert sein (ist es jetzt).

**Risiko:** Entfernen ist risikoarm, aber es ist eine Schnittstellenaenderung.
Fuer den GoLive nicht noetig.

### [ ] Uebernommen aus [Offene-Punkte.md](../Offene-Punkte.md)

Diese Punkte betreffen den Button-Service mit, sind aber dort schon erfasst und
gehoeren dienstuebergreifend erledigt:

| Punkt | Betrifft den Button-Service so |
|---|---|
| 1.1 Offener Port | `8005:8000` auf allen Interfaces, ohne Authentifizierung |
| 1.2 `degraded` wird nie ausgewertet | macht 1.2 dieses Reviews in der WebUI unsichtbar |
| 2.1 `lg`-Quelle ungepinnt | `git clone` auf `master`, ohne Pruefsumme (siehe 4.4) |
| 2.2 Deutsche Dockerfile-Kommentare | Zeilen 71-74 |
| 2.3 `pyproject.toml`-Version veraltet | `0.1.0` gegen `VERSION 0.1.2` |
| 2.5 `.dockerignore` | `config/buttons.json` landet in lokalen Builds |

---

## 3. Code-Qualitaet

### [~] [M] 3.1 54 ruff-Befunde – jetzt 24

```bash
.venv/bin/ruff check services/button-service/src/
# Found 54 errors (27 fixable)
```

Verteilung: 20 × `E501` (zu lange Zeile), 12 × `W293` (Leerzeile mit
Leerzeichen), 8 × `UP035`/`UP006` (`typing.Dict`/`List` statt `dict`/`list`),
5 × `I001` (Importblock unsortiert), 3 × `UP017` (`datetime.timezone.utc` statt
`datetime.UTC`), 1 × `UP041`, **2 × `F401`**.

Die beiden `F401` sind die einzigen mit Aussagekraft:

- `main.py:6` – `import logging`, nie benutzt.
- `main.py:21` – `from .exceptions import GPIOInitError`, nie benutzt.

Der Rest ist Formatierung.

**Teilweise erledigt:** jede in 1.1-1.4 angefasste Datei ist sauber, die beiden
`F401` sind weg. **54 -> 24.** Der Rest liegt in Dateien, die fuer die
GoLive-Punkte nicht angefasst werden mussten (`event_processor.py`,
`config_schema.py`, `events.py`, `mqtt_client.py`) und gehoert in einen eigenen
Formatier-Branch – dort faellt er als reine Formatierung auf und vermischt sich
nicht mit inhaltlichen Aenderungen.

### [~] [N] 3.2 Drei leere Dateien liegen im Repo – noch eine

```text
services/button-service/src/button_service/core/logic.py        0 Zeilen
services/button-service/src/button_service/models/__init__.py   0 Zeilen
services/button-service/src/button_service/models/schemas.py    0 Zeilen
```

Alle drei sind in Git eingecheckt, keine wird importiert. `models/` ist ein
leeres Paket ohne Inhalt – die Schemas liegen in `config_schema.py`.

**Teilweise erledigt:** `models/` beherbergt jetzt `HealthState` aus 1.2 und
hat damit einen Zweck. `core/logic.py` ist weiterhin leer und kann weg.

### [ ] [N] 3.3 Neun von zehn Exceptions werden nie ausgeloest

`exceptions.py` definiert 64 Zeilen Ausnahme-Hierarchie. Geworfen wird davon
genau eine: `GPIOInitError` (zweimal in `gpio_input_manager.py`). Die anderen
neun – `HardwareError`, `ButtonReadError`, `RotaryEncoderError`,
`ConfigurationError`, `InvalidButtonConfigError`, `InvalidButtonTypeError`,
`StateError`, `UnknownEventTypeError`, `MappingError` – kommen in keiner
`raise`- und keiner `except`-Zeile vor.

`_init_device()` wirft fuer einen unbekannten Typ ein nacktes `ValueError`
(Zeile 142), obwohl `InvalidButtonTypeError` genau dafuer bereitliegt. Erreichbar
ist die Zeile ohnehin nicht, weil das Pydantic-`Literal` vorher greift.

### [~] [N] 3.4 Vier Versionsnummern fuer einen Dienst – jetzt drei

| Ort | Wert |
|---|---|
| `VERSION` | `0.1.2` |
| `pyproject.toml:7` | `0.1.0` |
| `src/button_service/__init__.py:5` | `0.1.0` |
| `api/routes.py:39` (`FastAPI(version=...)`) | `0.1.0` |

`/health` meldet richtig `0.1.2`, weil es `shared_lib.version.get_version()`
benutzt (Build-Arg). Die drei anderen sind seit zwei Releases falsch. Die
OpenAPI-Beschreibung unter `/docs` behauptet damit dauerhaft `0.1.0`.

**Teilweise erledigt:** `routes.py` benutzt jetzt `get_version()`, `/docs`
zeigt also dieselbe Nummer wie `/health` (im lokalen Bau `0.1.2+local`).
`pyproject.toml` gehoert repo-weit erledigt
([Offene-Punkte 2.3](../Offene-Punkte.md)); `__init__.py:__version__` wird
nirgends gelesen und kann weg.

### [ ] [N] 3.5 Kleinigkeiten

- **[x] `AppConfig.buttons` wird nie benutzt.** Erledigt als Teil von 1.3 –
  das Feld ist weg, `load_app_config()` fasst `buttons.json` nicht mehr an.
- **[x] `EnvConfig.api_port` war nicht einstellbar.** `_load_env_config()` ruft
  `load_env()` jetzt mit `optional_defaults={"API_PORT": 8000,
  "DISABLE_GPIO": False}` auf, wie es der Audio- und der LED-Service vormachen.
  Damit liest auch `DISABLE_GPIO` nicht mehr an zwei Stellen direkt aus
  `os.environ`. `EXPOSE` und der Healthcheck stehen weiterhin fest auf 8000 –
  wer den Port verstellt, muss das Port-Mapping ohnehin anfassen.
- **`RawButtonEvent.timestamp` wird verworfen.** Der Zeitstempel entsteht in der
  Hardware-Schicht (`state_machine.py`), wandert durch die Queue – und im
  `event_processor` wird fuer den Publish ein *neuer*
  `datetime.now(timezone.utc)` erzeugt (`mqtt_client.py:83`, `:114`). Der
  Unterschied ist im Normalbetrieb Millisekunden, bei voller Queue mehr.
- **`EncoderRotationEmitter.steps_per_event`** (`state_machine.py:115`) ist
  definiert, dokumentiert und wird nirgends ausgewertet.
- **`main.py:147-149`** ruft `mqtt_client.stop()` (das den Task bereits
  abbricht), danach `_cancel_task(self._mqtt_task)` auf denselben, dann schon
  beendeten Task, und danach noch `mqtt_client.disconnect()` (das `stop()`
  ebenfalls schon getan hat). Wirkungslos, aber irrefuehrend.
- **`config/buttons.json` auf der Box** enthaelt zwei Buttons (`btn_3`, `btn_4`)
  mit derselben Aktion `play_pause`, beide `enabled: false`, einer davon heisst
  "Prev". Kein Fehler – der Dienst erzwingt keine Eindeutigkeit –, aber die
  Namen passen nicht zu den Aktionen.

### [~] [M] 3.6 Null Tests – jetzt 22

`services/button-service/` hat kein `tests/`-Verzeichnis. Zum Vergleich:
backend 15, led 6, rfid 4, audio 3.

Dabei ist gerade dieser Dienst gut testbar, weil die interessante Logik ohne
Hardware auskommt:

- `PressClassifier` – short/long/double, inklusive 1.5.
- `_resolve_action()` – basic/advanced, fehlendes Mapping.
- `ButtonDebouncer.should_fire()` – inklusive 1.6.
- `ButtonConfig`-Validierung – die zwoelf Regeln in `_validate_mode_and_type`.
- `MQTTClient.on_message()` – Topic-Dispatch.

Steht als offener Punkt bereits in [../../ServiceReview.md](../../ServiceReview.md)
("Die State-Machine des Button-Service waere der naechste lohnende Kandidat").

**Teilweise erledigt** – abgedeckt ist, was 1.1-1.4 angefasst haben:

| Datei | Tests | Deckt ab |
|---|---|---|
| `tests/test_gpio_input_manager.py` | 8 | 1.1, 1.7 |
| `tests/test_health_and_startup.py` | 14 | 1.2, 1.3 |
| `backend-service/tests/test_button_config_validation.py` | 37 | 1.4 |

Gesamtsuite 500 -> 559, alle gruen. **Nicht** abgedeckt sind
`PressClassifier` (short/long/double) und `ButtonDebouncer` – die gehoeren zu
1.5 und 1.6 und kommen mit denen zusammen.

---

## 4. Docker-Image

Das aktuelle Image ist **297 MB**. Das ist exakt der Stand, auf dem der
LED-Service vor seinem Review stand – die Dockerfiles sind aus demselben Muster
gebaut. Dort wurden daraus gemessene **229 MB (-68 MB, -23 %)**. Alle vier
Massnahmen greifen hier unveraendert.

Gemessen im laufenden Image (`du -sm site-packages` = 63 MB):

| Paket | Groesse | gebraucht? |
|---|---|---|
| `uvloop` | 17 MB | nein |
| `pip` | 12 MB | nein |
| `setuptools` | 7 MB | nein |
| `yaml` | 4 MB | nein |
| `websockets` | 2 MB | nein |
| `watchfiles` | 2 MB | nein |
| `httptools` | 2 MB | nein |
| `curl` + Abhaengigkeiten (apt) | 14,5 MB | nur fuer den Healthcheck |

### [x] [M] 4.1 `uvicorn[standard]` → `uvicorn` (≈ 27 MB)

`requirements.txt:3`. Der `[standard]`-Extra zieht `uvloop`, `httptools`,
`websockets`, `watchfiles` und `PyYAML` nach. Der Dienst braucht keines davon:
er hat keine WebSockets, kein Auto-Reload, keine YAML-Logkonfiguration
(`log_config=None` in `main.py:128`), und `uvloop` wird nie aktiv, weil
`main.py` den Server in einer selbst gestarteten Event-Loop betreibt –
`uvicorn.Server.serve()` ruft `setup_event_loop()` dann gar nicht auf.

Der LED-Service hat genau diesen Schritt gemacht; der Kommentar dort ist
uebertragbar.

**Risiko:** gering, aber es ist der einzige der vier Punkte, der die Laufzeit
beruehrt. Nach dem Umbau einmal `/health` im lokal gebauten Image abfragen.

### [x] [M] 4.2 `pip`, `setuptools` und `wheel` nicht ins Runtime-Image kopieren (≈ 19 MB)

Zeile 47 kopiert `site-packages` komplett aus dem Builder – inklusive `pip` und
`setuptools`. Das Runtime-Image hat aus `python:3.13-slim` bereits ein eigenes
`pip` in einer Basisschicht; die Kopie legt ein **zweites** darueber. Der
LED-Service hat dafuer 7 MB allein aus dem doppelten `pip` gemessen.

Zusaetzlich: **Zeile 48 (`COPY --from=builder /usr/local/bin /usr/local/bin`)
kann ersatzlos weg.** Der Einstiegspunkt ist `python -m button_service.main`;
die dort liegenden Konsolen-Skripte (`uvicorn`, `fastapi`, `dotenv`,
`watchfiles`, `websockets`, `pinout`, `pintest`) ruft der Dienst nie auf.

### [x] [M] 4.3 `curl` durch einen Python-Healthcheck ersetzen (≈ 14,5 MB)

Zeilen 39-41 installieren `curl` – 14,5 MB mit `libcurl4`, `libssh2`,
`librtmp1`, `libnghttp2/3` – ausschliesslich fuer den `HEALTHCHECK`. Python ist
im Image und kann dieselbe Anfrage stellen. Dann faellt der komplette
apt-Layer aus dem Runtime-Stage weg:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"
```

**Achtung:** Der Healthcheck in `docker-compose.yml:318` ruft ebenfalls `curl`
auf und ueberschreibt den aus dem Dockerfile. Beide muessen zusammen geaendert
werden, sonst ist der Container dauerhaft `unhealthy` und `depends_on` blockiert
– beim LED-Service steht die entsprechende Zeile schon richtig drin.

### [x] [H] 4.4 Die `lg`-Quelle wird unversioniert und ungeprueft gebaut

Zeile 18: `git clone --depth 1 https://github.com/joan2937/lg` – ohne Tag, ohne
Pruefsumme. Kein CI-Build ist reproduzierbar, und ein kompromittiertes Upstream
landet ungeprueft in einem Image, das als root baut und danach GPIO-Zugriff
bekommt. Steht als [Offene-Punkte 2.1](../Offene-Punkte.md); der LED-Service
zeigt die fertige Loesung (Tag `v0.2.2` plus SHA-256, `wget` statt `git`).

Nebenbei entfaellt damit `git` aus dem Builder. `python3-dev` (Zeile 13) ist
ebenfalls ueberfluessig – `python:3.13-slim` bringt die Header unter
`/usr/local/include/python3.13` mit; der LED-Builder kommt ohne aus und
uebersetzt `lgpio` problemlos.

### [x] [M] 4.5 `RPi.GPIO` und `tenacity` sind unbenutzte Abhaengigkeiten

`requirements.txt:13` und `:18`.

- **`tenacity`** kommt in keiner Zeile des Dienstes vor. Die Wiederhollogik
  liegt in `BaseMQTTClient` und ist von Hand geschrieben.
- **`RPi.GPIO`** wird ebenfalls nirgends importiert. Die Pin-Factory ist fest
  `lgpio` – im Dockerfile (`GPIOZERO_PIN_FACTORY=lgpio`), im Compose-Block
  (Zeile 303) und im Code (`gpio_input_manager.py:38`, das eine andere Factory
  aktiv ersetzt). Im Image ist das Paket vorhanden, aber nicht einmal
  importierbar:

  ```text
  RuntimeError: This module can only be run on a Raspberry Pi!
  ```

  (Es liest `/proc/device-tree`, das im Container nicht gemountet ist – die
  README des Dienstes beschreibt einen Mount, den `docker-compose.yml` gar nicht
  anlegt.)

  Wichtig fuer Abschnitt 5: `RPi.GPIO` steht in
  [../../ServiceReview.md](../../ServiceReview.md) als moeglicher Ausweg aus dem
  CPU-Verbrauch. Das ist **keine gute Idee** – die Bibliothek greift direkt auf
  die BCM-Register zu und funktioniert auf dem Pi 5 (RP1, `gpiochip4`)
  grundsaetzlich nicht mehr. Sie gehoert entfernt, nicht benutzt.

### [x] [N] 4.6 Kleinigkeiten im Dockerfile

- `PYTHONDONTWRITEBYTECODE=1` und `PYTHONUNBUFFERED=1` fehlen (LED hat beide).
- `useradd`, `mkdir /tmp/lgpio` und `chown -R /app` sind drei `RUN`-Schichten
  (Zeilen 57, 60, 62) und liessen sich zu einer zusammenfassen.
- `/tmp/lgpio` (Zeile 60) wird angelegt, aber von nichts benutzt: `lgpio` legt
  seine Notify-Datei `.lgd-nfy0` im Arbeitsverzeichnis an, also in `/app` – und
  das ist ohnehin schon beschreibbar.
- Der Versions-Block am Dateiende ist deutsch
  ([Offene-Punkte 2.2](../Offene-Punkte.md)).

### Ergebnis

Gemessen statt geschaetzt, `./scripts/build-local.sh button`:

| | vorher | nachher |
|---|---|---|
| Image gesamt | 297 MB | **229 MB** |
| `site-packages` | 63 MB | **27 MB** |
| `curl` + Abhaengigkeiten | 14,5 MB | **0** |
| apt-Layer im Runtime-Stage | 1 | **0** |

**-68 MB (-23 %)**, ohne eine Zeile Anwendungscode – dieselbe Zahl, die der
LED-Service aus demselben Muster geholt hat.

Der Healthcheck im `docker-compose.yml` wurde mitgeaendert (er ueberschreibt
den aus dem Dockerfile; waere er auf `curl` stehengeblieben, waere der
Container dauerhaft `unhealthy` und `depends_on` haette blockiert).

---

## 5. Laufzeitverbrauch – 8 % CPU im Leerlauf, jetzt 3 %

Der Button-Service ist mit Abstand der groesste Verbraucher der Box:

| Container | CPU (Mittel ueber 166 s) | RSS |
|---|---|---|
| **minabox-button** | **8,1 %** | 12,4 MB |
| minabox-display | 4,4 % | 26,1 MB |
| minabox-led | 3,0 % | 45,8 MB |
| minabox-rfid | 2,9 % | 13,6 MB |
| minabox-backend | 1,9 % | 99,4 MB |
| minabox-audio | 0,5 % | 17,3 MB |

Der Punkt steht als offen in [../../ServiceReview.md](../../ServiceReview.md),
mit dem Befund "die Last liegt in einem C-Thread, der in `ppoll` haengt".
**Die Ursache ist jetzt gefunden.**

### Ursache

`/proc/1/task/*` des laufenden Containers zeigt acht Threads. Einer davon
verbraucht praktisch alles, und fast nur Systemzeit:

```text
tid=26  wchan=poll_schedule_timeout  utime/stime=175340/869495   ->  4,9 %
tid=25  wchan=hrtimer_nanosleep      utime/stime=3807/24473      ->  1,3 %
tid=1   wchan=do_epoll_wait          utime/stime=72360/7102      ->  0,4 %
```

Das ist der Alert-Thread von `liblgpio`. In `lg` v0.2.2, `lgPthAlerts.c:438`:

```c
struct timespec tspec = {0, 5e5}; /* 0.5 ms timeout */
...
retval = ppoll(pfd, num_gpio, &tspec, NULL);
```

Der Thread weckt sich **2000-mal pro Sekunde**, unabhaengig davon, ob irgendein
Pin sich bewegt hat. Der Wert steht als Konstante in der C-Quelle und ist ueber
die Python-Schnittstelle nicht erreichbar.

### Nachgemessen

Vier identische Container, jeweils gleiche Konfiguration, Mittel ueber 166-188 s
(`/proc/1/stat`, nicht `docker stats`):

| Variante | Pins | CPU |
|---|---|---|
| `DISABLE_GPIO=true` (kein `lgpio`) | 0 | **0,5 %** |
| unveraendert, `tspec = 0,5 ms` | 1 | **6,4 %** |
| unveraendert, `tspec = 0,5 ms` | 5 (Produktivstand) | **8,1 %** |
| gepatcht, `tspec = 2 ms` | 1 | **2,8 %** |
| gepatcht, `tspec = 5 ms` | 1 | **1,8 %** |

Damit ist zweierlei belegt:

1. **Der Verbrauch ist fast vollstaendig ein Fixkostenblock.** Ein einziger
   ueberwachter Pin kostet schon 6 %; jeder weitere nur noch etwa 0,4 %. Weniger
   Buttons zu konfigurieren hilft also praktisch nicht.
2. **Der Python-Code des Dienstes ist unschuldig.** Ohne GPIO liegt derselbe
   Prozess bei 0,5 % – Event-Loop, MQTT-Client und die
   Sekunden-Warteschleife im `event_processor` fallen nicht ins Gewicht.

### Umgesetzt: Option B, `tspec` beim Build gepatcht

Das `sed` steht jetzt im Dockerfile zwischen Entpacken und `make`, mit dem Wert
als Build-Arg, damit er ohne Codeaenderung verstellbar ist:

```dockerfile
ARG LG_ALERT_POLL_NS=2000000
RUN ... && sed -i "s/struct timespec tspec = {0, 5e5};/struct timespec tspec = {0, ${LG_ALERT_POLL_NS}};/" lgPthAlerts.c \
        && grep -q "struct timespec tspec = {0, ${LG_ALERT_POLL_NS}};" lgPthAlerts.c \
        && make ...
```

Das `grep` ist Absicht: schreibt eine kuenftige `lg`-Version diese Zeile um,
soll der Bau abbrechen statt still eine ungepatchte Bibliothek auszuliefern.

Zum Ausprobieren ohne Codeaenderung:

```bash
docker compose build --build-arg LG_ALERT_POLL_NS=500000 button   # Upstream
docker compose build --build-arg LG_ALERT_POLL_NS=5000000 button  # 5 ms
```

**Gemessen am fertigen Image** (`/proc/1/stat`, Fenster 211 s):

| | Pins | CPU |
|---|---|---|
| 0.1.2 im Betrieb, 0,5 ms | 5 | 8,2 % |
| lokales Image, 2 ms | 2 | **3,1 %** |

Der Vergleich hinkt um drei Pins, weil die Produktivpins vom laufenden
Container gehalten werden. Aus den Einzelpin-Messungen (0,5 ms: 6,4 %; 2 ms:
2,8 %) und dem Zuwachs pro Pin ist fuer die echte Fuenf-Pin-Config mit **rund
3,5-4 %** zu rechnen, also gut die Haelfte. Bestaetigt sich beim Ausrollen.

**Noch offen: der Hardware-Test.** Dass die Bibliothek baut, laedt und Pins
belegt, ist geprueft. Ob sich der Drehknopf gleich anfuehlt, laesst sich nur am
echten Encoder beurteilen – ohne angeschlossene Taster gibt es keine Flanken zu
messen. Genau das ist der Teil, der auf der Box passieren muss.

**Was der Patch bewirkt und was nicht:** Der `ppoll` kehrt bei einer echten
Flanke *sofort* zurueck (`POLLIN`) – der Timeout regelt nur die Leerlauf-
Weckrate. Die Zeitstempel der Ereignisse kommen ohnehin vom Kernel und aendern
sich nicht. Was sich aendert, ist der Zeitpunkt der *Weitergabe*: `lg` sammelt
Ereignisse und gibt sie erst im naechsten Schleifendurchlauf sortiert heraus
(`emit(count, nowGT-500000)`, Zeile 590 – ein Verzoegerungsfenster von 0,5 ms
ist also bereits eingebaut). Mit 2 ms statt 0,5 ms wird daraus im schlechtesten
Fall 2,5 ms.

Fuer einen Tastendruck (≥ 30 ms) ist das nicht wahrnehmbar. Fuer den
Drehencoder heisst es, dass bei sehr schnellem Drehen mehrere Schritte gebuendelt
statt einzeln ankommen. **Verloren geht keiner** – der Kernel puffert die
Flanken im Line-Event-FD, und `gpiozero` zaehlt jede.

**Verbleibendes Risiko: mittel.** Es ist ein Eingriff in eine fremde
C-Bibliothek, der bei jedem `lg`-Update mitgepflegt werden muss. Faellt der
Encoder unangenehm auf, ist der Rueckweg ein Build-Arg weit
(`LG_ALERT_POLL_NS=500000`) – dann bleiben immer noch -68 MB aus Abschnitt 4.

**Option C – weg von `gpiozero`/`lgpio`,** direkt auf `libgpiod` mit blockendem
`read()` auf dem Line-Event-FD. Das waere der saubere Weg (0 % im Leerlauf),
bedeutet aber, die Hardware-Schicht neu zu schreiben. Kein GoLive-Thema.

**Kein Weg: `RPi.GPIO`.** Siehe 4.5 – auf dem Pi 5 nicht mehr funktionsfaehig.

Der zweite Thread (`tid=25`, `hrtimer_nanosleep`, 1,3 %) gehoert ebenfalls zu
`lg` und wurde nicht weiter verfolgt; er ist ein Fuenftel des Hauptpostens.

---

## 6. Was ich nicht anfassen wuerde

- **Die FIFO-Kette Hardware → Queue → Processor → MQTT.** Sie ist richtig
  aufgebaut: die gpiozero-Callbacks laufen in fremden Threads und kommen ueber
  `loop.call_soon_threadsafe()` sauber in den Event-Loop
  (`gpio_input_manager.py:89`). Genau das ist die Stelle, an der solche Dienste
  ueblicherweise falsch liegen.
- **Die Reihenfolge im `event_processor`** – erst entprellen, dann `raw-event`,
  dann `enabled` pruefen, dann die Aktion. Sie ist ungewoehnlich (der
  `raw-event` geht auch fuer abgeschaltete Buttons raus), aber sie ist bewusst
  so gebaut, damit der Hardware-Test in der WebUI auch deaktivierte Tasten
  zeigt, und sie ist im Code an Ort und Stelle begruendet.
- **Der Direktversand von `volume_up`/`volume_down` an den Audio-Service**
  (`event_processor.py:169`). Das umgeht das Backend und spart eine Station –
  eine bewusste Abkuerzung fuer die Latenz, und der Backend-Handler
  (`button_handler.py:57`) weiss davon und tut fuer diese beiden Aktionen
  absichtlich nichts.
- **`BaseMQTTClient`.** Der Dienst nutzt ihn korrekt: Subscriptions vor dem
  ersten Connect registriert, `service-started` mit `remember=True`, `start()`
  blockiert nicht auf dem Broker. Da ist nichts zu holen.
- **`python:3.13-slim` gegen Alpine.** `lgpio` und `gpiozero` gegen musl zu
  bauen ist eine eigene Baustelle, und nach 4.1-4.3 ist der Gewinn klein.

---

## 7. Wie es weitergeht

**Erledigt und bereit zum Ausrollen:** 1.1, 1.2, 1.3, 1.4, 1.7, Abschnitt 4
komplett, Abschnitt 5, und Teile von 3.1/3.2/3.4/3.5/3.6.

**Auf der Box zu pruefen, sobald das Image ausgerollt ist:**

1. Der Drehknopf – fuehlt sich die Lautstaerkeregelung mit dem 2-ms-Patch
   unveraendert an? Der Rueckweg ist ein Build-Arg
   (`LG_ALERT_POLL_NS=500000`), siehe Abschnitt 5.
2. `docker stats minabox-button` – erwartet werden rund 3,5-4 % statt 8,2 %.
3. `curl -s localhost:8005/health` – `buttons_available` muss
   `buttons_configured` erreichen.
4. Einmal im Admin-Bereich einen Button ohne Pin anzulegen versuchen: "Weiter"
   muss gesperrt bleiben.

**Als naechstes, in dieser Reihenfolge:**

5. **1.5** – Doppelklick-Fenster nur bei vorhandenem Mapping. Spuerbarster
   Gewinn fuer den Nutzer, aber sichtbare Verhaltensaenderung: erst Tests fuer
   `PressClassifier`, dann umbauen, dann mit echten Tasten ausprobieren.
6. **1.6** – Entprellung am `event_type` statt am Typ des Eintrags. Betrifft
   den Encoder-Taster (`mute_toggle` kann doppelt feuern).
7. **3.1** – der Formatier-Rest (24 ruff-Befunde) als eigener Branch.
8. **2.1, 2.2, 3.2, 3.3, 3.4** – Last Will, toter Config-Pfad, Aufraeumen.

**Dienstuebergreifend**, nicht hier: der offene Port 8005, der nie ausgewertete
`degraded`-Status (ohne den bleibt 1.2 in der WebUI unsichtbar) und
`.dockerignore` – alles in [../Offene-Punkte.md](../Offene-Punkte.md).
