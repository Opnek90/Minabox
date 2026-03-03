# Optimierungsvorschläge & Robustheit (Chuck-Norris-Proof)

Diese Datei dokumentiert potenzielle Verbesserungen, Architektur-Optimierungen und vor allem Maßnahmen zur maximalen Ausfallsicherheit ("Robustheit") des Minabox-Projekts. Das Ziel ist es, das System so stabil zu machen, dass es den rauen Kinderzimmer-Alltag problemlos übersteht.

## 1. System & Hardware (Chuck-Norris-Proofing)

### RFID & I2C Ausfallsicherheit
- [ ] **I2C Bus Auto-Recovery:** Der PN532 am I2C-Bus kann sich bei statischer Aufladung oder Wackelkontakten aufhängen. Der `rfid_service` sollte einen hängenden I2C-Bus erkennen (z.B. Timeout beim Lesen) und den Bus oder den Sensor automatisch reinitialisieren, anstatt abzustürzen.
- [ ] **Reader Watchdog:** Wenn der RFID-Reader für X Minuten keine Lebenszeichen mehr sendet, sollte ein Health-Check fehlschlagen und Docker den Container automatisch über `restart: unless-stopped` neu starten.

### Audio & Playback Langlebigkeit
- [x] **Audio-Popping unterdrücken:** Deaktivierung von `suspend-on-idle` für PipeWire/PulseAudio via Docker-Umgebungsvariablen umgesetzt.
- [x] **RFID-Bouncing (Flatter-Schutz):** Serverseitiger Debounce (15s) und Playback-Intent-Tracking eingebaut, um das Verschlucken bei schnellem Auflegen/Abziehen zu verhindern.
- [ ] **Stream Auto-Reconnect:** Wenn ein Internet-Stream (z.B. Webradio) abbricht (WLAN-Loch), sollte der `audio_service` versuchen, den Stream automatisch wiederherzustellen (mit exponentiellem Backoff), anstatt stumm zu bleiben.
- [ ] **Lautstärke-Limiter auf OS-Ebene:** Hard-Limit der maximalen ALSA-Lautstärke im Dockerfile oder via `amixer`, damit Fehler im Code (oder böse MQTT-Befehle) nicht die Boxen zerstören oder Gehörschäden verursachen.

### Datenbank & Zustand (SQLite)
- [ ] **SQLite WAL Mode:** Die SQLite-Datenbank muss im WAL-Modus (`PRAGMA journal_mode=WAL;`) betrieben werden. Aktuell können konkurrierende Lese-/Schreibzugriffe (z.B. von WebUI und RFID-Scanning gleichzeitig) zu `database is locked` Fehlern führen.
- [ ] **Transaktions-Timeouts:** Kürzere Timeouts für DB-Transaktionen einstellen, um Deadlocks zu vermeiden.

### OS & SD-Karten-Schutz
- [ ] **Log-Rotation & tmpfs:** Aktuell schreiben alle Services potenziell viel Output. Docker-Logs sollten via `daemon.json` stark begrenzt werden (`max-size: "10m"`, `max-file: "3"`). 
- [ ] **Read-Only RootFS (Optional):** Für maximale Robustheit sollte das Host-System (Raspberry Pi OS) als Read-Only konfiguriert werden, mit OverlayFS für `/var/log` und `/data`. So kann die Box jederzeit einfach vom Strom gezogen werden (Stecker raus), ohne dass das Dateisystem oder die DB korrumpiert.
- [ ] **Zustandsspeicherung im RAM:** Der `audio_status.json` wird potenziell sekündlich geschrieben. Dies sollte in ein In-Memory-Laufwerk (`tmpfs` Docker-Volume) ausgelagert werden, um die SD-Karte nicht in wenigen Monaten kaputtzuschreiben.

## 2. WebUI & Frontend-Optimierungen

### Performance: WebSocket State Management
- [ ] **Pub/Sub-Muster:** Aktuell wird jede WebSocket-Nachricht im globalen React Context gespeichert. Das zwingt alle UI-Komponenten zu einem Re-Render. Stattdessen einen Event-Emitter (z.B. `mitt` oder `zustand`) nutzen, bei dem sich Komponenten gezielt subscriben können (`useWebSocketEvent('audio_status', callback)`).

### Datenbeschaffung (Data Fetching)
- [ ] **React Query / SWR:** Anstatt `useEffect` und lokales Loading-State-Handling zu nutzen, sollte `@tanstack/react-query` für REST-Calls genutzt werden (Caching, Error-Handling, Auto-Refetching).

### PWA & App-Erlebnis
- [ ] **PWA (Progressive Web App):** Integration von `vite-plugin-pwa`, damit Eltern das UI wie eine native App (ohne Browser-Adressleiste) auf dem Homescreen installieren können.
- [ ] **Verbindungsabbruch-Screen:** Wenn die Box offline geht (z.B. ausgeschaltet wird), sollte das WebUI sofort einen netten "Box ist offline"-Screen anzeigen, statt in unendlichen Loading-States zu hängen.

### Code-Qualität & Maintenance
- [ ] **ESLint Update:** Upgrade von v8 auf v9 (Flat Config), da v8 EOL ist.
- [ ] **React 19 Readiness:** Vorbereitung der Code-Basis für React 19 (z.B. Ersetzen von manuellen `useMemo` durch den React Compiler, falls anwendbar).
