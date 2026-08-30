# WebUI – Struktur-Review

**Stand:** 2026-08-30, Version 0.1.23
**Grundlage:** Vollstaendige Durchsicht aller 141 Dateien unter
`services/webui-service/src/` (25.257 Zeilen), plus gemessene Duplikatsanalyse.
**Abgrenzung:** [Redesign.md](Redesign.md) bewertet Bedienung und
Container-Topologie und ist in den Phasen 1–3 umgesetzt. Dieses Dokument
betrachtet ausschliesslich die *innere* Struktur: Dateizuschnitt,
Verantwortlichkeiten, Duplikate, in sich unschluessige Ablaeufe. Der Punkt C2
aus Redesign.md ("Datenschicht") taucht hier als S2 wieder auf, jetzt mit
Zahlen.
**Nicht enthalten:** Fehler, die vor dem GoLive behoben gehoeren – die stehen
in der GoLive-Pruefung. Zwei Befunde ueberschneiden sich und sind unten als
solche gekennzeichnet.

---

## 1. Der Befund in Zahlen

| Messung | Wert |
| --- | --- |
| Dateien / Zeilen | 141 / 25.257 |
| Dateien > 400 Zeilen | 13 |
| Dateien > 300 Zeilen | 22 |
| `StreamList` ↔ `PodcastList`, nach Normalisierung der Entitaetsnamen | **619 von 647 Zeilen identisch (95 %)** |
| `StreamList` ↔ `TrackList`, gleiche Normalisierung | 558 von 647 (86 %) |
| Dateien, die `configApi.getGeneral()` selbst aufrufen | 9 |
| Formulare mit identischem Lade-/Speicher-Geruest | 7 (alle 7 erzeugen dieselbe ESLint-Warnung) |
| React Query genutzt in | 2 von 51 Dateien, die Serverdaten laden |
| `<ActionButton>` : rohes `<Button>` : `<IconButton>` | 138 : 60 : 94 |
| Toter Code | 288 Zeilen in 4 Dateien |
| Hoechste `useState`-Dichte je Datei | 28 / 27 / 23 |

Die Messung der Deckungsgleichheit ist reproduzierbar: Entitaetsnamen
(`track`/`stream`/`podcast`, in allen Schreibweisen) auf einen Platzhalter
abbilden, Leerraum normalisieren, `comm -12` ueber die sortierten Zeilen.

---

## 2. S1 – Vier Medienlisten, die eine Komponente sind

`TrackList` (849), `PodcastList` (703), `StreamList` (695) und `PlaylistList`
(516) sind zusammen 2.763 Zeilen. Nach Normalisierung der Entitaetsnamen sind
`StreamList` und `PodcastList` zu 95 % dieselbe Datei. Identisch sind unter
anderem:

- die Konstanten `TREE_WIDTH`, `TREE_COLLAPSED_WIDTH`, `PAGE_SIZE_OPTIONS`,
  `DEFAULT_PAGE_SIZE`, `LIST_ITEM_PR_MOBILE`;
- der Zustand: `search`, `popoverOpen`, `createFolderOpen`, `renameFolder`,
  `move<Entity>`, `menuAnchor`, `menu<Entity>`, `mobileView`,
  `dragging<Entity>Id`, `page` – zwoelf `useState` je Datei;
- `handleSortKey`, `handleSortDirToggle`, `handleNavigateFolder`,
  `handleMenuOpen`, `handleMenuClose`, `handleDragStart`, `handleDragEnd`,
  `handleDrop<Entity>OnFolder`;
- der `MoveMenu`-Popover – bis auf den Namen der Callback-Funktion Zeichen fuer
  Zeichen gleich;
- Filtern, Sortieren, Paginieren, der Umschalter Karten/Liste, das
  Mobil-Popover, die Aktiv-Chips, die Fusszeile mit Seitengroesse und
  Blaetterung, der Split-View mit `FolderTree` links.

