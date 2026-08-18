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
- [x] **SQLite WAL Mode:** Die SQLite-Datenbank wird im WAL-Modus betrieben (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `temp_store=MEMORY`). Umgesetzt in `db_manager.py` via SQLAlchemy Engine-Event.
- [ ] **Transaktions-Timeouts:** Kürzere Timeouts für DB-Transaktionen einstellen, um Deadlocks zu vermeiden.

### OS & SD-Karten-Schutz
- [x] **Log-Rotation & tmpfs:** Docker-Logs werden via `deploy/docker-daemon.json` auf `max-size: "10m"` und `max-file: "3"` begrenzt. Datei nach `/etc/docker/daemon.json` kopieren und Docker neu starten.
- [ ] **Read-Only RootFS (Optional):** Für maximale Robustheit sollte das Host-System (Raspberry Pi OS) als Read-Only konfiguriert werden, mit OverlayFS für `/var/log` und `/data`. So kann die Box jederzeit einfach vom Strom gezogen werden (Stecker raus), ohne dass das Dateisystem oder die DB korrumpiert.
- [ ] **Zustandsspeicherung im RAM:** Der `audio_status.json` wird potenziell sekündlich geschrieben. Dies sollte in ein In-Memory-Laufwerk (`tmpfs` Docker-Volume) ausgelagert werden, um die SD-Karte nicht in wenigen Monaten kaputtzuschreiben.

## 2. WebUI & Frontend-Optimierungen

> **Vollständige Redesign-Bewertung:** Siehe [docs/services/webui/Redesign.md](services/webui/Redesign.md) für eine detaillierte Analyse (Docker-Container-Kopplung, Struktur, Performance, neue Features) mit priorisierter Umsetzungsreihenfolge. Die Punkte unten sind die Kurzfassung der dort dokumentierten offenen Punkte plus bereits erledigte.

### Docker-Kopplung (kritisch, siehe Redesign.md Abschnitt 1)
- [x] **Nginx-Upstream-Resolver:** `nginx.conf` nutzte `proxy_pass http://backend:8080;` mit fest aufgelöstem Hostnamen – nach einem Backend-Rebuild blieb die alte IP gecacht, was zu dauerhaften 502-Fehlern führte, bis der WebUI-Container neu gestartet wurde. Umgesetzt: `resolver 127.0.0.11 valid=10s ipv6=off;` + `set $backend_upstream http://backend:8080;` in `/api/`, `/ws`, `/static/`. Mit einem isolierten Testaufbau verifiziert (alte Config hing nach echtem IP-Wechsel des Backends fest, neue Config resolvte automatisch neu). `depends_on: webui → host-helper` auf `service_started` gelockert, sodass die UI unabhängig vom Backend-Zustand startet.

### Performance: WebSocket State Management
- [x] **Pub/Sub-Muster:** Event-Emitter via `wsEventTarget` (EventTarget) und `useWebSocketEvent`-Hook umgesetzt. Komponenten subscriben sich gezielt auf einzelne Nachrichtentypen, ohne globalen Re-Render des kompletten Context.

### Datenbeschaffung (Data Fetching)
- [~] **React Query / SWR:** Für `PlayerPage` bereits umgesetzt (`@tanstack/react-query` mit Caching/staleTime). `MediaPage` lädt weiterhin alles per `Promise.all` in lokalen `useState` ohne Cache/Pagination – Migration steht noch aus (siehe Redesign.md Abschnitt 3, Punkt C2).

### Ausgeliefertes Bundle
- [x] **`gzip_static` aktivieren:** `vite-plugin-compression` erzeugte bereits `.gz`/`.br`-Dateien im Build, `nginx.conf` lieferte sie aber nie aus (nur dynamisches `gzip on`) – der Pi komprimierte bei jedem Request neu. `gzip_static on;` gesetzt, Brotli-Plugin entfernt (im `nginx:alpine`-Image nicht einkompiliert). Live verifiziert: Assets werden mit `Content-Encoding: gzip` aus der vorgebauten `.gz`-Datei ausgeliefert.
- [x] **Google Fonts self-hosten:** `index.html` lud Roboto von `fonts.googleapis.com` – render-blockierender externer Request, problematisch bei WLAN-Ausfall im Kinderzimmer. Auf `@fontsource/roboto` (lokal, in `main.tsx` importiert) umgestellt.

### PWA & App-Erlebnis
- [x] **PWA (Progressive Web App):** `vite-plugin-pwa` integriert – App kann als Standalone-App auf dem Homescreen installiert werden.
- [x] **Verbindungsabbruch-Screen:** `ConnectionLostScreen`-Komponente umgesetzt. Zeigt nach 3s Disconnect einen Vollbild-Overlay mit "Minabox nicht erreichbar" und verschwindet automatisch bei Reconnect.
- [x] **PWA-Manifest-Icons ergänzt:** `vite-plugin-pwa`-Konfiguration in `vite.config.ts` hatte kein Icon-Set und einen falschen `theme_color` (`#ffffff` statt `#e65100`). Vier Icons (192/512, normal + maskable) aus dem Favicon-Design generiert unter `public/icons/`, Manifest korrigiert.

