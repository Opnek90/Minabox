# WebUI – Redesign-Review

**Status:** Phase 1 (Docker-Entriegelung), Phase 2 (Quick Wins) und Phase 3 (B1 BottomNavigation, B2 Player entschlacken, B3 Dashboard/Admin-Trennung, B4 Settings-Suche) umgesetzt und deployt. B3/B4 hier sind die einfache Version (SystemStatusPanel ins Dashboard, Titel-basierte Suche) – die tiefergehende 5-Gruppen-Reorganisation ist als separates Konzept in [Settings-Reorganisation.md](Settings-Reorganisation.md) dokumentiert, aber nicht umgesetzt (offene Entscheidung, siehe dort Abschnitt 6). Phase 4 (Datenschicht, C2) offen.
**Erstellt:** 2026-08-17, zuletzt aktualisiert: 2026-08-17
**Grundlage:** Statische Code-Analyse (`services/webui-service/src/`, `nginx/nginx.conf`, `Dockerfile`, `vite.config.ts`, `docker-compose.yml`, Backend-Routen unter `services/backend-service/src/backend_service/api/`). Die laufende UI wurde nicht im Browser bedient – UX-Punkte (Abschnitt 3) stützen sich auf Struktur- und Komponentendichte, nicht auf visuelle Prüfung.

Dieses Dokument bündelt eine Redesign-Bewertung der WebUI mit besonderem Fokus auf die Docker-Container-Topologie, da alle Services im zentralen `docker-compose.yml` voneinander abhängen und jede Architektur-Änderung diese Kette berücksichtigen muss. Es ergänzt [Architecture.md](Architecture.md) (Ist-Struktur) und [docs/Optimierungen.md](../../Optimierungen.md) (projektweite Robustheit).

---

## 1. Docker-Randbedingung (verbindlich für jedes Redesign)

### 1.1 Aktuelle Startkette

```
mqtt → backend → host-helper → webui
                → audio
       mqtt     → rfid, button, led (parallel zu backend)
       backend  → media-downloader
```

Die WebUI hängt heute am **Ende** der Kette (`depends_on: host-helper: condition: service_healthy`). Das ist verkehrt herum: Die WebUI ist das einzige Diagnosewerkzeug des Systems und sollte der *verfügbarste* Container sein, nicht der letzte. Kumulierte `start_period`-Werte (10s + 20s + 10s) plus Healthcheck-Intervalle verzögern die erste ausgelieferte Seite unnötig, und ein hängendes Backend verhindert aktuell jede Fehlerdiagnose über die UI.

### 1.2 Befund A1 — Statischer nginx-Upstream-Hostname [BEHOBEN]

`services/webui-service/nginx/nginx.conf` verwendet `proxy_pass http://backend:8080;` direkt in den Locations `/api/`, `/ws` und `/static/`. Das hat zwei Konsequenzen:

1. **Harte Kopplung beim Start:** nginx löst `backend` beim Config-Load auf. Existiert der Container nicht, startet nginx nicht (`host not found in upstream`) – das ist der eigentliche Grund für das `depends_on: host-helper` (transitiv über backend).
2. **Stale-IP nach Rebuild:** nginx cached die aufgelöste IP dauerhaft für die Lebensdauer des Worker-Prozesses. Nach `docker compose up -d --build backend` bekommt der Backend-Container eine neue IP – nginx zeigt weiter auf die alte Adresse. Ergebnis: **permanente 502 Bad Gateway**, bis der WebUI-Container manuell neu gestartet wird. Verifiziert am laufenden Stack: `backend` = `172.18.0.9`, von nginx aktuell korrekt aufgelöst, aber nur weil seit dem letzten Backend-Rebuild kein Reload stattfand.

