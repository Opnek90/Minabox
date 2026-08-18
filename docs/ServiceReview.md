# Service-Review (ohne WebUI)

Review der neun Services unter `services/` außerhalb der WebUI, Stand 2026-08-18.
Umgesetzt auf dem Branch `refactor/services-hardening`.

Gegenstück zu [Optimierungen.md](Optimierungen.md), das überwiegend die WebUI behandelt.

Legende: `[x]` umgesetzt · `[ ]` offen · `[~]` teilweise

---

## 1. Behobene Fehler

### [x] Endlosschleife mit 100 % CPU im Temperatur-Logger

`core/temperature_logger.py` – die Schleife sah so aus:

```python
while True:
    data = await _fetch_host_status()
    if not data:
        continue          # kein sleep
    temp = data.get("temperature_celsius")
    if temp is None:
        continue          # kein sleep
    ...
    await asyncio.sleep(LOG_INTERVAL_SECONDS)   # erst am Ende
```

Antwortete der Host-Helper nicht, sprang die Schleife ohne Pause zurück an den
Anfang. Bei fehlendem `HOST_HELPER_API_KEY` kehrt `_fetch_host_status()` sogar
**ohne jedes I/O** sofort mit `None` zurück. Praxisnah ausgelöst durch jedes
`POST /system/restart`, das den Host-Helper kurz stilllegt.

Gemessen (`asyncio`-Zähler, 0,5 s Wanduhr-Zeit, im echten Backend-Image):

| | Abfragen in 0,5 s |
|---|---|
| vorher | **356.804** |
| nachher | 48 (eine pro Iteration) |

Der Effekt ist dabei gravierender als „ein Kern läuft heiß": ohne API-Key
enthält der Schleifenrumpf **keinen einzigen echten await-Punkt**, die Coroutine
gibt die Kontrolle also nie an den Event-Loop zurück. Selbst ein
`asyncio.wait_for()` von außen kann sie nicht abbrechen. Damit steht nicht nur
das Temperatur-Logging, sondern der gesamte Backend-Prozess – FastAPI,
WebSocket und MQTT-Verarbeitung inklusive. Ist der Schlüssel gesetzt (der
Normalfall), yieldet der HTTP-Versuch immerhin, dann bleibt es beim Hämmern
gegen den Host-Helper.

**Umgesetzt:** Der Schleifenrumpf steckt jetzt in `_sample_temperature_once()`.
Das Intervall-`sleep` läuft nach *jeder* Iteration, auch wenn keine Messung
zustande kam. Zusätzlich fängt die Schleife unerwartete Fehler ab, statt am
Task zu sterben.

### [x] `is_connected` ist ein Property, wurde aber aufgerufen

`MQTTClient.is_connected` ist mit `@property` dekoriert, der Temperatur-Logger
schrieb an zwei Stellen `mqtt_client.is_connected()`. Das ergibt
`TypeError: 'bool' object is not callable` – außerhalb des `try`, also starb der
gesamte Task. Folge: Beim ersten Überschreiten der Temperaturschwelle brach das
Temperatur-Logging ab, der Alarm wurde weder gesendet noch je wieder aufgehoben.
Genau der Pfad, der im Ernstfall funktionieren müsste.

**Umgesetzt:** Zugriff als Property. Durch Regressionstests abgesichert.

### [x] `NameError` statt sauberer Fehlermeldung im Host-Helper

`import docker` stand innerhalb des `try`-Blocks, die Handler darunter
referenzierten `docker.errors.*`. Fehlt das Paket, ist `docker` beim Auswerten
der except-Klausel ungebunden → `NameError` statt der gedachten 503.

**Umgesetzt:** Import auf Modulebene, `DockerNotFound`/`DockerAPIError` explizit
importiert. Der Docker-Aufruf läuft jetzt zusätzlich über `asyncio.to_thread`.

### [x] `DatabaseManager.is_connected()` unter SQLAlchemy 2.x kaputt

