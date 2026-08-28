# Dienstuebergreifende offene Punkte

Befunde, die beim Review eines Dienstes aufgetaucht sind, aber **andere oder
alle** Dienste betreffen. Sie stehen hier statt im Review des einzelnen
Dienstes, weil sie dort nur zufaellig gefunden wurden und in einem eigenen
Branch abgearbeitet gehoeren.

Aufgenommen am 2026-08-25 aus dem [LED-Review](led/GoLive-Review.md), dem
[Display-Review](display/GoLive-Review.md) und einer Stoerung im Betrieb.
1.6 und 1.7 kamen am 2026-08-26 aus einer zweiten Ton-Stoerung dazu, 1.8 aus
dem ersten echten Test von 1.7 auf einer Box, am selben Tag.
Ergaenzung zu [ServiceReview.md](../ServiceReview.md), das die neun Dienste
insgesamt behandelt.

Legende: `[ ]` offen · `[x]` erledigt · **[H]** hoch · **[M]** mittel ·
**[N]** niedrig

---

## 1. Robustheit & Betrieb

### [x] [M] 1.1 Vier Dienste veroeffentlichen ungeschuetzte Ports auf allen Interfaces

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

**Erledigt** am 2026-08-26. `127.0.0.1:` vor alle vier, mit der Begruendung
als Kommentar am jeweiligen Dienst. Die vier Architektur-Dokumente nennen den
Loopback jetzt ebenfalls. Vorher geprueft: nur das Backend greift zu.

### [x] [M] 1.2 `degraded` aus `/health` erreicht die WebUI nie

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

**Erledigt** am 2026-08-26. Beide Pfade in `routes_system.py` uebernehmen den
gemeldeten Status. `state` hat einen vierten Wert `degraded`, in der WebUI
bernsteinfarben; `error` sticht ihn, weil ein ungesunder Container die
schlechtere Nachricht ist. Abgefragt werden nur Eintraege, die online sind,
und alle zusammen - die Runde kostet ein `HEALTH_TIMEOUT`, nicht eines je
Dienst.

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

### [x] [H] 1.4 Der Python-Healthcheck kostet 6 % eines Kerns je Dienst

Aufgenommen am 2026-08-25 aus dem
[Display-Review, Abschnitt 5](display/GoLive-Review.md).

Das LED- und das Button-Review haben `curl -f http://…/health` ersetzt durch

```
python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(…).status==200 else 1)"
```

um 14,5 MB apt zu sparen. Gemessen kostet eine Pruefung in diesen Containern:

| Pruefung | CPU je Durchlauf |
| --- | --- |
| `curl -sf …/health` | **0,052 s** |
| `python -c "import urllib.request…"` | **2,13 s** |

Bei `interval: 30s` sind das **7 % eines Kerns, dauerhaft**. Ueber 120 s aus der
cgroup-Abrechnung, aufgeteilt nach Dienstprozess und Rest des Containers:

| Dienst | Container gesamt | davon Dienst | davon Healthcheck |
| --- | --- | --- | --- |
| `display` (curl) | 2,26 % | 1,47 % | **0,80 %** |
| `button` (Python) | 9,81 % | 3,74 % | **6,06 %** |

Der Healthcheck ist damit in `button` und `led` der groesste einzelne
Verbraucher – groesser als der Dienst selbst.

**Ursache:** das offizielle `python:3.13-slim` liefert **keinen kompilierten
Bytecode fuer die Standardbibliothek** aus:

```
docker exec minabox-display sh -c \
  'find /usr/local/lib/python3.13 -name "*.pyc" -not -path "*/site-packages/*" | wc -l'
→ 0
```

Und die Container laufen als Nicht-Root gegen root-eigene Verzeichnisse, koennen
also auch kein `__pycache__` anlegen. Jede Pruefung uebersetzt `ssl`, `email`,
`http.client` und `urllib.parse` neu. `python -X importtime` weist 1,90 s der
2,13 s allein dem `urllib.request`-Importbaum zu.