`PlaylistList` traegt dieselbe Werkzeugleiste – der Quelltext sagt es selbst:

```tsx
{/* Toolbar – identische Struktur wie TrackList/StreamList/PodcastList */}
```

### Was die Duplikation bereits gekostet hat

Vier Kopien driften auseinander, und das ist hier nicht theoretisch:

- **`PlaylistList` paginiert nicht.** Die anderen drei schon. Eine Mediathek
  mit 300 Playlists rendert alle 300 auf einmal.
- **`PlaylistList` ruft die API selbst auf** (`playlistsApi.create/update/
  delete/uploadCover/getById`), waehrend `TrackList`, `StreamList` und
  `PodcastList` alles per Callback an `MediaPage` hochreichen. Zwei
  Eigentumsmodelle fuer denselben Zweck.
- **`TrackList` hat einen Filter (`file`/`remote`), die anderen nicht** – also
  auch zwei verschiedene Badge-Zaehlungen im Mobil-Knopf (`activeBadgeCount`
  gegen ein hartkodiertes `1`).
- **Der eigentliche Beweis:** `MediaPage.tsx:508`. Die drei
  `onUpdate`-Handler stehen 80 Zeilen auseinander:

  ```tsx
  // Zeile 427, Playlists – richtig
  onUpdate={(pl) => setPlaylists((prev) => prev.map((p) => (p.id === pl.id ? pl : p)))}
  // Zeile 482, Streams – richtig
  onUpdate={(s)  => setStreams((prev)   => prev.map((x) => (x.id === s.id ? s : x)))}
  // Zeile 508, Podcasts – Zweige vertauscht
  onUpdate={(p)  => setPodcasts((prev)  => prev.map((x) => (x.id === p.id ? x : p)))}
  ```

  Wer einen Podcast bearbeitet, sieht die Aenderung an *diesem* Podcast nicht –
  dafuer werden **alle anderen Podcasts der Liste durch den bearbeiteten
  ersetzt**, bis die Seite neu geladen wird. Genau der Fehler, den
  Kopieren-und-Umbenennen erzeugt. *(Auch in der GoLive-Pruefung, dort als
  Blocker.)*

### Vorschlag

Eine generische `MediaLibraryView<T>` in `components/media/library/`, die
Werkzeugleiste, Filter, Sortierung, Blaetterung, Ordnerbaum, Drag & Drop und
das Ueberlaufmenue haelt. Je Entitaet ein Deskriptor statt einer Kopie:

```ts
export interface MediaListDescriptor<T extends MediaFolderItem> {
  dragType: string;                                   // 'application/minabox-track-id'
  sortKeys: ReadonlyArray<SortKeyDef<T>>;             // Schluessel + Label + Vergleich
  filters?: ReadonlyArray<FilterDef<T>>;              // nur Tracks nutzen das heute
  matchesSearch: (item: T, query: string) => boolean;
  play: (item: T) => Promise<void>;
  renderListItem: (item: T) => React.ReactNode;       // nur die Zeile, nicht die Liste
  renderCard: (item: T) => React.ReactNode;
  extraRowActions?: (item: T) => React.ReactNode;     // "zu Playlist" nur bei Tracks
}
```

`FolderTree` zeigt, dass das im Team bereits gemacht wurde und funktioniert: es
hat `MediaFolder`, `MediaFolderItem`, `dragType` und `treeLabel` als Parameter
und bedient alle drei Entitaeten aus einer Datei. Der Baum ist generisch, die
Liste drumherum nicht.

**Erwartung:** 2.763 → rund 950 Zeilen. Vier Sortier-Implementierungen werden
eine; ein Fehler wie der oben ist danach nicht mehr dreimal moeglich.
**Aufwand:** hoch. **Risiko:** mittel – die vier Listen sind der meistgenutzte
Teil der Oberflaeche. Umsetzung schrittweise: erst `StreamList` und
`PodcastList` zusammenlegen (die 95 %), dann `TrackList`, dann `PlaylistList`.