`conn.execute("SELECT 1")` mit rohem String wirft in 2.x
`ObjectNotExecutableError`; die Methode lieferte immer `False`. Folgenlos, weil
sie nirgends aufgerufen wird – toter Code mit latentem Fehler.

**Umgesetzt:** `text("SELECT 1")`.

### [x] Totes, nicht importierbares Paket `host_helper/core/`

`host_helper/core/__init__.py` exportierte `create_app`, `run` und
`setup_logging` aus einem `.main`, das es in diesem Paket nie gab – die echten
Funktionen liegen in `host_helper/main.py`. Nichts referenzierte das Paket;
`import host_helper.core` schlug schlicht fehl. Beim Import-Check aufgefallen.

**Umgesetzt:** Paket entfernt.

---

## 2. Blockierende I/O im Event-Loop

Das war das durchgängigste Muster im Bestand. `asyncio.to_thread` kam im ganzen
Repo nur an zwei Stellen vor; überall sonst lief blockierender Code direkt auf
dem Loop.

### [x] `pactl` alle 2 Sekunden, dauerhaft

Die Status-Schleife des Audio-Service (`core/service.py`, alle 2 s) rief über
`get_audio_devices()` bei jedem Durchlauf `PulseSinkDetector.detect_sinks()` –
ein blockierendes `subprocess.run(["pactl", "list", "sinks"], timeout=10)`. Also
ein Prozess-Fork alle 2 Sekunden für immer, der den Audio-Loop währenddessen
anhält.

**Umgesetzt:** `PulseSinkDetector` cached die Sink-Liste (`CACHE_TTL_SECONDS = 10`)
und führt `pactl` über `asyncio.to_thread` aus. Invalidiert wird gezielt dort, wo
sich Sinks tatsächlich ändern (`_reinitialize_and_resume`, also Gerätewechsel,
Bluetooth und Config-Reload). Die explizite Geräteabfrage der WebUI
(`GET /devices`) umgeht den Cache per `force_refresh=True`, damit ein gerade
eingeschalteter Lautsprecher sofort auftaucht.

Effekt: statt 30 `pactl`-Aufrufen pro Minute noch 6, plus je einer bei echten
Änderungen.

Zur TTL: 30 s wären sparsamer, aber der Display-Service leitet aus
`bluetooth_sink_available` sein Bluetooth-Symbol ab – ein gerade gekoppelter
Lautsprecher bräuchte dann bis zu 30 s, bis er auf dem OLED auftaucht. Die
zusätzlichen 4 eingesparten Aufrufe pro Minute sind das nicht wert. Sauber wäre
eine ereignisgesteuerte Invalidierung beim Bluetooth-Connect; dafür müsste der
Host-Helper den Audio-Service erreichen können – offen.

### [x] Display-Service: httpx-Client pro Poll statt pro Loop

Der Display-Service war mit 5,75 % der zweitgrößte CPU-Verbraucher der Box –
mehr als das Siebenfache des Audio-Services. Die naheliegende Vermutung (die
Render-Schleife zeichnet jede Sekunde neu) war **falsch**; ein py-spy-Profil des
laufenden Containers zeigte die tatsächliche Ursache:

```
_sleep_timer_poll_loop → _poll_backend → httpx … → aclose → _close_connections
  → current_async_library → _find_and_load → find_spec → _get_spec
```

`_poll_backend()` erzeugte den `httpx.AsyncClient` **innerhalb** der Schleife.
httpcore führt beim Schließen eine Import-Suche aus (`current_async_library`),
und bei zwei Poll-Loops à 5 s lief diese Import-Maschinerie im Dauerbetrieb.

**Umgesetzt:** Der Client lebt jetzt für die Laufzeit der Schleife – gleiches
Muster wie beim Host-Helper-Proxy. Nebenbei bleibt die Verbindung offen.

Gemessen bei Ruhe (0 WebUI-Requests/min), im laufenden Betrieb:

