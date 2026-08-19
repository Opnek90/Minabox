# Export-Schema

Vertrag zwischen Export (Backend) und Analyse (dieser Skill). Der Contract-Test
`services/backend-service/tests/test_debug_export_contract.py` prueft ein echt
erzeugtes Paket gegen dieses Dokument - wer einen Collector hinzufuegt und die
Doku vergisst, bekommt einen roten Test.

## schema_version 1

### manifest.json

| Feld | Bedeutung |
|---|---|
| `schema_version` | Version dieses Vertrags (aktuell 1) |
| `created_at` | Erstellzeit UTC |
| `device_id` | Geraetekennung aus der Konfiguration |
| `export_id` | Erste 16 Zeichen des Export-Salts (identifiziert das Paket, nicht das Geraet) |
| `redaction_level` | derzeit immer `standard` |
| `options` | die Auswahl des Nutzers, unveraendert |
| `versions` | Backend-Version, Schema, Geraet, Erzeugungszeit |
| `uncompressed_bytes` | Summe der geschriebenen Dateien |
| `collectors[]` | `{name, status, ms, error?}` je Collector |
| `files[]` | `{path, bytes}` je geschriebener Datei |
| `truncations[]` | gekuerzte oder ausgelassene Dateien samt Grund |
| `secret_tripwire` | `{checked: [...], blocked: [...]}` |

`status` eines Collectors: `ok`, `empty`, `failed`, `skipped_by_user`.

### Collector-Namen (Allowlist)

`client.context`, `database.copy`, `db.meta`, `history.usage`,
`logs.host_diagnostics`, `logs.services`, `logs.syslog`, `media.summary`,
`network.status`, `services.health`, `settings.environment`, `settings.general`,
`system.apt_history`, `system.boot_config`, `system.docker`, `system.hardware`,
`system.kernel_modules`, `system.os`, `system.packages`, `system.power`,
`system.storage`, `system.usb`, `runtime.buffers`

### Dateien

Vorhandene Dateien haengen von der Auswahl ab; fehlt eine, sagt das Manifest
warum.

```
manifest.json                      Vertrag, immer vorhanden
README.txt                         Datenschutzerklaerung fuer den Nutzer, immer vorhanden

system/hardware.json               Modell, Revision, CPU, RAM, SD-Karte (Seriennummern gehasht)
system/power.json                  Unterspannung (rpi_volt-hwmon), Temperatur, Takt
system/storage.json                usage[], mounts[] (aus /proc/1/mounts), readonly_mounts[]
system/os.json                     Distribution, Image-Datum, Kernel, Architektur, Uptime
system/usb_devices.json            USB-Inventar aus sysfs
system/kernel_modules.json         geladene Module
system/docker.json                 Docker-Version, Storage-Driver, Speicherverbrauch
system/packages.txt                vollstaendige Paketliste ("name version" je Zeile)
system/packages_relevant.json      kuratierter Auszug
system/apt_history.txt             letzte apt-Aktivitaet
system/boot_config.txt             /boot/firmware/config.txt (roh)
system/boot_config_active.json     dieselbe Datei ohne Kommentare
system/boot_cmdline.txt            /boot/firmware/cmdline.txt
system/systemd.json                fehlgeschlagene Units, journalctl -p3, timedatectl
system/network.json                Netzwerkstatus (SSID/MAC pseudonymisiert)
system/host_status.json            Host-Eckdaten vom Host-Helper
system/time_status.json            Zeitzone und NTP-Status

services/health.json               je Dienst: Erreichbarkeit, Container-Metadaten
services/<dienst>/logs.txt         Container-Logs (Tail)
services/logs_missing.json         Dienste ohne abrufbare Logs

logs/syslog-kernel.txt             Kernel-Log des Hosts
logs/syslog-docker.txt             Docker-Unit-Log
logs/kernel_findings.json          Zaehler fuer Unterspannungs-/Drosselungszeilen
logs/syslog_unavailable.json       nur wenn der Host-Helper fehlt
```

### Kopfzeilen gekuerzter Logs

Jede gefilterte oder gekuerzte Log-Datei beginnt mit einem Kommentarblock
(`#`-Zeilen, abgeschlossen durch eine Zeile `#`):

```
# Quelle: journalctl kernel
# Abgedeckter Zeitraum: 2026-08-18T09:00:01+0200 bis 2026-08-18T13:45:01+0200
# Zeilen: 84 von 4210 behalten, 4126 verworfen (Rauschen: 4100, Kuerzung: 26)
# Immer behalten: 8 Zeile(n) zu Unterspannung, Drosselung, mmc/SD, E/A-Fehler, OOM oder Boot
# Hinweis: Diese Datei ist gefiltert und gekuerzt. Fehlt hier ein Hinweis, ist
# das kein Beleg dafuer, dass es das Problem nicht gab.
```

Beim Kernel-Log wird Docker-veth-/Bridge-Rauschen verworfen, *bevor* gekuerzt
wird; Zeilen zu Unterspannung, Drosselung, mmc/SD, E/A-Fehlern, OOM und Boot
werden immer behalten. Der Zaehler in `logs/kernel_findings.json` zaehlt auf dem
ungefilterten Strom, ist also unabhaengig vom Zeilenbudget.

```

config/general_settings.json       Nutzereinstellungen
config/auth_settings.shape.json    nur Struktur - nie der Hash
config/env.sanitized.json          Variablennamen und ob gesetzt - nie Werte
config/services/<dienst>/*.json    Dienstkonfigurationen

db/schema.sql                      Schema aus sqlite_master
db/table_counts.json               Zeilenzahlen je Tabelle
db/alembic_version.txt             Migrationsstand
db/integrity_check.txt             PRAGMA quick_check
db/meta.json                       Groesse, Seitengroesse, Journal-Modus
db/recent_scans.json               nur bei history: letzte Scans, Karten-IDs gehasht
db/playback_summary.json           nur bei history: Aggregat der letzten 14 Tage
db/minabox.db.sql                  nur bei include_db: vollstaendiger SQL-Dump

media/library_summary.json         Anzahlen, Formate, Quelltypen
media/missing_files.json           Eintraege ohne vorhandene Datei
media/audio_state.json             Zustand des Audio-Dienstes

runtime/errors_recent.json         letzte Warnungen und Fehler des Backends (Ringpuffer)
runtime/mqtt_recent.json           letzte MQTT-Nachrichten, in = empfangen, out = gesendet
runtime/temperature_recent.json    nur bei history: letzte Temperaturmessungen

client/browser.json                Browser, Viewport, Sprache, PWA-Modus
client/console_errors.json         Ringpuffer der Frontend-Fehler
client/failed_requests.json        Ringpuffer fehlgeschlagener API-Aufrufe
```

### Was garantiert NICHT enthalten ist

Audio- und Cover-Dateien, `HOST_HELPER_API_KEY`, `WEB_AUTH_SECRET`, der
Passwort-Hash, WLAN-PSKs, Werte von Umgebungsvariablen. Seriennummern (Pi, SD),
SSIDs, MACs und Karten-UIDs erscheinen ausschliesslich als `id:<12 Hex>` -
vergleichbar innerhalb eines Pakets, nicht ueber Pakete hinweg.
