# RFID-Service – Architecture

## 1. Zweck & Verantwortung

Der RFID-Service ist ausschließlich dafür zuständig, RFID-Leser hardwareseitig anzubinden und Tag-Ereignisse in standardisierte Events zu übersetzen. 
Er kennt selbst keine Playlists oder Audio-Details, sondern liefert nur Tag-Informationen und Status-Meldungen.

Ziele:

- Abstrakte Anbindung verschiedener Leser (z.B. PN532, später weitere Modelle), ohne hart verdrahtete Treiber-Implementierungen.
- Zwei Betriebsmodi:
  1. **Lern-Modus** – neue Tags erfassen und an WebUI/Backend melden.
  2. **Normal-Modus** – Tags kontinuierlich überwachen und Wiedergabe indirekt triggern.

Nicht-Ziele:

- Keine Persistenz oder Datenbankzugriffe.
- Kein Wissen über Playlists, Songs oder Benutzerprofile.
- Kein direktes Ansteuern des Audio-Systems.

---

## 2. Datei- und Ordnerstruktur

Relevanter Pfad: `services/rfid-service/src/rfid_service/`

```text
rfid_service/
├── __init__.py                  # Package-Init
├── main.py                      # Einstiegspunkt: Config, RFIDManager, MQTT, API-Server, Graceful Shutdown
├── config.py                    # Lädt Env + rfid.json
├── config_schema.py             # Pydantic-Schema für RFID-Config (reader_type, interface, scan_interval_ms, duplicate_suppression_ms)
├── config_manager.py            # JSON-Config (config/rfid.json)
├── exceptions.py                # Service-spezifische Exceptions
├── core/
│   ├── __init__.py
│   └── rfid_manager.py          # Lern-/Normal-Modus, Scan-Loop, Duplicate-Suppression, Publish tag-scanned/tag-removed/status
├── infrastructure/
│   ├── __init__.py
│   ├── mqtt_client.py           # MQTT: Subscriptions (cmd/set-mode, config/general), Publish (tag-scanned, tag-removed, status)
│   └── hardware/
│       ├── __init__.py
│       ├── reader_interface.py  # Abstrakte RFIDReader-Schnittstelle
│       ├── reader_factory.py    # Factory: Reader-Instanz je reader_type (pn532, mock)
│       ├── pn532_reader.py      # PN532-Hardware-Implementierung
│       └── mock_reader.py        # Mock-Reader für Tests/Entwicklung
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI: GET /health (Reader, MQTT-Status)
└── models/
    ├── __init__.py
    ├── events.py                # Event-Definitionen / Datentypen für RFID-Events
    └── schemas.py               # Pydantic-Schemas für API/MQTT
```

---

## 3. Öffentliche Schnittstellen

### 3.1 MQTT

Grundschema aller Topics:

```text
minabox/<device-id>/<domain>/<action>
```

**Publish (vom RFID-Service):**

- Lern-Modus:
  - `minabox/<device-id>/rfid/tag-scanned-learning`
    - Payload (JSON):
      - `tag_id`: String, UID des Transponders im Hex-Format (z.B. `04A224BC19`).
      - `reader_id`: String (z.B. `pn532_01`).
      - `timestamp`: ISO-8601-String.

- Normal-Modus:
  - `minabox/<device-id>/rfid/tag-scanned`
    - Payload: wie oben.
  - `minabox/<device-id>/rfid/tag-removed`
    - Payload:
      - `tag_id`: String, zuletzt erkannter Tag.
      - `reader_id`: String.
      - `timestamp`: ISO-8601-String.

- Status (retained):
  - `minabox/<device-id>/rfid/status`
    - Payload (JSON):
      - `state`: `idle` | `normal` | `learning` | `error`.
      - `reader_id`: aktueller Reader.
      - `error`: optionaler Fehlercode (siehe Fehler & Status).
      - `timestamp`: ISO-8601-String.

**Subscribe (vom RFID-Service):**

- Modus umschalten:
  - `minabox/<device-id>/rfid/cmd/set-mode`
    - Payload:

    ```json
    { "mode": "learning" }
    ```

    oder

    ```json
    { "mode": "normal" }
    ```

**Hinweis Config-API:** Der RFID-Service unterstützt **kein** generisches Config-API-Pattern (keine Topics `config/get`, `config/update`, `config/response` wie bei Button- und LED-Service). Die Konfiguration erfolgt ausschließlich über die Datei `config/rfid.json`; zur Laufzeit kann nur der Modus (`cmd/set-mode`) per MQTT umgeschaltet werden. `minabox/<device-id>/config/general` wird für globale Einstellungen (z.B. Logging-Level) verwendet.

### 3.2 REST (optional)

Optional kann der Service einen kleinen HTTP-Endpoint anbieten (z.B. FastAPI), hauptsächlich für Health-/Debug-Zwecke:

- `GET /health` – Gesundheitszustand, aktueller Reader, MQTT-Status.

Alle fachlichen Funktionen (Lernen, Mapping, Playback) laufen über MQTT und werden im Backend gebündelt.

---

## 4. Kern-Funktionen / Use-Cases

### 4.1 Lern-Modus (Tag anlernen)

Ablauf:

1. Backend/WebUI setzt den Modus über MQTT:
   - `minabox/<device-id>/rfid/cmd/set-mode` → `{"mode": "learning"}`.