---

## 3. S2 – Zwei Datenschichten nebeneinander

React Query ist in `main.tsx` global konfiguriert (`staleTime` 5 min, 2
Wiederholungen, Neuladen bei Fensterfokus) und wird in genau zwei Dateien
benutzt: `PlayerPage.tsx` und dem `AudioConfigSync` in `App.tsx`. Die
uebrigen 49 datenladenden Komponenten bringen `useState` + `useEffect` +
eigenes `loading`/`error` mit.

Zwei messbare Folgen:

**Dieselben Daten mehrfach geholt.** `MediaPage` laedt beim Betreten sieben
Listen parallel (Playlists, Tracks, Streams, Podcasts und drei Ordner-Listen).
`RfidPage` laedt fuenf davon noch einmal. Die Befehlspalette laedt beim ersten
Oeffnen vier davon ein drittes Mal. Keine der drei sieht die Kopie der anderen.

**`GET /config/general` neunmal implementiert.** Die Aufrufer:
`useSetupStatus`, `i18n/debugMode`, `ChildSettingsForm`,
`SystemMaintenanceSection` und fuenf `ConfigForm`-Formulare. Oeffnet man die
Gruppe „Medien" in den Einstellungen, laufen drei identische Anfragen
gleichzeitig los.

Dazu ein Sonderfall, der ohne Cache besonders teuer ist: `RfidScanDrawer` holt
bei **jedem** Kartenscan die komplette Tag-Liste (`tagsApi.getAll()`), nur um
einen Eintrag zu finden. Das Backend bietet keine Suche nach UID – `getById`
erwartet die numerische Id, nicht die Karten-UID. Entweder Cache oder ein
Backend-Endpunkt `GET /tags/by-uid/{uid}`.

**Vorschlag:** Pro Ressource ein Hook in `src/queries/` (`useTracks()`,
`useStreams()`, `usePodcasts()`, `usePlaylists()`, `useGeneralConfig()`), der
React Query kapselt. Die Komponenten bekommen Daten statt Ladelogik.
`MediaPage` verliert damit den Grossteil seiner 27 `useState`.
**Aufwand:** hoch. **Risiko:** mittel. **Reihenfolge:** nach S1 – wer die
Listen vorher zusammenlegt, muss die Datenschicht nur einmal umstellen.

---

## 4. S3 – Die grossen Dateien und ihr Schnitt

13 Dateien ueberschreiten 400 Zeilen. Bei sechs davon liegt der Grund nicht in
der Menge, sondern darin, dass mehrere Verantwortungen in einer Datei stecken.

### `SystemMaintenanceSection.tsx` – 812 Zeilen, 28 `useState`

Enthaelt fuenf unabhaengige Funktionsbereiche mit je eigenem Zustand, eigener
Fortschrittsanzeige und eigenem Bestaetigungsdialog: Sicherung
(Herunterladen/Wiederherstellen), Versionspruefung und Minabox-Update,
Betriebssystem-Update, Aufraeumen (`docker prune`), Neustart/Herunterfahren/
Werksreset. Ein Blick auf die Zustandsnamen zeigt den Schnitt von selbst –
`restore*`, `update*`, `updateOs*`, `dockerPrune*`, `factoryReset*`.

**Schnitt:** `maintenance/BackupBlock`, `maintenance/UpdateBlock`,
`maintenance/OsUpdateBlock`, `maintenance/CleanupBlock`,
`maintenance/PowerBlock`. Je 100–200 Zeilen, je ein Zustand. Die
Aktualisierungs-Abfrage des Updates (`useEffect` mit `setInterval`, korrekt
aufgeraeumt) wird zu `useUpdateProgress()`.

### `MediaPage.tsx` – 624 Zeilen, 27 `useState`

