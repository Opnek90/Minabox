# Troubleshooting

Bekannte Fehlerbilder und wie man sie auseinanderhaelt. Ergaenzt die
Analyse-Anleitung in `.claude/skills/minabox-debug-analyze/` - dort steht, wie
ein Diagnose-Paket gelesen wird, hier steht, was die Befunde bedeuten.

## MQTT-Verlust

**Bild:** Mehrere Dienste (audio, led, rfid, button) melden gleichzeitig
`"event": "service_crashed"` und werden von Docker neu gestartet. Im Log davor
`MqttError: Disconnected during message iteration`, danach beim Neustart
`[Errno 111] Connection refused` und `[Errno -2] Name or service not known`.

**Ursache (behoben):** Bis einschliesslich der Analyse vom 2026-08-18 haben die
Dienste beim Start ausserhalb der ueberwachten Schleife verbunden. War der
Broker weg, gab `connect()` nach fuenf Versuchen auf, der Fehler lief bis in
`main()` durch und beendete den Prozess. Docker startete neu, der Broker war
immer noch weg - eine Schleife, die erst mit dem Broker endete.

**Verhalten heute:** Der gemeinsame Client in
`services/shared-lib/shared_lib/mqtt/base_client.py` verbindet innerhalb der
ueberwachten Schleife und gibt nie auf (Backoff ab 1 s, Deckel 60 s, Jitter).
Der Start haengt nicht mehr am Broker. Beim Wiederverbinden werden
Subscriptions und der zuletzt gemeldete Status neu publiziert.

**Woran man sieht, dass es wirkt:** `/health` des Dienstes meldet waehrend des
Ausfalls `"mqtt_connected": false` und `"status": "degraded"`, der Container
laeuft aber weiter (`docker ps` zeigt keine steigende Restart-Zahl). Im Log
stehen `mqtt_reconnect_scheduled` mit wachsendem `delay_seconds` statt
`service_crashed`.

`[Errno -2]` ist dabei normal und kein eigener Fehler: mit dem
Broker-Container verschwindet auch sein DNS-Name aus dem Docker-Netz.

## Diagnose-Paket: Docker-Daten fehlen

**Bild:** `system/docker.json` enthaelt nur
`{"error": "DockerException: ... PermissionError(13, 'Permission denied')"}`.
Ohne diese Datei fehlen Restart-Counts, OOM-Kills und Container-States, und die
Triage meldet faelschlich "kein Befund".

**Ursache:** Der Backend-Container ist in keiner Gruppe, die
`/var/run/docker.sock` lesen darf. Der Socket gehoert `root:docker` mit Modus
660; die GID der Gruppe `docker` ist hostabhaengig.

**Behebung:** GID auf dem Host ermitteln und in `.env` eintragen:

```bash
getent group docker | cut -d: -f3
```

```
DOCKER_GID=984
```

Danach `docker compose up -d backend`. Am Host wird nichts veraendert, der
Socket bleibt read-only gemountet.

**Gegenprobe:**

```bash
docker compose exec backend python -c "import docker; print(docker.from_env().version()['Version'])"
```

Ein Collector, der nur noch ein Fehlerobjekt liefert, steht im `manifest.json`
seit dem Fix auf `failed` statt `ok` - der Status ist also verlaesslich.

## Diagnose-Paket: Kernel-Log wirkt leer

`logs/syslog-kernel.txt` ist gefiltert: Docker-veth- und Bridge-Zeilen werden
verworfen, *bevor* gekuerzt wird, damit Boot-, Unterspannungs- und mmc-Zeilen
nicht aus dem Fenster fallen. Die Kopfzeile jeder gekuerzten Log-Datei nennt
den abgedeckten Zeitraum und die Zahl der verworfenen Zeilen.

Steht dort nichts zu Unterspannung, heisst das nicht, dass es keine gab -
sondern nur, dass im abgedeckten Zeitraum nichts protokolliert wurde. Der
Zaehler in `logs/kernel_findings.json` zaehlt auf dem ungefilterten Strom und
ist vom Zeilenbudget unabhaengig.

## Umfeld: wayvnc laeuft in einer Neustartschleife

**Kein Minabox-Dienst.** Auf dem untersuchten Geraet startete
`wayvnc.service` alle 91 Sekunden neu, ueber Stunden hinweg, und hielt die CPU
auf Anschlag. Das faellt in Diagnose-Paketen als hohe Last und als Rauschen im
System-Log auf und kann Minabox-Symptome (traege WebUI, stockende Wiedergabe)
verursachen oder verdecken.

Der Dienst gehoert zum Desktop/Remote-Zugang des Hosts, nicht zu Minabox. Er
wird von hier aus bewusst nicht angefasst. Zum Nachsehen auf dem Host:

```bash
systemctl status wayvnc.service
journalctl -u wayvnc.service -n 100 --no-pager
```

Wird er nicht gebraucht: `sudo systemctl disable --now wayvnc.service`. Das ist
eine Entscheidung ueber den Host, nicht ueber Minabox.

## Box nach WLAN-Wechsel nicht mehr erreichbar

**Bild:** Die Box lief, dann wurde der Router getauscht, das WLAN-Passwort
geaendert oder die Box an einen anderen Ort gebracht. Sie ist unter der
gewohnten Adresse und unter `minabox.local` nicht mehr zu finden.

**Verhalten heute:** Der Connectivity-Watchdog im Host-Helper
(`services/host-helper-service/src/host_helper/netwatch.py`) prueft alle
~20 Sekunden ueber den NetworkManager, ob die Box eine brauchbare Verbindung
hat. Ist sie laenger als 90 Sekunden ohne Verbindung und haengt auch kein
Netzwerkkabel, oeffnet die Box selbst ein WLAN:

- **SSID:** `Minabox-Setup`
- **Passwort:** steht am Display; sonst per Diagnose-Paket im Host-Helper-Log
  (`hotspot_up`) oder auf dem Host mit
  `nmcli -s -g 802-11-wireless-security.psk connection show Minabox-Setup`
- **Adresse:** `http://10.42.0.1`

Ueber die WebUI dort unter *Wartung -> Netzwerk* das neue WLAN eintragen. Sobald
die Box wieder online ist, schaltet der Watchdog den Hotspot von selbst ab
(er probiert die gespeicherten Profile alle paar Minuten neu).

**Woran man sieht, dass es wirkt:** `GET /api/v1/system/network-status` (ohne
Login erreichbar) meldet `"mode": "hotspot"` mit SSID und Passwort. Am OLED
steht der Netz-Screen mit denselben Angaben. Im Host-Helper-Log stehen
`netwatch_offline_grace_started` und `netwatch_starting_fallback_hotspot`.

**Wenn kein Hotspot kommt:** `nmcli` fehlt auf dem Host (NetworkManager nicht
installiert), oder `wlan0` ist im AP-Modus nicht nutzbar. `netwatch_op_failed`
im Log zeigt den `nmcli`-Fehler. Ein per Kabel angeschlossenes, aber nicht
routendes `eth0` unterdrueckt den Hotspot bewusst - das ist ein LAN-/DHCP-
Problem, kein Grund, ein WLAN aufzumachen.