| | minabox-display |
|---|---|
| vorher | 5,75 % |
| nachher | 1,45 % / 1,92 % (zwei Messungen) |

Nicht angefasst: Dieselbe Konstruktion steht in `media_downloader_client.py`,
dort aber in einer Retry-Schleife mit maximal drei Versuchen, die nur beim
Download läuft. Ein frischer Client nach einem Verbindungsfehler ist dort eher
erwünscht.

### [~] Display: Vollbild-Neuaufbau im Sekundentakt

Die Render-Schleife rief `show_areas()` jede Sekunde bedingungslos auf – voller
PIL-Bildaufbau plus I2C-Übertragung. Das Uhr-Element löst aber nur auf `%H:%M`
auf, im Leerlauf ändert sich der Inhalt also einmal pro Minute; 59 von 60
Frames waren überflüssig. Der OLED (`0x3c`) teilt sich dabei `/dev/i2c-1` mit
dem PN532-RFID-Leser (`0x24`) – laut `Optimierungen.md` ohnehin ein
Robustheitsthema.

**Umgesetzt:** Fingerprint über Inhalt, Schriftgröße und Schriftart; gezeichnet
wird nur bei Änderung. Dazu ein erzwungener Neuaufbau alle 60 s, damit ein
verglitchtes Panel sich selbst heilt, und ein Reset des Fingerprints, wenn das
Display neu verfügbar wird.

**Ehrlich zum Nutzen:** Das brachte **keine messbare CPU-Ersparnis**
(5,75 % → 6,22 %, danach erst der httpx-Fix). Die eingesparten I2C-Transaktionen
konnte ich mit den verfügbaren Mitteln nicht direkt messen – `/proc/*/io`
erfasst sie nicht, weil sie über `ioctl` laufen. Die Änderung bleibt drin, weil
sie logisch belegt und getestet ist (9 Tests) und die Buslast gegenüber dem
RFID-Leser senkt; als CPU-Optimierung taugt sie nachweislich nicht.

### [ ] Button-Service: 7,9 % CPU im Leerlauf

Der größte verbleibende Verbraucher. Ein py-spy-Profil zeigt **keinen**
Python-Code als Ursache; die Last liegt in einem C-Thread, der laut `/proc` in
`ppoll` hängt – also in der lgpio-Ebene unterhalb von gpiozero, nicht im
Minabox-Code. Ein Wechsel der Pin-Factory (`RPi.GPIO` steht ohnehin in den
Requirements) wäre der nächste Ansatz, ist aber ein Hardware-Eingriff mit
eigenem Testbedarf.

### [x] Datei-Upload fror das Backend ein

`routes_tracks.py:upload_track` war `async def` und machte
`shutil.copyfileobj(file.file, buffer)` synchron, dazu Mutagen-Parsing und
Cover-Extraktion. Beim Hochladen eines Hörbuchs stand das gesamte Backend
inklusive WebSocket und Player-Steuerung für die Dauer des Schreibvorgangs.

**Umgesetzt:** Schreiben und Tag-Auswertung in `_store_uploaded_track()`
ausgelagert und über `asyncio.to_thread` aufgerufen.

### [x] Host-Helper: 42 blockierende Handler auf dem Event-Loop

Von 45 Route-Handlern hatten **42 gar kein `await`** – sie waren nur aus
Gewohnheit `async def` und riefen darin blockierendes `subprocess.run` mit
Timeouts bis 120 s. Während `/restart` lief, beantwortete der Host-Helper keinen
einzigen anderen Request, auch den Healthcheck nicht.

**Umgesetzt:** Alle 42 auf `def` umgestellt – FastAPI führt synchrone Handler
automatisch im Threadpool aus. Kein Logikeingriff, ein Wort pro Handler.
Die drei echt asynchronen Handler bleiben `async`:

- `backup_restore` – Compose down/up plus Entpacken jetzt in
  `_restore_backup_archive()` über `asyncio.to_thread`