Traegt vier Ordner-Verwaltungen (Tracks, Streams, Podcasts – jeweils
`create`/`rename`/`delete`/`move`, zwoelf fast gleiche Handler), den
Loeschdialog samt Karten-Abgleich, den Track-Bearbeiten-Dialog und die
Verdrahtung von sechs weiteren Dialogen. Nach S1 und S2 bleibt davon die
Tab-Auswahl uebrig; bis dahin: die zwoelf Ordner-Handler in einen Hook
`useFolderActions(api, setItems)` zusammenfassen – sie unterscheiden sich nur
im API-Objekt.

### `NetworkPanel.tsx` – 395 Zeilen, 23 `useState`

Vier unabhaengige Themen in einer Datei: WLAN suchen und verbinden, Hotspot,
feste IP-Adresse, Geraetename. Kein gemeinsamer Zustand ausser `loading`.
**Schnitt:** `network/WifiBlock`, `network/HotspotBlock`,
`network/IPv4Block`, `network/HostnameBlock` – jeweils unter 120 Zeilen. Der
`SettingsBlock` dafuer existiert bereits.

### `ButtonConfigPanel.tsx` (589) und `LEDConfigPanel.tsx` (541)

Zwei Dateien mit identischem Aufbau: Laden, Liste als Karten (Mobil) *und* als
Tabelle (Desktop), zweistufiger Anlege-/Bearbeiten-Dialog mit eigener
Validierung, Loeschdialog, Testdialog. Auch hier ist die Doppelung sichtbar –
`renderBtnActions` und `renderLedActions` unterscheiden sich in einem Symbol.

**Schnitt:** ein gemeinsames `admin/hardware/DeviceTable<T>` (Karten + Tabelle
+ Zeilenaktionen), darunter `ButtonEditDialog` und `LedEditDialog` als eigene
Dateien. Die Validierung von `ButtonConfigPanel` (`missingPins`,
`isStep0Valid`, `isStep1Valid`) gehoert in eine reine Funktion – sie ist die
einzige Stelle im Projekt, die sich testen liesse, ohne React zu mounten.

### `PlayerPage.tsx` – 633 Zeilen

Hier ist der Schnitt kleiner: das Ueberlaufmenue, der Einschlaf-Popover und der
Ausgabegeraete-Dialog sind je ein in sich geschlossener Block und koennen als
`player/PlayerOverflowMenu`, `player/SleepTimerMenu`, `player/OutputDeviceDialog`
heraus. Der Einschlaf-Countdown (`startDisplayCountdown`/`stopDisplayCountdown`
plus Ref und Intervall) wird zu `useSleepCountdown()`.

### Gegenbeispiele, die so bleiben sollten

`SoundTroubleshootDialog` (323) ist ein benannter Zustandsautomat
(`idle → asking → fixed | escalate_restart | escalate_human`) und liest sich
von oben nach unten. `DebugExportDialog` (487) ist gross, weil der Inhalt gross
ist – ein Block je Exportteil, alle gleich aufgebaut. `MediaImportDialog` (474)
haelt eine echte Zustandsmaschine mit Abfrageschleife. Diese drei sind kein
Zerlegungsfall.

---

## 5. S4 – Sieben Formulare, ein Geruest

`SleepTimerSettingsForm`, `UploadLimitForm`, `MediaImportDomainsForm`,
`AdvancedSettingsForm`, `PlaybackSettingsForm`, `RFIDConfigForm` und
`AudioConfigForm` haben denselben Rumpf:

```tsx
const { t } = useTranslation('admin');
const { showSuccess } = useToast();
const { saving, error, setError, run } = useFormState();
const [value, setValue] = useState<T | null>(null);

useEffect(() => {
  configApi.getGeneral()
    .then((d) => setValue((d as GeneralConfig).feld ?? STANDARD))
    .catch(() => setError(t('load_error')));
}, []);                       // ← erzeugt in allen sieben dieselbe ESLint-Warnung

const handleSave = () => run(async () => {
  if (value === null) return;
  await configApi.updateGeneral({ feld: value });
  setError(null);
  showSuccess(t('general.save_success'));
});

if (value === null) return null;
```

