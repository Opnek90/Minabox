# Optimierungsvorschläge für das Minabox WebUI

Diese Datei dokumentiert potenzielle Verbesserungen und Architektur-Optimierungen für das WebUI-Frontend des Minabox-Projekts.

## 1. Performance: WebSocket State Management
**Aktuelles Problem:** 
Im `WebSocketContext` wird `lastMessage` als State gespeichert und im Context-Provider bereitgestellt. Jedes Mal, wenn eine neue WebSocket-Nachricht eingeht, ändert sich das Context-Objekt. Das führt dazu, dass **alle** Komponenten, die `useWebSocket()` verwenden (z.B. für `isConnected`), bei jeder einzelnen Nachricht komplett neu gerendert werden, selbst wenn sie die Nachricht gar nicht benötigen.
**Lösung:**
* **Pub/Sub-Muster (Event Emitter):** Entferne `lastMessage` aus dem React-Context. Nutze stattdessen ein Event-Emitter-Pattern (z.B. `mitt` oder native `EventTarget`), bei dem sich Komponenten gezielt auf bestimmte Nachrichten-Typen subscriben können (`useWebSocketEvent('tag_not_found', callback)`).
* **Zustand:** Alternativ kann eine leichtgewichtige State-Library wie `zustand` eingesetzt werden, die ein "Selektieren" von States ohne Re-Rendering des gesamten Baums ermöglicht.

## 2. Datenbeschaffung (Data Fetching) & Caching
**Aktuelles Problem:**
Die API-Calls im `api/`-Ordner (`audio.ts`, `system.ts`, etc.) deuten darauf hin, dass asynchrone Daten klassisch via `useEffect` und lokalem State (`useState`) in den Komponenten geladen werden. Dies erfordert viel Boilerplate-Code für Loading/Error-States und ist anfällig für Race-Conditions.
**Lösung:**
* **React Query (@tanstack/react-query) oder SWR:** Die Einführung einer dieser Bibliotheken reduziert den Boilerplate-Code drastisch. Es bietet out-of-the-box Caching, automatisches Re-Fetching (z.B. Window-Focus), Optimistic Updates und vereinfacht das State-Management für asynchrone Daten enorm.

## 3. PWA (Progressive Web App) & Build-Optimierungen
**Aktuelles Problem:**
Das WebUI ist eine klassische SPA (Single Page Application). Da die Minabox oft über Smartphones oder Tablets im Heimnetzwerk gesteuert wird, fehlt die Möglichkeit, die App nativ wie eine echte App auf dem Homescreen zu installieren.
**Lösung:**
* **vite-plugin-pwa:** Füge dieses Plugin in der `vite.config.ts` hinzu, um einen Service Worker und ein Web-App-Manifest zu generieren. Dadurch lässt sich das WebUI auf iOS/Android als App installieren, die im Vollbildmodus ohne Browser-UI läuft.
* **Kompression:** Da die Minabox (vermutlich ein Raspberry Pi o.ä.) begrenzte Ressourcen hat, kann das `vite-plugin-compression` (Brotli/Gzip) genutzt werden, um die ausgelieferten Bundles vorab zu verkleinern und das Backend (z.B. NGINX) zu entlasten.

## 4. MUI Bundle Size und Rendering
**Aktuelles Problem:**
In der `vite.config.ts` sind `manualChunks` für MUI konfiguriert, was gut ist. Allerdings kann die exzessive Nutzung von MUI-Komponenten in großen Listen (z.B. Media-Listen, Tracks) zu Performance-Engpässen führen.
**Lösung:**
* **Virtualisierung:** Falls die Listen für Tracks oder Verzeichnisse sehr lang werden können, sollte `react-virtuoso` oder `@tanstack/react-virtual` eingesetzt werden, um nur die sichtbaren Elemente im DOM zu rendern.
* **Memoization:** Achte bei komplexen MUI-Komponenten auf den gezielten Einsatz von `React.memo` sowie `useMemo` und `useCallback` für Event-Handler, die an Child-Komponenten weitergereicht werden.

## 5. Tooling & Maintenance
* **ESLint Update:** Das Projekt nutzt aktuell `eslint ^8.57.0`. Ein Upgrade auf ESLint 9 (mit dem neuen Flat Config Format) bereitet das Projekt auf die Zukunft vor, da v8 sein End-of-Life erreicht.
* **React 19 Readiness:** React 18.3.1 ist bereits installiert, was hervorragend ist (es bereitet auf React 19 vor). Perspektivisch können Features wie der React Compiler (React 19) ausprobiert werden, was manuelles Memoizing (`useMemo`/`useCallback`) größtenteils überflüssig machen würde.
