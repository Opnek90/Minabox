# Bekannte Faelle

Jeder geloeste Supportfall wird hier ein Eintrag. Format: **Signatur** (woran man
es im Export erkennt) → **Ursache** → **Fix**. Laesst sich die Signatur
mechanisch pruefen, gehoert zusaetzlich eine Regel in `scripts/triage.py`.

Die Liste startet mit den Faellen, die aus dem Aufbau des Systems folgen. Sie
waechst mit der Praxis - das ist der Teil, der sich verzinst.

---

## Unterspannung des Raspberry Pi

**Signatur:** `system/power.json` mit `undervoltage_now: true`, oder Treffer auf
`Under-voltage detected` in `logs/syslog-kernel.txt`
(`logs/kernel_findings.json` zaehlt sie).
**Ursache:** Netzteil oder Kabel liefern zu wenig Strom. Haeufig ein
Handy-Ladegeraet, ein langes duennes Kabel oder ein passiver USB-Hub mit
Festplatte.
**Fix:** Original-Netzteil (Pi 4: 5 V/3 A, Pi 5: 5 V/5 A), kurzes Kabel,
angetriebener Hub. Vor jeder weiteren Analyse klaeren - Unterspannung erzeugt
Folgefehler in allen Diensten und verfaelscht jede Messung.
**Triage-Regel:** `undervoltage`, `undervoltage_history`

## Read-only gewordenes Wurzeldateisystem

**Signatur:** `system/storage.json` mit nicht-leerem `readonly_mounts`, dazu
I/O-Fehler in `logs/syslog-kernel.txt`.
**Ursache:** Die SD-Karte meldet Schreibfehler, der Kernel schaltet auf
read-only. Anwendungen melden dann Rechte- oder Datenbankfehler, ohne den Grund
zu nennen.
**Fix:** Karte ersetzen, vorher Backup ziehen.
**Triage-Regel:** `readonly_root`, `sd_io_errors`

## Kein Ton trotz laufendem Audio-Dienst

**Signatur:** `services/health.json` zeigt audio online, `system/boot_config.txt`
enthaelt kein bzw. ein falsches `dtoverlay` fuer den verbauten Audio-HAT.
**Ursache:** Ohne passendes Overlay existiert die Soundkarte nicht; der Dienst
startet trotzdem sauber.
**Fix:** Passendes `dtoverlay` in `/boot/firmware/config.txt` eintragen und neu
starten.

## Doppelt belegter GPIO-Pin

**Signatur:** derselbe Pin in `config/services/button/buttons.json` und
`config/services/led/leds.json`.
**Ursache:** Zwei Dienste beanspruchen denselben Pin; einer scheitert beim Start
oder verhält sich zufällig.
**Fix:** Belegung in einer der Konfigurationen aendern.
**Triage-Regel:** `gpio_conflict`

## Titel spielen nicht nach Umzug der Medien

**Signatur:** `media/missing_files.json` mit `count > 0`.
**Ursache:** Die Datenbank verweist auf Pfade, die es nicht mehr gibt - Medien
verschoben, USB-Speicher nicht eingehaengt, Dateien geloescht.
**Fix:** Medienpfad korrigieren oder Eintraege neu einlesen.
**Triage-Regel:** `missing_media`

## Fehler seit dem letzten Update

**Signatur:** juengster `Start-Date` in `system/apt_history.txt` faellt mit dem
Fehlerbeginn zusammen; oder `db/alembic_version.txt` passt nicht zum Code.
**Ursache:** Paket-Update auf dem Host oder halb durchgelaufenes Minabox-Update.
**Fix:** Betroffenes Paket pruefen; bei Migrationsstand-Abweichung Migration
nachziehen.
**Triage-Regel:** `recent_apt_change`, `alembic_mismatch`

## Scheinbar tote Box bei gesunden Diensten

**Signatur:** `services/health.json` zeigt mqtt offline, alle anderen online.
**Ursache:** Ohne Nachrichtenbus erreichen Tasten- und RFID-Ereignisse das
Backend nicht. Jeder Dienst wirkt einzeln gesund.
**Fix:** MQTT-Container und dessen Logs pruefen.
**Triage-Regel:** `services_offline`