### Mobile Bedienung (Zielgerät: Smartphone 6–7")

- [x] **Edit-Dialoge als Vollbild-Sheet auf dem Telefon:** Von 47 `<Dialog>`-Instanzen nutzten nur 3 Komponenten `fullScreen`. Ein zentrierter Dialog liess bei eingeblendeter Tastatur (~45 % Displayhöhe) nur noch ein paar hundert Pixel Formular übrig – der Speichern-Button in den `DialogActions` lag ausserhalb des Sichtbereichs. Neue Komponente `components/common/ResponsiveDialog.tsx` (API-gleich zu `Dialog`, `fullScreen` unterhalb `sm`, Aktionsleiste über der Geräte-Schutzzone, `overscroll-behavior: contain` im Content). In 13 Formular-Dialogen eingesetzt: TagEditDialog, MediaPage-Track-Edit, Upload/MediaImport/RemoteTrack, Stream/StreamEdit, Podcast/PodcastEdit, PlaylistList-Formular, PlaylistTracksDialog, AddToPlaylistDialog, SecurityPanel-Passwortdialog. Bestätigungs-Dialoge (Ja/Nein) bleiben bewusst kleine Karten.
- [x] **Tastatur verdeckt Formulare nicht mehr (Android/Chrome):** `interactive-widget=resizes-content` im Viewport-Meta – der Layout-Viewport schrumpft beim Einblenden der Tastatur, statt Inhalt dahinter zu verstecken. iOS ignoriert den Wert (scrollt das fokussierte Feld selbst in den Blick).
- [x] **Touch-Ziele auf 44 px:** MUI rendert `IconButton size="small"` als 30 px Trefferfläche (padding 5 + 20 px Icon) – 62 Verwendungen quer durch Listen, Karten und Dialoge. Theme-Override in `main.tsx` zieht `sizeSmall` unter `@media (pointer: coarse)` auf 44×44 px auf; Icon-Grösse und Maus-Desktops bleiben unverändert. `MenuItem` bringt mit `minHeight: 48` bereits genug mit.
- [x] **Geräte-Schutzzone (Gestenleiste) berücksichtigt:** `viewport-fit=cover` im Viewport-Meta plus `SAFE_AREA_BOTTOM` (`env(safe-area-inset-bottom, 0px)`, exportiert aus `Navigation.tsx`). BottomNav trägt den Wert als Padding, MiniPlayer, MediaFab und der Bottom-Offset des `<main>` in `App.tsx` rechnen ihn auf. Vorher lagen BottomNav-Labels auf Geräten mit Gestenleiste unter dem Home-Indicator.
- [x] **`100dvh` statt `100vh`:** Mobile-Browser rechnen `vh` gegen die *grösste* Viewport-Höhe (eingeklappte URL-Leiste). Betroffen: `App.tsx` (`minHeight`), `TrackList.tsx` (`calc(100vh - 220px)` – der Panel ragte darunter und die innere Virtuoso-Liste bekam einen zweiten, konkurrierenden Scroll), `PlayerPage.tsx`. Per `@supports`-Block gesetzt, `vh` bleibt Fallback.
- [x] **RFID-Tag-Zuweisung: Auswahl mit Suche.** `TagEditDialog` listete Inhalte in einem einfachen `<Select>` – bei 200 Tracks ein 200-Zeilen-Popover ohne Suche, und das im meistgenutzten Edit-Flow überhaupt. Umgesetzt: Inhaltstyp als `ToggleButtonGroup` (vier kurze Labels nebeneinander, ein Tap statt Tap-Scroll-Tap), Inhalt als `Autocomplete` mit Volltextsuche über Playlists/Tracks/Streams/Podcasts (`blurOnSelect`, damit die Tastatur nach der Auswahl wieder zugeht). Neuer i18n-Key `new_tag_dialog.no_options` in DE und EN.
- [x] **Playlist-Reihenfolge auf dem Touchscreen.** `PlaylistTracksDialog` sortierte per dnd-kit an einem 20 px-Griff, in einer Scroll-Box (`maxHeight: 240`) in einem Scroll-Dialog – drei verschachtelte Scroll-Container, und ein Track von Position 30 auf 1 war praktisch nicht zu ziehen. Umgesetzt: „Reihenfolge" und „Hinzufügen" als zwei Tabs (immer nur ein Scroll-Container aktiv, `maxHeight` entfällt), auf `(pointer: coarse)` ersetzen Hoch/Runter-Buttons den Drag-Griff, dnd-kit bleibt für Zeigergeräte aktiv. Neue i18n-Keys `playlists.move_up`/`move_down`.
- [x] **Log-Viewer im Vollbild.** `ServiceLogsModal` und `SyslogModal` zeigten Monospace-Logs in einem zentrierten Dialog – auf 6–7" blieben ~40 Zeichen pro Zeile. Auf `ResponsiveDialog` umgestellt; die feste `minHeight: 60vh`/`maxHeight: 85vh` des ServiceLogsModal gilt jetzt erst ab `sm`, im Vollbild-Sheet füllt der Dialog ohnehin den Schirm.