Gegenprobe in einem Wegwerf-Container: mit vorkompilierter stdlib faellt
derselbe Import von 2,13 s auf **0,47 s** – Faktor 4,5 – zum Preis von 13 MB
(stdlib waechst von 104 MB auf 117 MB).

**Fix, eine der drei Varianten:**

- `curl` zurueckholen (+15 MB je Image, −6 % eines Kerns),
- `RUN python -m compileall -q /usr/local/lib/python3.13` in die Runtime-Stage
  (+13 MB, −5 % eines Kerns) – das nimmt denselben Uebersetzungslauf auch aus
  dem Dienststart heraus,
- die Pruefung auf einen rohen Socket umstellen, sodass nur `socket` importiert
  wird (gemessen 0,86 s – besser, aber immer noch Faktor 16 gegenueber `curl`).

`interval` auf 60 s zu setzen halbiert es unabhaengig von der Wahl.

**Betrifft:** `button` und `led`. Der Display-Service behaelt `curl` bewusst;
die Begruendung steht in [seinem Review](display/GoLive-Review.md#5-runtime-cost--and-a-warning-about-the-health-check).

**Risiko:** keins bei `compileall`. Beim Zurueckholen von `curl` ist es eine
bewusste Ruecknahme zweier Review-Entscheidungen – deshalb hier und nicht
stillschweigend im naechsten Branch.

**Erledigt** am 2026-08-26. `compileall` in der Runtime-Stage von `button` und
`led`, vor `USER`. Im lokal gebauten Image nachgemessen: 633 `.pyc` in der
stdlib, der Import faellt von 2,05 s auf 0,53 s, das Image waechst von 229 MB
auf 256 MB. `interval` bleibt bei 30 s - die schnellere Erkennung eines
haengenden Dienstes ist die 1,5 % eines Kerns wert, die jetzt noch anfallen.

**Revidiert** am 2026-08-28 (Issue #141). Statt zwei Healthcheck-Strategien im
Baum gilt jetzt eine: `curl -f` in allen neun Diensten. `button` und `led`
holen `curl` zurueck und lassen den `compileall`-Schritt fallen — lokal
nachgemessen sind die Images damit **248 MB** gegen 256 MB mit `compileall`,
und der Healthcheck kostet 0,8 % statt 1,5 % eines Kerns. Die Regel steht jetzt
in [Entwicklungs-Workflow.md](../Entwicklungs-Workflow.md), Abschnitt
„Container-Healthcheck".

### [x] [H] 1.5 Der Audio-Dienst meldet `healthy`, waehrend gar kein Ton moeglich ist

Aufgefallen am 2026-08-25 an einer echten Stoerung, nicht beim Lesen von Code.

Nach einem Neustart hielt der PN532 den I2C-Bus fest. Der Codec-Treiber probiert
genau einmal beim Booten und gab auf:

```
wm8960 1-001a: Failed to issue reset
wm8960 1-001a: probe with driver wm8960 failed with error -5
```

Die Soundkarte existierte danach nicht mehr - `aplay -l` zeigte nur noch HDMI und
die Kopfhoererbuchse. Aus der Box kam kein Ton. In derselben Zeit meldete
`GET /health` des Audio-Dienstes:

```json
{"status": "healthy", "service": "audio", "mqtt_connected": true,
 "vlc_initialized": true}
```

Und `docker ps` zeigte alle zehn Container gruen.

Der Endpunkt kennt nur zwei Bedingungen: Broker verbunden, VLC hochgefahren.
Beides war wahr. Ob das konfigurierte Ausgabegeraet ueberhaupt existiert, wird
nicht geprueft - dabei steht es in `audio.json` (`enabled_output_devices`) und
laesst sich mit einer Abfrage der vorhandenen Senken vergleichen.

Das ist derselbe Fehler, der fuer [LED](led/GoLive-Review.md) und
[Display](display/GoLive-Review.md) bereits behoben wurde - konfiguriert ist
nicht dasselbe wie benutzbar - nur beim Dienst, bei dem er am meisten weh tut.
Ein dunkles Display ist ein Schoenheitsfehler; eine stumme Box ist kaputt.

**Fix:** `/health` um das Ausgabegeraet erweitern und `degraded` melden, wenn die
konfigurierte Senke fehlt. Der Dienst fragt die Geraeteliste ohnehin schon ab -
`get_audio_devices()` liefert sie, und `_publish_status` wertet sie fuer
`multiple_output_devices` bereits aus.

**Zusammenhang:** haengt an 1.2. Solange `degraded` die WebUI nicht erreicht,
bleibt auch ein korrekter Status unsichtbar. Beide zusammen ergeben erst den
Nutzen - deshalb am besten in einem Zug.

**Risiko:** gering. Nur ein zusaetzliches Feld und eine Bedingung; der
Container-Healthcheck fragt weiterhin nur, ob der Endpunkt antwortet.

**Erledigt** am 2026-08-26. `/health` fragt jetzt zusaetzlich, ob die
konfigurierte Senke ueberhaupt da ist, und meldet sonst `degraded`. Eine
*fehlgeschlagene* Abfrage gilt bewusst nicht als fehlendes Geraet. Zusammen
mit 1.2 ist das in der WebUI sichtbar.

### [x] [H] 1.6 Ein gemerkter Mute in PipeWire ueberlebt jeden Neustart

Aufgefallen am 2026-08-26 an einer echten Stoerung, wie 1.5 nicht beim Lesen von
Code. Die Box gab keinen Ton. Gleichzeitig erzeugte

```bash
speaker-test -D plughw:3,0 -c2 -t wav -l1
```

einwandfrei Ton - die Lautsprecher, der Codec und der ALSA-Pfad waren also in
Ordnung. `speaker-test` spricht ALSA direkt an und geht an PulseAudio/PipeWire
vorbei; der Audio-Dienst spielt ueber libVLC → PulseAudio → PipeWire.

WirePlumber merkt sich Lautstaerke und Stummschaltung **pro Medienrolle**,
dauerhaft in `~/.local/state/wireplumber/stream-properties`. Dort stand:

```
Output/Audio:media.role:Movie={"mute":true, "channelVolumes":[0.027001]}
```

Stumm - und zusaetzlich auf 2,7 % Lautstaerke. Jeder neue VLC-Stream bekam das
beim Oeffnen des Ausgangs sofort aufgedrueckt:

```
Sink Input #194   Mute: yes
    media.role = "video"
    module-stream-restore.id = "sink-input-by-media-role:video"
```

Nachweisbar auch an libVLC selbst: eine frisch erzeugte Instanz meldet vor
`play()` noch `mute=0`, unmittelbar nach dem Oeffnen des Ausgangs `mute=1` -
ohne dass irgendjemand stummgeschaltet haette.

**Ursache:** eine Zustandsverdopplung. `_handle_mute_toggle()`
(`core/service.py`) schaltet ueber `audio_set_mute()` stumm, PipeWire schreibt
das in seine Datenbank. `self._muted` im Dienst ist nach einem Neustart wieder
`False` - der Dienst haelt sich fuer entstummt, PipeWire schaltet aber weiter
stumm. Kein Neustart des Containers und kein Neustart der Box raeumt das weg,
daher kam die Stoerung wieder.

**Nebenbefund:** `PULSE_PROP_media.role=music` in `docker-compose.yml` ist
wirkungslos. VLC setzt seine eigene Rolle und nimmt dafuer standardmaessig
`video`, weshalb der Zustand unter `Movie` landete statt unter `Music`.

**Zweiter Nebenbefund:** der bestehende `POST /api/v1/test-tone` kann diesen
Fehler gar nicht zeigen. Er spielt ueber `paplay`, und das laeuft unter
`application.name:paplay` - eine andere Rolle, mit einem eigenen, gesunden
Eintrag. Der Testton war hoerbar, waehrend die Musik stumm blieb.

**Fix, drei Teile:**

1. `--role=music` in `_build_vlc_args()` (`infrastructure/vlc_backend.py`).
   Dann landet der Stream in der Rolle, die der Dienst ohnehin meint.
2. Nach jedem `play()` den Mute-Zustand einmal explizit aus `self._muted`
   setzen, statt darauf zu vertrauen, dass ein frischer Player unstumm ist.
   Vor `play()` genuegt nicht - der gemerkte Zustand wird erst beim Oeffnen des
   Ausgangs angewendet.
3. Den Testton ueber denselben libVLC-Pfad schicken wie die Musik, sonst prueft
   er weiterhin einen Weg, den im Betrieb niemand benutzt.

**Sofortmassnahme, falls es erneut auftritt:** waehrend ein VLC-Stream laeuft
den Sink-Input entstummen - WirePlumber schreibt den korrigierten Wert dann von
selbst zurueck:

```bash
XDG_RUNTIME_DIR=/run/user/1000 pactl set-sink-input-mute <index> 0
```

**Risiko:** gering. Teil 1 und 2 sind wenige Zeilen im Backend des Dienstes.
Teil 3 beruehrt einen Endpunkt, den nur die WebUI aufruft.

**Erledigt** am 2026-08-26. Alle drei Teile: `--role=music`, der Mute wird nach
`play()` erzwungen, und der Testton laeuft ueber libVLC - auf einer eigenen
Wegwerf-Instanz, damit der Assistent weiter pruefen kann, waehrend Musik
laeuft. Der Kommentar an `PULSE_PROP_media.role` in `docker-compose.yml` sagt
jetzt, dass die Variable nur den `pacat`-Prewarm erreicht.

### [x] [H] 1.7 Der Nutzer hat keinen Weg, eine stumme Box selbst zu reparieren

Nichts ist aergerlicher als eine Box, die ploetzlich keinen Ton mehr gibt. Die
bisherigen Stoerungen dieser Art (1.5, 1.6) waren beide nur mit `aplay -l`,
`pactl` und einem Blick in die WirePlumber-Datenbank zu finden. Das kann niemand
leisten, der die Box benutzt statt sie zu entwickeln - und genau die Person
steht davor.

Vorschlag: ein Knopf **„Ton-Problem beheben"** in der WebUI unter
*Wartung*, neben dem Debug-Export. Ein Klick, danach fuehrt die Box durch die
Pruefkette und behebt, was sie selbst beheben kann.

**Pruefkette,** von unten nach oben, jeder Schritt mit einer Behebung, die ohne
Rueckfrage sicher ist:

| # | Pruefung | Erkennbar an | Automatische Behebung |
|---|---|---|---|
| 1 | Soundkarte vorhanden? | Karte zum konfigurierten Sink fehlt in `pactl list cards` | keine - Neustart der Box noetig, siehe 1.5 |
| 2 | Konfigurierter Sink vorhanden? | `output_device_name` fehlt in `pactl list sinks` | auf den ersten verfuegbaren Sink zurueckfallen |
| 3 | Sink stumm oder sehr leise? | `Mute: yes`, Volume unter ca. 20 % | entstummen, auf einen normalen Pegel setzen |
| 4 | Gemerkter Rollen-Zustand stumm? | Testton-Stream startet mit `Mute: yes` | Sink-Input entstummen, WirePlumber speichert es |
| 5 | Dienst selbst stummgeschaltet? | `self._muted` | entstummen |
| 6 | Dienst-Lautstaerke unter `min_volume`? | `get_volume()` | auf `default_volume` |
| 7 | ALSA-Mixer auf 0? | `amixer -c <karte> sget Speaker` | auf einen sinnvollen Wert setzen |

Schritt 4 geht nur, **waehrend** ein Stream laeuft - der Testton ist genau
dieser Stream, und er muss ueber libVLC laufen, nicht ueber `paplay`
(siehe 1.6).

**Der DAU-taugliche Teil ist der Abschluss:** die Box spielt den Testton und
fragt in grossen Worten *„Hoerst du jetzt etwas?"* mit **Ja** und **Nein**.

- **Ja** → „Das Problem ist behoben." Dazu in einem Satz, was es war.
- **Nein** → naechste Eskalationsstufe: Audio-Dienst neu starten, erneut
  fragen. Danach die zwei Dinge, die nur ein Mensch pruefen kann - Kabel und
  Stromversorgung der Lautsprecher - und als letztes das Angebot, die Box neu
  zu starten.

Was der Nutzer nie zu sehen bekommt: `pactl`, Rollennamen, Sink-Indizes. Die
technischen Details gehoeren in den Debug-Export, nicht in den Dialog.

**Wo das hingehoert:**

- `POST /api/v1/audio/troubleshoot` im Audio-Dienst. Der Dienst spricht ohnehin
  ueber den gemounteten Socket mit PulseAudio und kann die Schritte 2 bis 6
  allein erledigen.
- Schritt 1 und 7 brauchen den Host: `/proc/asound/cards` und `amixer` sind im
  Audio-Container nicht erreichbar. Der `host-helper` hat `/:/host:rw` und
  laeuft als root - dort als Erweiterung von `/diagnostics/host`.
- Backend-Proxy wie bei den uebrigen Wartungsfunktionen.
- WebUI: in `SystemMaintenanceSection.tsx`, mit Uebersetzungen in
  `de/admin.json` und `en/admin.json`.

**Zusammenhang:** 1.5 liefert die Erkennung („die Senke fehlt"), 1.6 den
haeufigsten Einzelfall, 1.2 die Anzeige. Dieser Punkt macht daraus etwas, das
der Nutzer selbst ausloesen kann. Sinnvoll erst, wenn 1.5 und 1.6 stehen -
sonst prueft der Knopf Zustaende, die der Dienst noch falsch meldet.

**Risiko:** mittel. Ein Knopf, der Zustaende veraendert, muss idempotent sein
und darf nichts anfassen, was nicht nachweislich falsch steht - sonst
ueberschreibt er eine bewusst leise eingestellte Box. Jede Behebung gehoert
protokolliert, damit im Debug-Export nachvollziehbar bleibt, was der Knopf
getan hat.

**Erledigt** am 2026-08-26. Knopf *Ton-Problem beheben* neben dem
Debug-Export, mit Deep-Link `?action=sound-fix`. Die Kette liegt im
Audio-Dienst (Schritte 2-6) und im Host-Helper (1 und 7); das Backend fuegt
beide Haelften zusammen, Host zuerst - ein Mixer auf null muss hochgesetzt
sein, bevor der Testton laeuft. Der Dialog fragt danach *Hoerst du jetzt
etwas?* und eskaliert ueber einen Neustart des Ton-Dienstes zu Kabel, Strom
und zuletzt einem Neustart der Box. Jede Behebung ist idempotent und greift
nur bei Werten, die niemand gemeint haben kann - dafuer gibt es Tests.

### [x] [H] 1.8 Der Testton aus 1.6/1.7 kam trotzdem nicht an

Aufgefallen am 2026-08-26 beim ersten echten Test von 1.7 auf einer Box: der
Knopf lief durch, meldete `tone_played: true`, kein Schritt als `fixed` - und
es kam kein Ton. `speaker-test -D hw:3,0` und `paplay` direkt auf denselben
Sink spielten sofort und sauber; der Fehler lag also wieder zwischen
Audio-Dienst und Lautsprecher, nicht dahinter.

Zwei Ursachen, beide auf der echten Box nachgewiesen:

**Erstens, ein Rueckfall von 1.6:** `~/.local/state/wireplumber/stream-properties`
stand erneut auf stumm - diesmal korrekt unter der Rolle, die 1.6 selbst
eingefuehrt hat:

```
Output/Audio:media.role:Music={"mute":true, "channelVolumes":[0.125000]}
```

Die in 1.6 dokumentierte Sofortmassnahme (`pactl set-sink-input-mute <index> 0`
waehrend der Stream laeuft) wurde direkt am laufenden Sink-Input erprobt und
schreibt sich zuverlaessig in die Datei zurueck, sofern der Sink-Input lange
genug lebt. Genau daran haperte es:

**Zweitens, der eigentliche Fund:** die libVLC-`pulse`-Ausgabe selbst ist auf
dieser Box unzuverlaessig. Mit `--verbose=3` zeigt sie fuer denselben Testton:

```
pulse audio output debug: cannot synchronize start
pulse audio output debug: deferring start (1149098 us)
vlcpulse audio output debug: write index corrupt
main audio output warning: playback way too late (200246): flushing buffers
```

Bei der 1,4 s kurzen `test-tone.wav` aus 1.7 ist die Datei zu Ende dekodiert
(`EOF reached` → `State.Ended`), waehrend die Ausgabe noch mit dem
Verbindungsaufbau kaempft - hoerbarer Ton kommt gar nicht erst zustande. Mit
einer laengeren, selbst erzeugten Testdatei (3,5 s) bestaetigt sich das Muster:
kein einmaliger Anlaufeffekt, sondern wiederkehrende Aussetzer waehrend der
gesamten Wiedergabe (drei von vier Toenen einer Testschleife nur teilweise
hoerbar, ein durchgehender Ton in der Mitte unterbrochen). `paplay` gegen
denselben Sink, dieselbe Rolle, dieselbe Datei spielte in jedem Versuch
einwandfrei durch. Damit war auch der Sink-Input aus dem VLC-Pfad nicht
zuverlaessig lange sichtbar genug, um von der 1.6-Sofortmassnahme erwischt zu
werden - der Rueckfall oben blieb deshalb unbehandelt liegen.

**Fix:** `play_test_tone()` in `infrastructure/vlc_backend.py` spielt nicht
mehr ueber eine Wegwerf-libVLC-Instanz, sondern ueber `paplay`, mit
`--property=media.role=Music` (die von PipeWire tatsaechlich verwendete
Rollen-Bezeichnung, durch Lesen von `stream-properties` auf der Box bestaetigt
- nicht das `--role=music`, das VLC selbst entgegennimmt) und
`--volume=65536`, damit eine leise gemerkte Rollen-Lautstaerke den Test nicht
verfaelscht. Behebt genau den einen Fehlgriff aus 1.6 Teil 3 - "muss ueber
libVLC laufen" war die falsche Schlussfolgerung aus einer richtigen
Beobachtung (paplay unter `application.name:paplay` prueft die falsche Rolle).
Die Rolle explizit zu setzen loest beides: gleiche Rolle wie die Musik, ohne
die kaputte libVLC-Pulse-Ausgabe.

**Nicht geaendert:** `--role=music` in `_build_vlc_args()` fuer den
persistenten Player aus 1.6 bleibt bestehen - nur der Testton wechselt den
Player. Ob dieselbe libVLC-Pulse-Instabilitaet auch laengere,
normale Wiedergabe im Hintergrund staffelweise stoert (unwahrscheinlicher bei
Minuten statt Sekunden, aber nicht ausgeschlossen), ist damit nicht
untersucht.

**Risiko:** gering. Eine Methode in `vlc_backend.py`, keine Aenderung an
`_build_vlc_args()` oder am Reparatur-Ablauf selbst. `pulseaudio-utils` war
bereits Laufzeit-Abhaengigkeit (`pactl`, `pacat`).

**Erledigt** am 2026-08-26, mehrfach live auf einer echten Box bestaetigt -
inklusive Selbstheilung: mit der neuen Testton-Wiedergabe fand und behob die
bestehende Schrittkette aus 1.7 den Rueckfall aus diesem Punkt beim naechsten
Lauf von selbst, ohne den manuellen Eingriff, der zur Diagnose noetig war.

---

## 2. Angrenzendes, das sonst verloren geht

Kein Robustheitsthema, aber beim selben Review aufgefallen.

### [x] [H] 2.1 Die `lg`-Quelle wird unversioniert und ungeprueft gebaut

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

**War beim Nachsehen schon erledigt.** Beide Dockerfiles sind auf den Tag
`v0.2.2` mit SHA256 festgenagelt und pruefen die Summe vor dem Auspacken;
`button` patcht zusaetzlich das Poll-Intervall und laesst den Build lautstark
scheitern, falls ein kuenftiger Release die Zeile umschreibt.

### [x] [M] 2.2 Deutsche Kommentare in vier Dockerfiles

Der Versions-Block am Dateiende ist noch deutsch in:

`button`, `audio`, `media-downloader`, `webui`

`host-helper`, `led` und `display` sind bereits uebersetzt – der Wortlaut kann
von dort uebernommen werden. Reine Textaenderung, kein Risiko, aber sie invalidiert die
letzten Metadaten-Layer und loest damit einen Rebuild aus.

**Erledigt** am 2026-08-26. `audio`, `media-downloader` und `webui` uebersetzt;
beim Backend war nur noch die Abschnittsueberschrift deutsch. `button` war
entgegen der Liste oben bereits erledigt.

### [x] [N] 2.3 Die Version in `pyproject.toml` ist repo-weit veraltet

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

**Erledigt** am 2026-08-26. `setuptools` liest die Version jetzt aus der Datei
`VERSION` des Dienstes - eine Quelle je Dienst, die nicht wieder auseinander
laufen kann. Fuer alle acht Pakete nachgerechnet: die gebauten Metadaten
stimmen mit `VERSION` ueberein. Die Tabelle oben war beim Abarbeiten schon
veraltet, `button` und `led` standen laengst auf 0.2.0.

### [x] [N] 2.4 Die WebUI erklaert `repeat` nicht

Seit der Korrektur zaehlt `repeat` bei allen LED-Patterns **ganze Zyklen** – ein
Blinken ist an *und* wieder aus. Im Admin-Bereich
(`LEDConfigPanel.tsx`) steht dazu nichts; das Feld ist ein nacktes Zahlenfeld
mit `min: 0`.

Dasselbe gilt fuer `0` = unendlich, was man dem Feld ebenfalls nicht ansieht.

**Fix:** `helperText` an den drei Stellen, analog zu `leds.fields.gpio_hint`.

**Erledigt** am 2026-08-26. `helperText` am Feld, in beiden Sprachen: zaehlt
ganze Zyklen, 0 = endlos.

### [x] [N] 2.5 Lokale Builds backen die Config der Box mit ins Image

`services/.dockerignore` schliesst die Laufzeit-Configs nicht aus. In der CI
faellt das nicht auf, weil dort aus einem Git-Checkout gebaut wird und
`config/leds.json` & Co. gitignored sind – das veroeffentlichte Image enthaelt
sie also nicht. `./scripts/build-local.sh` baut dagegen aus dem Arbeitsbaum und
nimmt sie mit.

Aufgefallen beim A/B-Vergleich zweier Images: der lokale Bau startete ohne
Mount, der veroeffentlichte brach mit `Configuration file not found` ab.

Folgenlos im Betrieb – Compose mountet `config/` ohnehin darueber. Aber ein
lokal gebautes Image verhaelt sich damit nicht wie das, was spaeter ausgeliefert
wird, und genau dafuer baut man es.

**Fix:** in `services/.dockerignore` die Laufzeit-Configs ausschliessen, die
`*.example`-Vorlagen behalten. Betrifft `audio`, `button`, `display`, `led`,
`rfid` gleichermassen – deshalb hier und nicht im LED-Review.

**Erledigt** am 2026-08-26. Die vier gitignorierten Laufzeit-Configs stehen in
`services/.dockerignore`. `rfid.json` und `backend.json` bleiben drin: beide
sind eingecheckt und stecken deshalb auch im veroeffentlichten Image.

### [x] [M] 2.6 Button-Service: 10 % CPU im Leerlauf

Gemessen im Vergleich (drei `docker stats`-Durchlaeufe): `button` 9,6–10,5 %,
`led` und `rfid` je rund 3 %. Steht bereits als offener Punkt in
[ServiceReview.md](../ServiceReview.md) und ist hier nur als Querverweis
aufgenommen, damit die Messung nicht verlorengeht.

**Erklaert.** Es ist nicht der Dienst, es ist sein Healthcheck – siehe 1.4. Von
den gemessenen 9,81 % entfallen 6,06 % auf die Pruefung, 3,74 % auf den Dienst.

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