**Fix (löst beide Punkte gemeinsam):**

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;   # Docker embedded DNS
set $backend_upstream http://backend:8080;
proxy_pass $backend_upstream;              # in /api/, /ws, /static/
```

Mit einer Variable resolvt nginx bei jedem Request neu über Dockers eingebauten DNS-Server statt einmalig beim Start. Danach kann `depends_on` für `webui` auf `service_started` (oder ganz entfallen) reduziert werden – die UI startet in jedem Fall, und der bereits vorhandene `ConnectionLostScreen` übernimmt die Anzeige, falls das Backend noch nicht bereit ist.

**Umgesetzt (2026-08-17):** `nginx.conf` nutzt jetzt `resolver 127.0.0.11 valid=10s ipv6=off;` + `set $backend_upstream http://backend:8080;` in `/api/`, `/ws`, `/static/`. `docker-compose.yml`: `webui → host-helper` auf `condition: service_started` reduziert. Verifiziert mit einem isolierten Testaufbau (zwei nginx-Container, alte vs. neue Config, gegen einen Stub-Backend-Container mit erzwungenem IP-Wechsel via `--ip`): Die alte Config hing nach dem IP-Wechsel an der toten Adresse fest (`wget: download timed out`), die neue Config resolvte automatisch neu und erreichte den Backend-Container unter der neuen IP. Anschließend live gegen den echten Stack getestet: `minabox-webui` neu deployt, `/health`, `/api/v1/system/version` und `/static/`-Pfad funktionieren.

### 1.3 Architektur-Leitplanken für jedes Redesign

| Regel | Begründung |
|---|---|
| WebUI bleibt **statisches nginx** – kein SSR, kein Next.js, kein eigener Node-Prozess im Container | Ein zusätzlicher Node-Prozess in der Startkette kostet Boot-Zeit und RAM auf dem Pi und verlängert die Kette statt sie zu verkürzen |
| Alle neuen Daten **ausschließlich über `backend:8080`** | `host-helper` hat bewusst kein Port-Mapping nach außen; `led`/`button`/`display`/`media-downloader` direkt zu proxien würde 4 weitere DNS-Abhängigkeiten in nginx erzeugen – jede mit dem A1-Problem, falls nicht per `resolver`-Variable gelöst |
| WebUI-Healthcheck prüft **nur nginx selbst** (`/health` → `return 200`) | ist heute korrekt so. Backend-Health gehört in die UI-Anzeige (Alert-Bar/ConnectionLostScreen), nicht in den Container-Healthcheck – sonst restartet Docker die UI, sobald das Backend kurz hustet |
| Kein Shared Volume zwischen `webui` und anderen Services | Der Build ist self-contained (Multi-Stage: Node-Build → Nginx-Serve); das soll so bleiben, um die WebUI unabhängig deploybar zu halten |

---

## 2. Redesign-Bewertung

### 2.1 Trägfähige Substanz (Basis für das Redesign, nicht ersetzen)

- Service-Layer-Trennung `api/` → `hooks/` → `components/`
- `ActionButton` als einziges Button-Primitiv, Variante über semantisches `actionType` statt Ad-hoc-Styling
- `ThemeContext` mit CSS-Custom-Properties (`applyTokens`)
- WebSocket-EventTarget-Pub/Sub (`wsEventTarget`, `useWebSocketEvent`) – vermeidet globalen Re-Render bei jeder WS-Nachricht
- `useAudioStatus` mit clientseitiger Positions-Extrapolation zwischen WS-Updates

### 2.2 Strukturelle Schwächen