Das Eigentliche – ein Eingabefeld – sind zwischen 8 und 30 Zeilen. Der Rest ist
in sieben Dateien wortgleich, samt der gleichen ESLint-Warnung.

**Vorschlag:** ein Hook, der auch S2 mit erledigt:

```ts
const { value, setValue, save, saving, error } =
  useGeneralConfigField('sleep_timer_minutes', 30);
```

Intern React Query, also *eine* Anfrage fuer alle Formulare einer Gruppe statt
einer pro Formular. Die sieben Formulare schrumpfen auf ihr Feld plus
Speicherknopf. **Aufwand:** gering. **Risiko:** gering. **Empfehlung:** als
erster Schritt – kleiner Eingriff, sofort sichtbarer Nutzen, und der Hook ist
die Blaupause fuer S2.

---

## 6. S5 – Ablaeufe, die in sich nicht schluessig sind

Sieben Stellen, an denen der Code etwas anderes tut, als er ankuendigt.

### 6.1 „Speichern" im Dialog speichert nicht

`ButtonConfigPanel` und `LEDConfigPanel`: der Speichern-Knopf im
Bearbeiten-Dialog ruft `handleSaveButtonDialog` bzw. `handleSaveLedDialog` –
beide schreiben ausschliesslich in den lokalen `config`-Zustand. Zum Server
geht es erst ueber den *zweiten* Speichern-Knopf in der Werkzeugleiste
darueber. Dasselbe gilt fuer den Ein/Aus-Schalter je Geraet
(`handleToggleEnabled`) und fuers Loeschen.

Wer einen Taster anlegt, den Dialog mit „Speichern" schliesst und die Seite
verlaesst, hat nichts gespeichert – ohne Warnung.

**Vorschlag:** den Dialog-Knopf „Uebernehmen" nennen und den ungespeicherten
Stand sichtbar machen (Hinweisleiste „Nicht gespeicherte Aenderungen" mit dem
Speichern-Knopf darin), oder der Dialog schreibt direkt. Die zweite Variante
passt zu allen anderen Einstellungsformularen.

### 6.2 Cover entfernen schliesst den Bearbeiten-Dialog

`StreamEditDialog.handleRemoveCover` ruft nach dem Loeschen `onSuccess(updated)`.
`StreamList:691` verdrahtet das als
`onSuccess={(updated) => { onUpdate(updated); setStreamToEdit(null); }}` – der
Dialog geht zu. Wer den Titel geaendert und *dann* das Cover entfernt hat,
verliert die Titelaenderung. Identisch bei `PodcastEditDialog` /
`PodcastList:699`.

**Ursache:** `onSuccess` bedeutet an einer Stelle „fertig, schliess mich" und an
der anderen „hier ist ein aktualisierter Datensatz". Zwei Callbacks
(`onSaved` und `onEntityChanged`) loesen das.

### 6.3 Falsche Uebersetzungsschluessel – der Nutzer liest etwas Unpassendes

| Ort | Was passiert ist | Was angezeigt wird |
| --- | --- | --- |
| `UsbImportPanel.tsx:54` | USB-Import fehlgeschlagen | „Logs nicht verfuegbar. Auf dem Host: `docker logs minabox-<service>`" |
| `UsbImportPanel.tsx:67` | USB-Auswerfen fehlgeschlagen | dieselbe Logs-Meldung |
| `BoardLedsToggle.tsx:32` | Board-LED umschalten fehlgeschlagen | dieselbe Logs-Meldung |
| `SecurityStep.tsx:55` | Passwort setzen fehlgeschlagen | „Der Test ist fehlgeschlagen. Die Komponente meldet sich nicht." |
| `AudioStep.tsx:77` | Audio-Einstellung speichern fehlgeschlagen | dieselbe Hardware-Test-Meldung |
| `SystemMaintenanceSection.tsx:232` | Sicherung **erfolgreich** heruntergeladen | Erfolgstext der *Wiederherstellung* |