- `bluetooth_scan` – `proc.wait()`/`reader.join()` über `asyncio.to_thread`
- `container_logs` – Docker-SDK-Aufruf über `asyncio.to_thread`

### [x] Synchrones SQLAlchemy in `async def`-Routen

48 Backend-Routen nahmen `db: Session = Depends(get_db)` und liefen als
`async def` – jede DB-Query blockierte damit den Event-Loop.

**Umgesetzt:** 41 Routen auf `def` umgestellt (Threadpool). Bewusst *nicht*
umgestellt:

- 7 Routen, die tatsächlich `await` verwenden (Uploads)
- `create_track_from_url` – ruft `asyncio.create_task()` ohne `await`. Als
  synchrone Funktion im Threadpool gäbe es keinen laufenden Event-Loop, der
  Download-Task würde nie starten. Die Route bleibt `async def`.

Der letzte Punkt ist der Grund, warum diese Umstellung nicht blind über alle
Handler laufen darf.

---

## 3. Struktur & Duplizierung

### [x] `routes_host.py`: 1197 Zeilen, fast alles Copy-Paste

44 Proxy-Endpunkte wiederholten denselben ~25-Zeilen-Block: URL bauen, API-Key
prüfen, `httpx.AsyncClient` erzeugen, 401 behandeln, ≥400 behandeln, Detail
extrahieren, `RequestError` fangen. Zusätzlich wurde **pro Request ein neuer
`httpx.AsyncClient`** aufgebaut – kein Connection-Pooling, jedes Mal ein neuer
TCP-Handshake.

**Umgesetzt:** Zwei Helfer tragen jetzt die gesamte Logik:

- `_proxy(...)` – strikt: reicht Fehler an den Aufrufer durch
- `_proxy_optional(...)` – weich: liefert einen neutralen Fallback, wenn der
  Host-Helper fehlt oder klemmt (für Status-Kacheln, die die
  Einstellungsseite nicht mitreißen dürfen)

Dazu ein gepoolter `httpx.AsyncClient` auf Modulebene, der beim Shutdown über
`close_host_helper_client()` in `app_factory.stop()` geschlossen wird.
Datei von 1197 auf 909 Zeilen; alle 45 Routen, Signaturen und das
OpenAPI-Schema unverändert (geprüft, siehe Abschnitt 6).

**Eine bewusste Verhaltensänderung:** Ein 401 vom Host-Helper wird jetzt
einheitlich als 503 gemeldet. Vorher taten das nur ~25 der Endpunkte, der Rest
reichte die 401 durch – und die WebUI liest 401 als „Sitzung abgelaufen" und
würde die Eltern bei einer reinen Server-Fehlkonfiguration ausloggen.

### [ ] `host-helper/api/routes.py`: weiterhin 2138 Zeilen in einer Datei

WLAN, Bluetooth, USB, Backup, Netzwerk, Updates, Board-LEDs und Container-Logs
liegen in einem Modul. Die Aufteilung entlang der bereits vorhandenen
Kommentar-Abschnitte in Sub-Router wäre naheliegend, ist aber ein eigener,
größerer Umbau – hier bewusst nicht mit den Fehlerkorrekturen vermischt.

### [ ] `BaseMQTTClient` in der shared-lib ist toter Code

`shared_lib/mqtt/base_client.py` wird von keinem Service abgeleitet (per Grep
über das ganze Repo verifiziert). Stattdessen hat jeder der sechs
MQTT-Services seinen eigenen Client mit **identisch kopierter** Reconnect-Logik
(`reconnect_delay = 2.0`, verdoppeln, Cap bei 60 s): audio, button, display,
led, rfid und backend. Ironischerweise implementiert die ungenutzte Basisklasse
den Reconnect gar nicht, obwohl ihr Docstring ihn verspricht.

