# Dienste-Landkarte

Wer macht was - und wo der Fehler wirklich sitzt, wenn ein Symptom woanders
sichtbar wird.

| Dienst | Container | Aufgabe | Typische Fehlerbilder |
|---|---|---|---|
| backend | minabox-backend | REST-API, Datenbank, MQTT-Verteiler, WebSocket | 5xx in `client/failed_requests.json`, DB-Fehler, Migrationsprobleme |
| webui | minabox-webui | Oberflaeche (statisch ausgeliefert) | leere Seite, JS-Fehler in `client/console_errors.json` |
| audio | minabox-audio | Wiedergabe via VLC/PipeWire | kein Ton, Aussetzer, falsches Ausgabegeraet |
| rfid | minabox-rfid | Kartenleser | Karte nicht erkannt, Doppel-Scans |
| button | minabox-button | GPIO-Tasten | Knopf ohne Wirkung, Dauerausloesung (Pin-Konflikt) |
| led | minabox-led | LED-Ansteuerung | LED dunkel oder falsche Farbe, Pin-Konflikt mit Tasten |
| display | minabox-display | Anzeige | Bild friert ein, Dienst fehlt |
| mqtt | minabox-mqtt | Nachrichtenbus zwischen allen Diensten | **wenn der weg ist, reagiert scheinbar gar nichts mehr** |
| host-helper | minabox-host-helper | Host-Zugriff: Logs, Netzwerk, Updates, USB | Netzwerk-/Log-Bereiche fehlen im Export |
| media-downloader | minabox-media-downloader | Downloads (Podcasts, Streams) | fehlende Dateien, volle Platte |

## Faustregeln

- **Alles reagiert nicht mehr** → zuerst MQTT in `services/health.json` pruefen.
  Tasten, RFID und Wiedergabe laufen ueber den Bus; ist er weg, wirkt jeder
  Dienst einzeln gesund und trotzdem passiert nichts.
- **Symptom im Frontend** → erst `client/console_errors.json`, dann
  `services/backend/logs.txt`. Ein leerer Bildschirm ist oft ein JS-Fehler und
  kein Backend-Problem.
- **Hardware-Symptom (Ton, Knopf, LED)** → erst `system/boot_config.txt`
  (dtoverlay) und die Dienstkonfiguration, dann der Dienst selbst. Ein fehlendes
  Overlay laesst den Dienst sauber starten und trotzdem nichts tun.
- **Mehrere Dienste gleichzeitig auffaellig** → Systemursache verdaechtigen:
  Unterspannung, volle Platte, read-only Dateisystem, OOM.