**B1 — Mobile-Navigation passt nicht zum Nutzungsmuster. [BEHOBEN]**
`Navigation.tsx`: Permanent-Drawer (220px) auf Desktop, Hamburger-Drawer auf Mobile. Für ein Gerät, das überwiegend vom Smartphone bedient wird, war Navigation oben links die schlechteste Daumenzone; der MiniPlayer lag unten fix (`zIndex: 1200`). Umgesetzt: `Navigation.tsx` in zwei Komponenten aufgeteilt – `Navigation` (Desktop, unverändert permanenter Drawer) und neu `MobileBottomNav` (fixierte `BottomNavigation` mit den 5 Nav-Punkten, `zIndex: 1100`). `App.tsx` rendert je nach Breakpoint (`down('md')`) die passende Variante, Hamburger-Button und `showMenuButton`/`onMenuToggle` komplett aus `Header.tsx` entfernt. `MiniPlayer` und `MediaFab` bekamen einen zusätzlichen mobilen Bottom-Offset (`MOBILE_BOTTOM_NAV_HEIGHT = 56px`), damit sie über der BottomNav statt dahinter sitzen – Stacking geprüft: BottomNav (1100) < MiniPlayer/MediaFab (1200) < Header/SystemAlertBar (1201/1202) < RfidScanDrawer-Modal (1300) < Fade-Feedback (1400) < ConnectionLostScreen (2000). Deployt und im ausgelieferten `mui-*.js`-Chunk verifiziert (`MuiBottomNavigation`/`MuiBottomNavigationAction`-Klassen vorhanden).

**B2 — Player-Seite war überladen. [BEHOBEN]**
`PlayerPage.tsx` stapelte in einer 480px-Karte: Status-Chip, Sleep-Timer, Kiosk-Button, TrackInfo, ProgressBar, Controls, Volume, **Output-Device-Select + Refresh**, Repeat, Shuffle, Up-Next. Der Output-Device-Selector war eine Setup-Einstellung auf der Seite, die primär ein Kind bedient. Umgesetzt: Output-Device (jetzt als Dialog statt Inline-Select), Repeat/Shuffle-Toggles, Sleep-Timer-Start und Kiosk-Link in ein Overflow-Menü (⋮-Button in der Status-Zeile) verschoben. Sichtbar in der Hauptkarte bleiben: Cover/Titel, Progress, die 4 Haupt-Buttons, Volume, die aktive Sleep-Timer-Chip (falls ein Timer läuft – dann taucht der Start-Menüpunkt auch nicht mehr im Menü auf) und Up-Next (weiterhin eingeklappt). Deployt und im ausgelieferten `PlayerPage-*.js`-Chunk verifiziert (neue Menü-Strings und Icon-Referenzen vorhanden).

Nicht visuell/interaktiv im Browser getestet: Die Chrome-Extension war in dieser Umgebung nicht verbunden, und headless Chromium ließ sich auf diesem Pi/ARM-Setup nicht zum Rendern bewegen (Renderer-Prozess crash-loopt mit `Failed global descriptor lookup`, vermutlich ein Sandbox/IPC-Problem der Umgebung). Verifiziert wurde stattdessen: `tsc --noEmit` (keine neuen Fehler ggü. Baseline), `eslint` (keine neuen Warnungen ggü. Baseline), Produktions-Build, Live-Deploy gegen den echten Backend-Container, sowie Bundle-Inhaltsprüfung der ausgelieferten JS-Chunks. Ein manueller Klick-Test im Browser (Mobile-Breakpoint, Overflow-Menü, Output-Device-Dialog) steht noch aus.

**B3 — Zwei konkurrierende Übersichtsbereiche. [TEILWEISE BEHOBEN 2026-08-18]**
`/dashboard` (Overview, Stats, Scan-Verlauf) und `/admin` → Gruppe *System* (Status, System, Security) überschnitten sich inhaltlich. Umgesetzt: `SystemStatusPanel` (reine Diagnose: Host-Stats, Container-Health, Syslog – keine Konfigurationsaktionen) aus Admin→System in einen neuen Dashboard-Tab „System" verschoben, inklusive seiner drei exklusiven Unterkomponenten (`ServiceStatus.tsx`, `ServiceLogsModal.tsx`, `SyslogModal.tsx`, dazu `StatsDashboard.tsx` – alle von `components/admin/` nach `components/dashboard/` verschoben, da sie nur dort verwendet werden). Admin→System bleibt bei `SystemPanel` (Netzwerk/WLAN/Hostname/USB) + `SecurityPanel` (Auth/SSH/Passwort) – reine Konfiguration. Eine tiefergehende 5-Gruppen-Reorganisation (Design/Control neu zuordnen, Sleep-Timer-Defaults verschieben) ist als Konzept in [Settings-Reorganisation.md](Settings-Reorganisation.md) dokumentiert, aber nicht umgesetzt – das ist eine größere, invasivere Änderung mit einer offenen Entscheidung (siehe dort Abschnitt 6).