Der übrige Teil der shared-lib (`config`, `logging`, `exceptions`) wird gut
genutzt. Die Konsolidierung berührt sechs Services gleichzeitig und gehört
darum in einen eigenen Branch mit eigenem Hardware-Test.

### [ ] Topic-Konstruktion an ~10 Stellen dupliziert

`f"minabox/{device_id}"` wird in jedem Service neu zusammengebaut,
`get_mqtt_topic()` aus der shared-lib nur zweimal verwendet. Die Topic-*Namen*
selbst (`audio/status`, `rfid/presence`, `system/service-started`, …) sind reine
String-Literale ohne zentrale Registry – ein Tippfehler auf einer Seite trennt
die Kopplung lautlos, und kein Test fängt das auf. Sinnvoll gemeinsam mit der
`BaseMQTTClient`-Konsolidierung.

---

## 4. Konfiguration & Deployment

### [x] Der dokumentierte Schnellstart schlug fehl

README nannte `cp .env.example .env && docker compose up -d`. `docker-compose.yml`
fordert aber `HOST_HELPER_API_KEY=${HOST_HELPER_API_KEY:?...}`, und in
`.env.example` kam die Variable überhaupt nicht vor – Compose brach sofort ab.

**Umgesetzt:** `HOST_HELPER_API_KEY` in `.env.example` dokumentiert (bewusst
leer, kein mitgelieferter Default-Schlüssel), README um den
Generierungsschritt ergänzt:

```bash
cp .env.example .env
echo "HOST_HELPER_API_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d
```

Zusätzlich in `.env.example` ergänzt: `WEB_AUTH_SECRET`, `AUDIO_FILES_PATH`,
`ALLOWED_AUDIO_PATHS`, `TZ`, `HOST_IP`, `DISABLE_GPIO` und die
`MEDIA_DOWNLOADER_*`-Variablen – allesamt in Compose referenziert, aber nirgends
beschrieben.

### [x] `WEB_AUTH_SECRET` war nicht durchgereicht

`core/auth.py` liest die Variable, `docker-compose.yml` gab sie nie weiter – aus
`.env` war sie also gar nicht setzbar. Ohne sie fällt das JWT-Signaturgeheimnis
auf `HOST_HELPER_API_KEY` zurück, ein Schlüssel für zwei Zwecke.

**Umgesetzt:** In den Backend-Block der Compose-Datei aufgenommen.

### [x] `media-downloader-service` hing hinterher

Als einziger Service exakt gepinnt (`fastapi==0.115.6`, `pydantic==2.10.4`,
`structlog==25.1.0`) statt auf den Bereichen der übrigen Services.

**Umgesetzt:** Auf dasselbe Versionsniveau gehoben wie der restliche Stack.

### [x] `passlib` war eine ungenutzte Abhängigkeit

`core/auth.py` importiert `bcrypt` direkt; `passlib` kam in keiner Zeile
Quelltext vor. Heikel dabei: `bcrypt` stand nirgends als direkte Dependency, es
kam nur transitiv über die `passlib[bcrypt]`-Extra herein.

**Umgesetzt:** `passlib[bcrypt]` durch ein direktes `bcrypt>=4.1.0,<6.0.0`
ersetzt. `python-jose` bleibt – anders als im ersten Bericht behauptet ist die
zulässige Version 3.5.0 gepinnt und hat die CVEs von 2024 bereits behoben; ein
Bibliothekswechsel wäre reiner Umbau ohne Sicherheitsgewinn. Untergrenze auf
`>=3.5.0` angehoben, damit die gepatchte Version auch wirklich erzwungen ist.

### [ ] Dev-Reste in der Produktions-Compose

`./.cursor:/cursor-debug` ist in Backend *und* Host-Helper gemountet. Nicht
angefasst, weil unklar ist, ob das lokal noch gebraucht wird – Entscheidung
liegt beim Betreiber.

---

## 5. Sicherheit