`translateApiError()` existiert und wird an 14 Stellen richtig benutzt. Diese
sechs greifen daran vorbei.

### 6.4 Abfrageschleife ohne Aufraeumen

`MediaPathForm.tsx:79`: `runMoveAndRestart` startet ein `setInterval`, das nur
aus seiner eigenen Rueckruffunktion beendet wird. Verlaesst der Nutzer waehrend
des Umzugs die Einstellungsgruppe, wird die Komponente abgebaut – das Intervall
laeuft weiter, fragt jede Sekunde `getMoveStatus()` ab und setzt Zustand auf
einer nicht mehr vorhandenen Komponente. Kein `useEffect`, kein Ref, kein
Abbruch.

Der richtige Weg steht im selben Projekt: `SystemMaintenanceSection.tsx:284`
loest dieselbe Aufgabe mit `useEffect` + `active`-Flag + `clearInterval` in der
Aufraeumfunktion.

### 6.5 Blob-URLs im JSX

Sechs Stellen (`MediaPage:576`, `RemoteTrackDialog:84`, `PodcastDialog:71`,
`StreamDialog:74`, `AddToPlaylistDialog:191`, `PlaylistList:476`) rufen
`URL.createObjectURL(file)` direkt im JSX auf. Jeder Renderdurchlauf erzeugt
eine neue URL, keine wird je freigegeben. *(Auch in der GoLive-Pruefung.)*
Ein `useObjectUrl(file)`-Hook loest alle sechs.

### 6.6 Vier Zustaende fuer eine Frage

`BluetoothSection` haelt `pairing`, `connecting`, `disconnecting` und
`removing` – jeweils die Adresse des betroffenen Geraets – und fuehrt sie in
`busy(addr)` wieder zusammen. Ein `busy: { address, action } | null` sagt
dasselbe und macht die Absicht sichtbar.

### 6.7 Doppelte Geraeteabfrage

`AudioConfigForm` laedt die Ausgabegeraete in einem `useEffect` **und** in
`handleRefreshDevices` – sechs identische Zeilen zweimal. Das `useEffect`
haengt zudem an `[config]`, sodass jedes Speichern die Geraeteliste neu holt.

---

## 7. S6 – Toter Code

| Datei | Zeilen | Status |
| --- | --- | --- |
| `components/media/FolderCard.tsx` | 92 | nur von `FolderList` benutzt |
| `components/media/FolderBreadcrumb.tsx` | 80 | nirgends importiert |
| `hooks/useApi.ts` (`useApi`, `useAsyncAction`) | 69 | nirgends importiert |
| `components/media/FolderList.tsx` | 47 | nirgends importiert |
| **Summe** | **288** | |

Dazu drei nie aufgerufene API-Funktionen: `playlistsApi.reorderTracks`,
`playlistsApi.removeTrack`, `resetAuth`. `PlaylistTracksDialog` sortiert ueber
`update({ track_ids })` statt ueber `reorderTracks` – eine der beiden Wege
gehoert weg.

Und ein Ausblick, der nie eingetreten ist: `AddToPlaylistDialog` nimmt
`track: Track | Stream`, wird aber ausschliesslich mit `Track` aufgerufen. Der
`Stream`-Fall wuerde die Stream-Id als Track-Id in die Playlist schreiben.
Union entfernen.

---

## 8. S7 – Der Baukasten wird nur teilweise benutzt

Die gemeinsamen Bausteine sind da und gut gemacht. Sie werden nur nicht
durchgehalten.