**B4 — Admin ist eine Formularwand ohne Suche. [TEILWEISE BEHOBEN 2026-08-18]**
`AdminPage.tsx`: 4 Gruppen × 12 Sections, Desktop als Tabs, Mobile als Accordions. Umgesetzt: Suchfeld über den Tabs/Accordions, filtert Gruppen- und Sektions-Titel (case-insensitive, aus `useSettingsGroups()`), Treffer erscheinen als flache Liste mit Gruppen-Chip statt der Tabs/Accordion-Navigation. Bewusst **nicht** umgesetzt: Feld-Level-Suche (z. B. Suche nach „Lautstärke" würde direkt zur Audio-Sektion springen) – das würde eine robuste Zuordnung von i18n-Strings zu Sections erfordern, die quer durch alle ~15 Formular-Komponenten nicht sauber 1:1 ist (z. B. nutzt `ChildSettingsForm` Keys aus dem `general.*`-Namespace). Titel-Suche ist der sichere, vollständig verifizierte erste Schritt; Feld-Level-Suche wäre eine separate, riskantere Erweiterung.

**B5 — Kontrastfehler bei aktivem Nav-Eintrag. [BEHOBEN]**
`Navigation.tsx`: `backgroundColor: 'primary.light'` mit `color: 'primary.contrastText'` ergab bei der Default-Palette (Orange, `#ff8a50`) Weiß auf Hellorange ≈ **2,2:1** Kontrast – riss WCAG AA (4.5:1) deutlich. Rechnerisch geprüft (relative Luminanz nach WCAG-Formel) über alle 5 Farb-Presets: `primary.main` reicht nicht durchgängig (Orange nur ~3,8:1), `primary.dark` erreicht 7,3:1 bis 15,2:1 für alle Presets. Umgesetzt: `primary.dark` als Hintergrund, Hover-Effekt über `filter: brightness(0.85)` statt Farbwechsel.

**B6 — Zwei Design-Systeme im Build, eines davon tot. [BEHOBEN]**
`tailwindcss`, `@tailwindcss/vite`, `lucide-react`, `class-variance-authority` waren installiert; der Tailwind-Vite-Plugin lief bei jedem Pi-Build – **0 Dateien** in `src/` verwendeten `className="`, 0 importierten `lucide-react`. `components/ui/button.tsx` war eine tote 2-Zeilen-Datei (nur Type-Exports), `lib/utils.ts` dokumentierte Tailwind-Class-Merging, das im Code nirgends verwendet wurde. Entfernt: alle vier Pakete plus `clsx` aus `package.json`, `tailwindcss()`-Plugin aus `vite.config.ts`, beide toten Dateien gelöscht. MUI v5 trägt die UI vollständig.

**B7 — Kein `system`-Theme-Modus.**
[`ThemeContext.tsx`](../../../services/webui-service/src/contexts/ThemeContext.tsx) defaultet hart auf `light`, liest `prefers-color-scheme` nie. Für ein Kinderzimmergerät sinnvoll: abends automatisch dunkel.

**B8 — Google-Fonts-CDN im `<head>`. [BEHOBEN]**
`index.html` lud Roboto von `fonts.googleapis.com` – ein render-blockierender externer Request auf einem Gerät, das offline im Kinderzimmer stehen kann. Bei WLAN-Ausfall stockte der First Paint bis zum Timeout. Umgesetzt: `@fontsource/roboto` (Gewichte 300/400/500/700) lokal installiert und in `main.tsx` importiert, `<link>`/`<preconnect>` aus `index.html` entfernt. Live verifiziert: kein `googleapis.com`-Request mehr im ausgelieferten HTML.

---

## 3. Funktionen optimieren

**C1 — Präkomprimierte Assets werden gebaut und nie ausgeliefert. [BEHOBEN]**
`vite-plugin-compression` erzeugte `.gz` **und** `.br` (11 Dateien in `dist/assets`). Der nginx-Alpine-Build hat `--with-http_gzip_static_module` einkompiliert, aber `nginx.conf` aktivierte nur dynamisches `gzip on` – die vorgebauten Dateien wurden nie ausgeliefert, der Pi komprimierte bei jedem Request neu. Brotli ist im `nginx:alpine`-Image gar nicht einkompiliert; die `.br`-Dateien waren reiner Ballast. Umgesetzt: `gzip_static on;` in `nginx.conf`, Brotli-Plugin aus `vite.config.ts` entfernt. Live verifiziert: Assets werden mit `Content-Encoding: gzip` direkt aus der vorgebauten `.gz`-Datei ausgeliefert.

**C2 — Inkonsistente Datenschicht zwischen den Seiten.**
`PlayerPage` nutzt `@tanstack/react-query` sauber (Caching, `staleTime`, gezielte Invalidierung). [`MediaPage.tsx`](../../../services/webui-service/src/pages/MediaPage.tsx) lädt bei jedem Mount **alles** per `Promise.all` (Playlists + Tracks + Streams + Podcasts + Folders) in lokalen `useState`, ohne Cache, ohne Pagination, mit manueller State-Synchronisierung in ca. 10 Handlern. Das ist die langsamste und fehleranfälligste Seite. `docs/Optimierungen.md` führt „React Query" bereits als offenen Punkt – die Migration von `MediaPage` ist der Schritt, an dem sich das auszahlt.

**C3 — Bundle-Splitting grob.**
`vite.config.ts`: `manualChunks` wirft `@mui/material` + `@mui/icons-material` komplett in einen Chunk; `index` ist 189 KB, `AdminPage` 109 KB (unkomprimiert). Named-Imports der Icons konsequent tree-shaken lassen und `AdminPage` weiter in Lazy-Chunks pro Settings-Gruppe aufteilen.

**C4 — Queue ist read-only.**
Up-Next in `PlayerPage.tsx` zeigt max. 8 Einträge in einem Collapse, ohne Umsortieren, Entfernen oder „jetzt spielen". `@dnd-kit/core` + `@dnd-kit/sortable` sind bereits Dependencies, aber ungenutzt für diesen Zweck.

**C5 — Sleep-Timer nur mit festen Minuten-Presets.**
`SLEEP_PRESETS = [15, 30, 45, 60]` in `PlayerPage.tsx`. Es fehlen „bis Ende des aktuellen Tracks" und „bis Ende der Playlist" – Varianten, die in der Praxis öfter gewünscht werden als feste Minutenwerte.

**C6 — CommandPalette versteckt und mit hartcodierten Labels.**
[`CommandPalette.tsx`](../../../services/webui-service/src/components/common/CommandPalette.tsx): Ctrl/Cmd+K ist gebunden, aber der einzige Einstieg ist ein Blitz-Icon ohne Label im Header. `GROUP_LABELS` ist hart auf Deutsch verdrahtet (`'Wiedergabe'`, `'Navigation'`, …) – bricht die i18n für `en`-Nutzer. Als sichtbares Suchfeld im Header wäre das die globale Suche, die der UI aktuell fehlt.

**C7 — PWA-Manifest unvollständig. [BEHOBEN]**
`vite-plugin-pwa`-Konfiguration in `vite.config.ts` hatte **keine Icons**, und `theme_color: '#ffffff'` widersprach dem `#e65100` in `index.html`. Umgesetzt: vier PNG-Icons (192/512, normal + maskable mit korrektem Safe-Zone-Padding) aus dem bestehenden Favicon-Design generiert, unter `public/icons/` abgelegt, im Manifest referenziert, `theme_color` auf `#e65100` korrigiert.

**C8 — `build:fast` überspringt `tsc` im Docker-Build.**
Im `Dockerfile` bewusst so gewählt (Pi-Buildzeit) – vertretbar als Trade-off, aber `npm run build:check` muss dann verpflichtend vor dem Merge laufen (CI oder Pre-Commit), sonst landen Typfehler unbemerkt im Image.

---

## 4. Funktionen hinzufügen

Die Backend-API ist vollständig von der UI abgedeckt (alle ca. 120 Routen unter `services/backend-service/src/backend_service/api/routes_*.py` gegen `services/webui-service/src/api/` geprüft — auch selten genutzte wie `temperature-history`, `usb/*`, `wifi/*`, `docker-prune`, `factory-reset`). Die Lücke ist keine „ungenutzten Endpoints", sondern fehlende neue Fähigkeiten:

1. **Echter Kind-Modus als eigenständige Ansicht.** `ChildSettingsForm` (Nutzungszeiten, Tageslimit, Volume-Limits) existiert bereits als Konfiguration – aber es gibt keine kindgerechte *Bedienoberfläche*. `/kiosk` ([`KioskPage.tsx`](../../../services/webui-service/src/pages/KioskPage.tsx)) ist der richtige Ansatz, zeigt aber nur Now-Playing. Ausbauen zu einem Cover-Kachel-Grid der Playlists mit Tap-to-Play und großen Buttons, ohne jede destruktive Aktion. Höchster Produktnutzen der gesamten Liste.
2. **Druckvorlage für RFID-Karten.** Aus Tag-Name + zugewiesenem Cover ein Print-Sheet generieren (reines Frontend, `window.print()` + CSS `@page`). Hoher Alltagsnutzen, keine Architekturkosten.
3. **Zuweisung per Drag & Drop.** Playlist/Track auf eine Tag-Karte ziehen. `RfidScanDrawer` liefert den gescannten Tag bereits beim Auflegen; `@dnd-kit` ist als Dependency vorhanden.
4. **Diagnose-Seite, die auch bei kaputtem Backend funktioniert.** Setzt Fix A1 voraus. Service-Grid aus `/system/status` + Docker-Health, plus statischer Fallback-Screen, der bei fehlendem Backend erklärt, welcher Container hängt. `ServiceStatus.tsx` und `ServiceLogsModal.tsx` sind die vorhandenen Bausteine.
5. **Favoriten / zuletzt gespielt** als Schnellstart-Reihe auf dem Player.
6. **Undo statt zweistufigem Bestätigungsdialog** beim Löschen in `MediaPage.tsx` – `ToastContext` kann das tragen (Toast mit „Rückgängig"-Aktion statt Dialog).
7. **Offline-Fallback der PWA.** Service Worker läuft mit `registerType: 'autoUpdate'`, hat aber keine Strategie für `/api`-Requests im Offline-Fall.

---

## 5. Priorisierte Umsetzungsreihenfolge

1. **Entriegelt die Architektur (zuerst): [ERLEDIGT 2026-08-17]** A1 (`resolver` + Variable in `nginx.conf`) → `depends_on: webui` auf `service_started` reduziert. Mit isoliertem Testaufbau (erzwungener Backend-IP-Wechsel) und live am laufenden Stack verifiziert. Voraussetzung für Punkt 4.4 (Diagnose-Seite), macht das System insgesamt resilienter gegen Backend-Rebuilds.
2. **Günstig, hohe Wirkung: [ERLEDIGT 2026-08-17]** C1 (`gzip_static`), B8 (Fonts self-hosted), B5 (Kontrast-Fix), B6 (toten Tailwind-Stack entfernt), C7 (PWA-Icons). Alle Punkte gebaut, live deployt und funktional verifiziert (siehe Abschnitte 2–3 oben für Details je Punkt).
3. **Eigentliches Redesign: [ERLEDIGT 2026-08-17/18]** B1 (BottomNavigation), B2 (Player entschlacken), B3 (Dashboard/Admin trennen), B4 (Settings-Suche) umgesetzt und deployt (manueller Browser-Test steht noch aus, siehe Hinweis in Abschnitt 2.2). Vertiefung offen: die volle 5-Gruppen-Reorganisation aus [Settings-Reorganisation.md](Settings-Reorganisation.md).
4. **Substanz (offen):** C2 (MediaPage auf React Query migrieren) als Voraussetzung für C4 (Queue-Reorder) und Feature 4.1 (Kind-Modus).

---

## 6. Nebenfund: i18n-Fragmente liefen aus dem Ruder [BEHOBEN 2026-08-17]

Beim Rebuild für B1/B2 fiel auf: `scripts/merge-admin-locales.js` regeneriert `public/locales/{de,en}/admin.json` bei **jedem** Docker-Build ausschließlich aus den Fragment-Dateien unter `public/locales/{de,en}/admin/*.json` (der Dockerfile ruft `npm run i18n:merge-admin && npm run build:fast`). Die Fragmente waren gegenüber der committeten `admin.json` unvollständig – 15 Keys pro Sprache fehlten komplett (u. a. `security.title` und `status.title`, beides **ohne** i18n-Fallback im Code verwendet, wären also als roher Key `"security.title"`/`"status.title"` auf der Admin-Seite sichtbar geworden), dazu ~13 Wortlaut-Abweichungen (DE: „Header“ statt „Kopfzeile“, „Repeat“ statt „Wiederholung“ u. a.). Die Fragmente `security.json` und `status.json` fehlten sogar komplett als Dateien.

Das ist kein Nebeneffekt dieser Session, sondern ein latenter Bug, den **jeder** normale Docker-Build dieses Service auslöst – vermutlich entstanden, weil `admin.json` irgendwann direkt bearbeitet wurde, ohne die Quell-Fragmente nachzuziehen. Da mein Rebuild für B1/B2 genau diesen Mechanismus ausgelöst und live deployt hat, wurde er hier direkt behoben statt nur zurückgedreht: alle 15 fehlenden Keys plus Wortlaut-Korrekturen in die passenden Fragment-Dateien zurückgetragen, `security.json`/`status.json` neu angelegt (DE+EN). Regeneration danach 1:1 deckungsgleich mit der vorherigen `admin.json` verifiziert (Python-Diff auf geflachten Keys: 0 fehlend, 0 abweichend – die einzigen „extra“ Treffer waren 5 neue, bereits korrekt in den Fragmenten vorhandene Keys aus dem LED-Glow-Pattern-Feature, die schlicht noch nie gemergt worden waren). Live nochmals verifiziert nach Rebuild + Redeploy.

**Für die Zukunft:** Wer `admin.json` direkt bearbeitet (statt der Fragmente unter `admin/`), verliert die Änderung beim nächsten Build stillschweigend – das ist die eigentliche Fehlerquelle und bleibt bestehen, falls diese Praxis fortgesetzt wird.

## 7. Offene Punkte / nicht geprüft

- UX-Bewertungen in Abschnitt 2.2 (B1–B4, B7) basieren auf Code-/Komponentenstruktur, nicht auf visueller Prüfung im Browser. B5, B6, B8 sowie C1/C7 aus Abschnitt 3 wurden umgesetzt und verifiziert (siehe jeweilige `[BEHOBEN]`-Markierungen).
- A1 war ein **latentes** Risiko (kein zum Analysezeitpunkt beobachteter Fehler, da `backend` und der nginx-DNS-Cache noch auf dieselbe Adresse zeigten) und ist mittlerweile behoben – siehe Abschnitt 1.2.
- Offen: B1–B4, B7 (Redesign-Substanz), C2–C6, C8 (Funktionsoptimierungen) sowie alle Punkte aus Abschnitt 4 (neue Features). Kein Soll-Aufwand/Schätzung pro Punkt enthalten; das ist bewusst eine Bewertung, keine Umsetzungsplanung.