Der Host-Helper mountet `/:/host:rw` mit `pid: host`, `user 0:0` und
`SYS_ADMIN`. Das ist bei diesem Zweck Absicht, macht die Zugangsprüfung aber zum
einzigen Riegel.

### [x] API-Key-Vergleich war nicht zeitkonstant

`_check_api_key` verglich mit `!=`.

**Umgesetzt:** `secrets.compare_digest`, plus expliziter Guard gegen einen
leeren erwarteten Schlüssel.

### [ ] Kein Rate-Limiting

Weder auf `/api/v1/auth/login` noch auf den Host-Helper-Endpunkten. Beim Login
kommt hinzu, dass `bcrypt.checkpw` auf einem Pi bewusst 100–300 ms braucht und
im `async def`-Handler den Event-Loop blockiert – das ist zugleich ein
billiger DoS. Fix wäre ein Fehlversuchs-Zähler mit Sperrzeit plus
`asyncio.to_thread` um die Prüfung. Nicht umgesetzt, weil es eine
Produktentscheidung ist (Sperrdauer, Verhalten bei ausgesperrten Eltern).

### [ ] Hardcodierter Fallback-Secret

`core/auth.py` fällt auf `"minabox-web-auth-dev-secret"` zurück, wenn weder
`WEB_AUTH_SECRET` noch `HOST_HELPER_API_KEY` gesetzt sind. Greift praktisch nie,
weil Compose `HOST_HELPER_API_KEY` erzwingt. Sauber wäre, beim Start hart
abzubrechen statt still auf ein bekanntes Geheimnis zu fallen.

### [ ] WLAN-Passwörter stehen in der Prozessliste

`wifi_connect` übergibt `wifi-sec.psk` als Kommandozeilenargument an `nmcli`,
damit ist es für jeden auf dem Host in `ps` sichtbar. Sauber wäre
`nmcli --ask` mit Eingabe über stdin.

### [ ] Logout invalidiert serverseitig nichts

Der JWT bleibt 24 h gültig, auch nach Passwortwechsel – das Signaturgeheimnis
ändert sich ja nicht. Bräuchte eine Token-Version bzw. ein `iat`-Cutoff in
`auth_settings.json`.

### [ ] Upload ohne Größen- und Typbegrenzung

`upload_track` nimmt Dateien beliebiger Größe und Endung an. Bewusst nicht
angefasst: ein zu knappes Limit bricht legitime Hörbuch-Uploads, die Grenze ist
eine Produktentscheidung.

---

## 6. Datenhaltung & Robustheit

### [x] Nicht-atomarer State-Write im Audio-Service

`state_manager.save()` öffnete die Zieldatei mit `"w"` – Stecker ziehen mitten
im Schreiben hinterließ eine abgeschnittene JSON. Das Laden fing den
`JSONDecodeError` ab und fiel auf Defaults zurück, es ging also „nur" die
Fortsetzungsposition verloren. Für ein Gerät, dessen erklärtes Ziel „jederzeit
vom Strom ziehen" ist, trotzdem der falsche Weg.

**Umgesetzt:** Schreiben in eine temporäre Datei im selben Verzeichnis,
`fsync`, dann `os.replace()` – atomar. Bei Fehlern wird die Temp-Datei
aufgeräumt.

Nebenbefund: Die Sorge in `Optimierungen.md`, der State werde sekündlich
geschrieben, trifft nicht mehr zu. Geschrieben wird bei Pause, Stop,
Lautstärkeänderung und Shutdown. Das heißt allerdings weiterhin: **jeder
Lautstärke-Tastendruck ist ein SD-Write.** Ein Debounce von wenigen Sekunden auf
den Lautstärkepfad wäre die naheliegende Ergänzung – offen.

### [x] `PRAGMA`-Listener hing an der globalen `Engine`-Klasse

`@event.listens_for(Engine, "connect")` stand *innerhalb* von `connect()`: der
Listener wurde global registriert und bei jedem erneuten `connect()` ein
weiteres Mal.