- [x] **Bereichswechsel ohne Wischgeste (Mediathek, Eltern-Dashboard):** Beide Seiten nutzten `Tabs variant="scrollable"`. MUI gibt jedem `Tab` `minWidth: 90px` – fünf Bereiche brauchen also mindestens 450 px, auf einem 390-px-Gerät bleiben nach dem `PageShell`-Padding 366 px. Die Leiste lief zwangsläufig über, und man musste wischen, um überhaupt zu *sehen*, dass es weitere Bereiche gibt; die Scroll-Pfeile fraßen die knappe Breite zusätzlich. Neue Komponente `components/common/SectionTabs.tsx`: Desktop unverändert Tabs, unterhalb `sm` eine Zeile mit aktuellem Bereich und Zähler („2/5"), ein Tap öffnet die vollständige Liste als Bottom-Sheet aus der Daumenzone (52 px hohe Zeilen, Häkchen beim aktiven Bereich, Safe-Area-Padding). Gleiches Muster wie die Einstellungsseite, die ihre Gruppen auf Mobil schon aufklappt statt sie in eine Tab-Leiste zu zwingen.
### Einstellungsseite: Überschriften-Hierarchie

- [x] **Dritte Ebene vereinheitlicht (`SettingsBlock`):** Gruppe (Tab/Accordion) und Section (`SettingsSection`) waren zentral gerendert und damit konsistent – die Blöcke *innerhalb* einer Section erfand dagegen jedes Formular neu. Im Bestand fanden sich fünf Varianten nebeneinander: `overline`+`text.secondary` (12×, De-facto-Standard), `overline` ohne `text.secondary` (DesignSettingsForm), `subtitle1` fett in einem Paper und `subtitle2` secondary (beide DisplayConfigPanel), `h6` (AuthSection). Neue Komponente `components/admin/SettingsBlock.tsx` mit Titel als `overline` secondary, optionalem `caption`-Erklärtext direkt unter dem Titel und festem Abstand; in 11 Komponenten mit 21 Blöcken eingesetzt.
- [x] **Jeder Block hat einen Titel – auch der erste.** Vorher standen die ersten Felder einer Section regelmäßig überschriftslos da (`AudioConfigForm`: zwei Gerätefelder vor dem ersten Divider; `DesignSettingsForm`: die Sprachauswahl saß zwischen „Eigenes Logo" und „Erscheinungsbild" und sah aus, als gehöre sie zum Logo). Neue Blöcke: „Gerät & Anschluss", „Beim Einschalten", „Sprache", „Board-LEDs" (der Stealth-Schalter hing bis dahin ohne jede Überschrift unter der LED-Liste).
- [x] **Überschriften wiederholen nicht mehr ihre Elternebene.** Vorher las man dasselbe Wort auf drei Ebenen: Gruppe *Netzwerk* › Section *WLAN & Adresse* › Block *Netzwerk*; Gruppe *Wartung* › Block *Wartung*; Gruppe *Sicherheit* › Block *Sicherheit*. Umbenannt (DE und EN): „Netzwerk"→„Verbindungsdetails", „Wartung"→„Version & Update", „Sicherheit"→„Fernzugriff (SSH)", „Hostname"→„Gerätename", „Host"→„Gerät", „Docker-Containerstatus"→„Dienste". Ganze Sätze wandern in den Erklärtext: „Wenn eine Karte aufgelegt wird" ist jetzt der Titel „Karte auflegen" plus `control.section_rfid_hint`.
- [x] **Einheitliche Breite:** `maxWidth` saß in 3 von 21 Formularen (560 px), der Rest lief über die volle Breite – auf dem Desktop stand ein schmales Formular direkt neben einem randlosen Panel. Die Begrenzung sitzt jetzt einmal in `SettingsSection` (720 px, weit genug für die Display-Elementliste und die Knopf-/LED-Karten).

### Code-Qualität & Maintenance
- [ ] **ESLint Update:** Upgrade von v8 auf v9 (Flat Config), da v8 EOL ist.
- [ ] **React 19 Readiness:** Vorbereitung der Code-Basis für React 19 (z.B. Ersetzen von manuellen `useMemo` durch den React Compiler, falls anwendbar).
- [x] **Toten Tailwind-Stack entfernt:** `tailwindcss`, `@tailwindcss/vite`, `lucide-react`, `class-variance-authority`, `clsx` waren installiert und liefen im Build mit, wurden aber nirgends in `src/` verwendet (0 `className`-Nutzungen). Entfernt aus `package.json`/`vite.config.ts`, dazu die toten Dateien `components/ui/button.tsx` und `lib/utils.ts` gelöscht.
- [x] **Kontrastfehler aktiver Nav-Eintrag behoben:** `Navigation.tsx` nutzte `primary.light` als Hintergrund für den aktiven Eintrag – ergab je nach Farb-Preset nur ~2.2–3.8:1 Kontrast zu weißem Text (WCAG AA verlangt 4.5:1). Auf `primary.dark` umgestellt, rechnerisch für alle 5 Presets auf 4.5:1+ geprüft (7.3:1 bis 15.2:1).