**`ActionButton`.** Der Kopfkommentar sagt „Single button component for the
entire WebUI". Tatsaechlich: 138 `<ActionButton>`, 60 rohe `<Button>`, 94
`<IconButton>`. Ganze Bereiche liegen daneben – `ButtonConfigPanel` (16 rohe
Knoepfe), `LEDConfigPanel` (8), der komplette Einrichtungsassistent (10), fuenf
Medien-Dialoge. `actionType="icon"` existiert, wird aber von keinem der 94
`IconButton` benutzt. Entweder den Anspruch einloesen oder den Kommentar
korrigieren; heute stimmt beides nicht.

**`SettingsBlock`.** Der Kommentar beschreibt, dass diese Komponente die dritte
Ebene der Einstellungsseite vereinheitlicht, weil es vorher vier Varianten gab.
Sechs von 21 Panels benutzen sie nicht: `AdvancedSettingsForm`,
`MediaPathForm`, `RFIDConfigForm`, `UsbImportPanel`, `LEDConfigPanel`,
`ButtonConfigPanel`. Die alte Uneinheitlichkeit ist also nicht beseitigt,
sondern halbiert.

**Zweimal dieselbe kleine Komponente.** `StatTile` steht in
`DashboardOverview.tsx:32` und in `SystemStatus.tsx:51` (letzteres mit
`onClick`/`title` erweitert). `TabPanel` steht in `DashboardPage.tsx:21` und
`MediaPage.tsx:60`, wortgleich. Beide gehoeren nach `components/common/`.

**Zwei Namensschemata im `localStorage`.** `minabox-theme-mode`,
`minabox-theme-color`, `minabox-font-scale`, `minabox-language`,
`minabox-setup-seen` mit Bindestrich – `minabox.prefs`, `minabox.capabilities`
mit Punkt. Eine Migration kostet ein paar Zeilen, spaeter mehr.

**Sechs nicht uebersetzte Texte im Quelltext.** `'Laden fehlgeschlagen'`
(`ButtonConfigPanel:78`, `LEDConfigPanel:74`, `DisplayConfigPanel:38`),
`'Status konnte nicht geladen werden'` (`SystemStatus:131`),
`` `${count}× neu gestartet` `` (`ServiceStatus:60`) – dazu die vier
Fehlerbildschirm-Texte aus der GoLive-Pruefung.

---

## 9. Reihenfolge

Von unten nach oben – jeder Schritt macht den naechsten kleiner.

| # | Schritt | Aufwand | Risiko | Zeilen |
| --- | --- | --- | --- | --- |
| 1 | S6 toter Code weg, S7 `StatTile`/`TabPanel` nach `common/`, deutsche Reste uebersetzen | gering | keins | −300 |
| 2 | S5.3 falsche Uebersetzungsschluessel, S5.4 Intervall-Leak, S5.5 `useObjectUrl` | gering | gering | ±0 |
| 3 | S4 `useGeneralConfigField` – sieben Formulare auf ihren Inhalt reduzieren | gering | gering | −250 |
| 4 | S5.1 „Speichern"-Semantik in `ButtonConfigPanel`/`LEDConfigPanel` klaeren | mittel | gering | ±0 |
| 5 | S3 `SystemMaintenanceSection` und `NetworkPanel` zerlegen | mittel | gering | ±0 |
| 6 | S1 `MediaLibraryView` – erst Stream+Podcast, dann Track, dann Playlist | hoch | mittel | −1.800 |
| 7 | S2 Datenschicht auf React Query (`src/queries/`) | hoch | mittel | −400 |

Schritte 1–3 sind eine Sitzung und beruehren die Bedienung nicht. Schritt 6 ist
der grosse Posten und sollte nicht vor dem GoLive beginnen: die vier Listen
sind der meistgenutzte Teil der Oberflaeche, und sie funktionieren heute – bis
auf `MediaPage:508`, was ein Einzeiler ist.