**Umgesetzt:** Registrierung an der Instanz (`self.engine`).

### [x] Spalten-Migrationen verschluckten jeden Fehler

`_apply_column_migrations()` fing alle Exceptions mit `except Exception: pass` –
eine gesperrte DB war nicht von „Spalte existiert schon" zu unterscheiden.
Zusätzlich stand mitten im Schleifenrumpf ein `__import__("sqlalchemy").text(...)`.

**Umgesetzt:** Normaler Import, `rollback()` nach Fehlern, „duplicate column"
still übersprungen, alles andere als Warnung geloggt.

### [ ] Zwei konkurrierende Migrationsmechanismen

Es gibt Alembic mit vier Versionen und `run_migrations()`, gleichzeitig macht
`connect()` ein `Base.metadata.create_all()` plus die handgeschriebene
ALTER-TABLE-Liste. Beides läuft bei jedem Start. Das aufzulösen – Alembic als
alleinige Quelle, `create_all` und die Handliste raus – ist ein Eingriff, der
eine bestehende Datenbank betrifft und ein Backup-und-Restore-Testlauf
verdient. Bewusst offen gelassen.

---

## 7. Tests

Vor diesem Branch existierte für ~22.500 Zeilen Service-Code kein einziges
Testverzeichnis (nur `test_cold_start.py` und `scripts/test_display.py` im
Repo-Root).

### [x] Erste Regressionstests

- `services/backend-service/tests/test_temperature_logger.py` – nagelt beide
  Bugs aus Abschnitt 1 fest: keine Busy-Loop bei nicht erreichbarem
  Host-Helper, keine Busy-Loop bei fehlendem Temperaturfeld, Alarm wird bei
  Überhitzung gesendet und bei Abkühlung wieder aufgehoben, ein fehlgeschlagenes
  Sample tötet den Task nicht.
- `services/audio-service/tests/test_state_manager.py` – atomarer Write, keine
  Temp-Reste, Round-Trip, Fallback bei korrupter Datei.
- `services/audio-service/tests/test_pulse_detector.py` – Parsing sowie
  Cache-Verhalten inklusive der Simulation der 2-Sekunden-Status-Schleife
  (30 Aufrufe → ein `pactl`).

Ausführen (die Service-Abhängigkeiten liegen in den Images, nicht im `.venv`):

```bash
./scripts/run-tests.sh
```

### [ ] Keine Abdeckung für die übrigen Services

button, display, led, rfid und media-downloader haben weiterhin keine Tests.
Die State-Machine des Button-Service (`core/state_machine.py`) und die
LED-Muster wären die nächsten lohnenden Kandidaten – reine Logik, ohne
Hardware testbar.

---

## 8. Verifikation dieses Branches

Was tatsächlich geprüft wurde, und wie:

| Prüfung | Ergebnis |
|---|---|
| `ruff` gegen HEAD-Baseline (backend / audio / host-helper) | 48→45, 50→50, 180→174 – keine neuen Meldungen |
| Import aller 56 Backend-Module im echten Image | OK |
| Import aller Audio- und Host-Helper-Module im echten Image | OK |
| OpenAPI-Schema alt vs. neu (139 Operationen) | byte-identisch |
| Route-Pfade und -Signaturen in `routes_host.py` (45 Routen) | unverändert |
| `docker compose config` mit frischer `.env` aus `.env.example` | schlägt ohne Key fehl, klappt mit generiertem Key |
| Regressionstests | 20 Tests, alle grün |
| Temperatur-Tests gegen den **alten** Code | hängen (Busy-Loop) – der Test greift also wirklich |
| Busy-Loop-Messung alt vs. neu | 356.804 → 48 Abfragen pro 0,5 s |

Die vorbestehenden ~540 `ruff`-Meldungen (überwiegend `E501` Zeilenlänge und
`B904` `raise ... from`) wurden bewusst nicht angefasst – das wäre Rauschen über
dem eigentlichen Diff.