2. RFID-Service wechselt in Lern-Modus (`state = learning`) und publisht Status auf `.../rfid/status`.
3. Beim Auflegen eines Tags:
   - Tag wird gelesen → `tag_id` (UID als Hex-String) ermittelt.
   - Event wird publisht: `minabox/<device-id>/rfid/tag-scanned-learning`.
4. Backend/WebUI zeigt Tag in der UI an und erlaubt Zuordnung zu Playlist/Song.
5. Backend speichert Tag→Content-Mapping in der Datenbank.
6. Nach Abschluss kann der Modus wieder auf `normal` gesetzt werden.

Optional: Ein konfigurierbarer Timeout kann den Lern-Modus nach einer gewissen Zeit ohne Scan automatisch zurück in den Normal-Modus setzen.

### 4.2 Normal-Modus (Tag → Playback)

Ablauf:

1. RFID-Service läuft im Normal-Modus (`state = normal`).
2. Service scannt kontinuierlich Tags.
3. Bei erkanntem Tag:
   - Tag wird gelesen → `tag_id` ermittelt.
   - Event: `minabox/<device-id>/rfid/tag-scanned` mit UID und Reader-ID.
4. Backend empfängt Event, löst aus:
   - Lookup `tag_id` → Playlist/Song.
   - Triggert Audio-Service, z.B. via `minabox/<device-id>/audio/play`.
5. Wenn der Tag entfernt wird und der Reader das erkennt:
   - Event: `minabox/<device-id>/rfid/tag-removed`.
   - Backend kann z.B. Pause/Stop auslösen.

### 4.3 Doppeltes Scannen / Entprellen

Um mehrfaches Auslösen durch leichte Bewegungen zu vermeiden:

- Der Service besitzt einen Parameter `duplicate_suppression_ms` (z.B. 2000 ms).
- Wenn dieselbe `tag_id` innerhalb dieses Zeitfensters erneut erkannt wird, wird **kein** neues `tag-scanned`-Event erzeugt.
- Erst nach Ablauf dieser Zeit erzeugt ein erneuter Scan desselben Tags wieder ein Event.

---

## 5. Abhängigkeiten

- **Hardware:**
  - Mindestens ein RFID-Reader (z.B. PN532), abstrahiert über eine Reader-Interface-Klasse (z.B. `RFIDReader`), sodass weitere Modelle eingebunden werden können.

- **MQTT-Broker:**
  - Verbindung zu Mosquitto (Host/Port aus zentraler `.env`).

- **Backend-Service:**
  - Verarbeitet Lern-Events (`tag-scanned-learning`) und Normal-Events (`tag-scanned`).
  - Führt Tag→Content-Mapping durch und triggert Audio-Service.

- **Konfiguration:**
  - Globale `.env` (Root):
    - `MINABOX_DEVICE_ID` – Box-ID für MQTT-Topics.
    - `MQTT_BROKER`, `MQTT_PORT`.
  - Service-spezifische `config/rfid.json`:
    - `reader_type`: z.B. `"pn532"`, `"mock"`.
    - `interface`: z.B. `"i2c"`, `"spi"`, `"uart"`.
    - `scan_interval_ms`: Scan-Intervall.
    - `duplicate_suppression_ms`: Zeitfenster zur Unterdrückung von Doppel-Scans.

---

## 6. Fehler & Status

### 6.1 Zustände

Der `state` im Status-Payload kann folgende Werte annehmen:

- `idle` – Service läuft, Reader initialisiert, aber kein aktiver Scan (z.B. kurz nach Start).
- `normal` – Normal-Modus aktiv, kontinuierliches Scannen.
- `learning` – Lern-Modus aktiv.
- `error` – Fehler verhindert normalen Betrieb.

### 6.2 Typische Fehlercodes

Im Feld `error` des Status-Payloads können z.B. auftreten:

- `reader_not_found` – Reader-Hardware nicht erreichbar (falscher Bus, Kabelproblem).
- `reader_init_failed` – Initialisierung des Reader-Treibers fehlgeschlagen.
- `read_timeout` – Lesen eines Tags ist wiederholt fehlgeschlagen.
- `protocol_error` – Unerwartete oder ungültige Antwort vom Reader.

Beispiel-Status bei Fehler:

```json
{
  "state": "error",
  "reader_id": "pn532_01",
  "error": "reader_not_found",
  "timestamp": "2026-02-14T13:30:00Z"
}
```

### 6.3 Logging

Der Service loggt alle relevanten Ereignisse strukturiert, z.B.:

- `tag_scanned` mit `tag_id`, `reader_id`.
- `tag_removed` mit `tag_id`, `reader_id`.
- `mode_changed` mit `old_mode`, `new_mode`.
- Fehler mit `error_code` (z.B. `reader_not_found`, `read_timeout`).

Die Log-Konfiguration folgt den globalen Logging-Regeln aus dem Framework (structlog, JSON-Logging, Level-Definitionen).

---

## 7. Nicht-Ziele / Abgrenzung

- Keine Persistenz von Tag-Mappings (rein Sache des Backends).
- Kein direktes Ansteuern des Audio-Services (nur Events).
- Keine UI-Logik – der Service kennt WebUI und Frontend nicht, sondern spricht ausschließlich über MQTT und evtl. einen Health-Endpoint.

---

## 8. Refactoring-Checkliste

- [ ] **Keine groben Inkonsistenzen:** RFID-Manager in core, Hardware-Abstraktion in infrastructure/hardware, MQTT in infrastructure.
- [ ] Nach Refactoring: Dateistruktur und „Funktion pro Datei“ in diesem Dokument aktualisieren.
