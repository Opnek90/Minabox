# Einstellungen (`/admin`) – Reorganisations-Konzept

**Status:** **Umgesetzt und live deployt (2026-08-18).** Der Schnitt wurde nach Nutzer-Feedback von „Zustand vs. Konfiguration" auf „Elternalltag vs. Einrichtung" umgestellt – siehe Abschnitt 2.
**Erstellt:** 2026-08-17, zuletzt aktualisiert: 2026-08-18
**Grundlage:** Löst B3 ("Zwei konkurrierende Übersichtsbereiche") und B4 ("Admin ist eine Formularwand ohne Suche") aus [Redesign.md](Redesign.md#22-strukturelle-schwächen) auf. Ergänzt [Architecture.md](Architecture.md).

---

## 1. Das eigentliche Problem

Die aktuelle Gruppierung in [`AdminPage.tsx`](../../../services/webui-service/src/pages/AdminPage.tsx) (4 Gruppen, 12 Sections) ist nicht nach *Absicht* sortiert, sondern danach, wo eine Einstellung technisch im Backend liegt. Drei konkrete Folgen:

1. **Betrieb und Konfiguration sind vermischt.** Die Gruppe „System & Sicherheit" enthält gleichzeitig reine Diagnose (Host-Status, Syslog, Docker-Logs) und einmalige Konfigurationsentscheidungen (Netzwerk, Backup, Werksreset). Das überschneidet sich inhaltlich mit `/dashboard`, das ebenfalls Betriebszustand zeigt (B3).
2. **Falsche Nachbarschaft einzelner Sections.**
   - „Design" (Sprache, Theme, Akzentfarbe, Logo – [`DesignSettingsForm.tsx`](../../../services/webui-service/src/components/admin/ConfigForm/DesignSettingsForm.tsx)) steckt in der Gruppe „Kind & Profil", hat aber nichts mit dem Kind zu tun.
   - „Steuerung & Wiedergabe" ([`ControlSettingsForm.tsx`](../../../services/webui-service/src/components/admin/ConfigForm/ControlSettingsForm.tsx)) mischt RFID-Wiedergabeverhalten (Stop/Resume bei Tag-Entfernen – eine Wiedergabe-Einstellung) mit Bedtime-Fade (eine Kinderschutz-Einstellung) in einer Section, sitzt aber komplett in „Kind & Profil".
3. ~~**Tageslimit ist unerreichbar.**~~ **[KORRIGIERT 2026-08-18]** Falsch verifiziert – `ChildSettingsForm.tsx` (aktiv, unter Admin → Kind & Profil) hat bereits einen vollständigen Daily-Limit-Toggle + Minuten-Slider (Zeilen 156–184). `ParentSettingsForm.tsx` war ein unbenutzter, überholter Duplikat-Entwurf derselben Funktion – als toter Code entfernt, keine Funktionslücke.

Keine Suche über 12+ Sections zu haben (B4) verschärft das: Wer nicht weiß, in welcher der vier Gruppen eine Option liegt, muss alle durchklicken.

---


## 2. Die Achse, nach der geschnitten wird

Der erste Entwurf trennte nach **„Zustand oder Konfiguration?"**. Das ist eine Entwicklerfrage – sie erklärt, wie Daten im Backend liegen, aber nicht, was ein Elternteil gerade vorhat. Ergebnis war eine Struktur, in der die Kindersicherung bei den technischen Einstellungen lag und Docker-Container-Logs im Eltern-Dashboard.

Maßgeblich ist stattdessen die **Rolle und Häufigkeit**:

> **Was Eltern regelmäßig tun → Eltern-Dashboard.** Nachsehen wie lange gehört wurde, Zeiten und Limits anpassen, Verlauf prüfen. Mobil, oft, nebenbei.
>
> **Was einmalig eingerichtet wird → Einstellungen.** Lautsprecher, Knöpfe, WLAN, Updates, Passwörter. Selten, bewusst, gerne am Rechner.

Diagnose (Host-Status, Container, Protokolle) ist damit *keine* Elternsache: sie steht ganz unten in den Einstellungen unter „Technische Details" – auffindbar wenn etwas klemmt, sonst nicht im Weg.

**Nachtrag 2026-08-19 – warum Abspielverhalten nicht ins Dashboard wandert.** Der Menüpunkt „Abspielen & Einschlafen" lag unter der Gruppe *Ton* und war dort schlecht auffindbar: „Ton" heißt Klang (Lautsprecher, Bluetooth), nicht Verhalten. Naheliegend wäre gewesen, ihn ins Eltern-Dashboard zu verschieben, weil er die Hauptfunktion der Box betrifft. Das wäre aber ein Rückfall hinter genau diese Achse: Was am Ende einer Karte passiert, stellt man *einmal* ein, nicht im Alltag – anders als Zeiten, Limits und Auswertung. Statt der Verschiebung wurde das falsche Dach ersetzt: „Abspielen" ist jetzt eine eigene, erste Gruppe gleichrangig neben „Ton". Der Zuschnitt liegt weiterhin allein in `settingsIndex.ts`, die Änderung war entsprechend klein.

Zweite Leitlinie: **Bezeichnungen in Alltagssprache.** Fachbegriffe nur, wo es keine Alternative gibt (WLAN, Bluetooth, RFID, MQTT). Aus „LEDs" wird „Lichter", aus „Buttons" „Knöpfe & Drehregler", aus „Audio-Einstellungen" „Lautsprecher & Kopfhörer".

---

## 3. Eltern-Dashboard (`/dashboard`)

| Tab | Inhalt |
|---|---|
| Übersicht | Heute gehört, gesamt, verbleibende Minuten, Zähler für Tags/Tracks/Playlists |
| **Zeit & Regeln** | Nutzungszeiten je Wochentag, Tageslimit, Lautstärke-Grenzen, Einschlaf-Fade |
| Auswertung | Hördauer pro Tag, Top-Tags, Top-Playlists, Heatmap |
| Verlauf | Welche Karte wann aufgelegt wurde |

„Zeit & Regeln" steht bewusst direkt neben der Übersicht: dort werden die verbleibenden Minuten angezeigt, hier wird das Limit gesetzt, das sie erzeugt. Vorher lagen Anzeige und Regel in zwei verschiedenen Hauptbereichen.

---

## 4. Einstellungen (`/admin`)

Neun Gruppen, absteigend nach Alltagsrelevanz. Auf dem Mobilgerät ist jede Gruppe eine Accordion-Zeile – eine Liste aus verständlichen Wörtern statt einer Formularwand.

| Gruppe | Sections | Inhalt |
|---|---|---|
| **Abspielen** | Beim Auflegen einer Karte · Einschlafen | Verhalten beim Abnehmen/erneuten Auflegen, Verhalten am Ende des Inhalts samt Schleifen-Sperre · Einschlaf-Timer |
| **Ton** | Lautsprecher & Kopfhörer | Ausgabegerät, Bluetooth, Ein-/Ausblenden |
| **Aussehen** | Sprache & Farben | Sprache, Hell/Dunkel, Akzentfarbe, eigenes Logo |
| **Medien** | Musik-Ordner · Upload-Limit · Erlaubte Import-Quellen · Vom USB-Stick übertragen | Speicherort der Musik, maximale Upload-Größe, Domain-Allowlist für den URL-Import, USB-Import |
| **Angeschlossene Geräte** | Kartenleser · Knöpfe & Drehregler · Lichter · Display am Gerät | RFID-Leser, GPIO-Knöpfe, LEDs inkl. Status-Lichter des Pi, OLED |
| **Netzwerk** | WLAN & Adresse | WLAN, Hotspot, Gerätename, DHCP/feste IP |
| **Wartung** | Updates & Sicherung · Ersteinrichtungs-Assistent | Updates, Backup, Aufräumen, Neustart, Zurücksetzen · Onboarding erneut durchlaufen |
| **Sicherheit** | Passwörter & Zugriff | SSH, System-Passwort, geschützte Bereiche |
| **Technische Details** | Erweiterte Einstellungen · Status & Protokolle | Geräte-ID, Log-Level, MQTT · Host-Status, Container, Syslog |

**Nachtrag 2026-08-27 – „Medien" als eigene Gruppe (Issue #133).** Upload-Limit und die Domain-Allowlist für den URL-Import kamen nachträglich dazu und wurden mangels besserem Ort unter „Wartung" abgelegt, wo sie – neben Musik-Ordner und USB-Import – einen faktischen Medien-Block bildeten, den die Überschrift „Wartung" verdeckte. Die vier Sections bilden jetzt die Gruppe „Medien" (zwischen „Aussehen" und „Angeschlossene Geräte"). „Wartung" enthält nur noch echte Wartung; der ebenfalls nachträglich unter „Technische Details" gelandete Neustart des Ersteinrichtungs-Assistenten sitzt jetzt dort neben Sicherung und Werksreset. Reiner `settingsIndex.ts`-Zuschnitt plus ein neuer Gruppen-Key/-Icon, keine Komponenten berührt.

### Komponenten-Zuschnitt

Damit die Gruppen nicht nur Überschriften sind, wurden drei Sammel-Komponenten aufgeteilt:

| Vorher | Nachher |
|---|---|
| `SystemPanel` (WLAN + IP + Hostname + USB + Stealth + Wartung in einem Block) | `NetworkPanel` (Netzwerk) · `UsbImportPanel` (Wartung) · `BoardLedsToggle` (Lichter) · `SystemMaintenanceSection` (Wartung, unverändert) |
| `GeneralSettingsForm` (Musik-Ordner + Geräte-ID + Log-Level + MQTT) | `MediaPathForm` (Wartung) · `AdvancedSettingsForm` (Technische Details) |
| `ControlSettingsForm` (RFID-Verhalten + Sleep-Timer + Einschlaf-Fade) | `PlaybackSettingsForm` (Abspielen) · `SleepTimerSettingsForm` (Abspielen) · Einschlaf-Fade in `ChildSettingsForm` (Eltern-Dashboard) |

`ChildSettingsForm` ist nach `components/dashboard/` gewandert, `SystemStatus`/`ServiceStatus`/`ServiceLogsModal`/`SyslogModal` zurück nach `components/admin/` – jede Datei liegt jetzt in dem Ordner, in dem sie auch gerendert wird.

---

## 5. Suche

- Suchfeld über der Einstellungsseite matcht Gruppenname, Section-Titel **und die Labels der enthaltenen Felder** (`searchKeys` in [`settingsIndex.ts`](../../../services/webui-service/src/config/settingsIndex.ts), über i18n – funktioniert in DE und EN ohne eigene Wortlisten).
- Treffer sind eine **Sprungliste**, keine ausgeklappten Formulare: eine kurze Eingabe trifft fast alle Sections, und die gleichzeitig zu mounten würde auf dem Pi vierzehn Panels samt API-Calls auf einmal starten. Klick öffnet die Gruppe, scrollt hin und hebt die Section kurz hervor.
- Die CommandPalette (Ctrl/Cmd+K) nutzt denselben Index und springt per `/admin?section=<key>` direkt in eine Section – eine Suchimplementierung statt zweier. Einstieg ist jetzt ein sichtbares Suchfeld im Header statt eines Blitz-Icons ohne Label.

---

## 6. i18n: Fragmente und Merge-Skript abgeschafft

**Vorher:** 16 Fragmentdateien je Sprache unter `public/locales/{de,en}/admin/`, aus denen `scripts/merge-admin-locales.js` bei *jedem* Build `admin.json` neu erzeugte – wobei die generierte `admin.json` zusätzlich im Git lag. Wer sie direkt bearbeitete, verlor die Änderung beim nächsten Build stillschweigend. Genau das ist schon einmal passiert (siehe [Redesign.md Abschnitt 6](Redesign.md)).

**Jetzt:** eine handgepflegte `admin.json` je Sprache. Entfallen sind 32 Fragmentdateien, `scripts/merge-admin-locales.js`, das Gegenstück `scripts/split-admin-locales.js`, die npm-Skripte `i18n:merge-admin` und `predev` sowie der Merge-Schritt im `Dockerfile`. Es gibt kein Generat mehr und damit keine Frage, welche Datei die Quelle ist.

Die Key-*Pfade* wurden bewusst nicht umbenannt (nur die Werte) – das hätte einen Eingriff in rund 15 Komponenten bedeutet, ohne für Nutzer etwas zu ändern. Zwei tote Blöcke sind entfallen: `tabs.*` (durch `groups.*` ersetzt) und `child.*` (Section lebt jetzt im Dashboard).

---

## 7. Verifikation

`tsc --noEmit`: 13 Fehler, identisch zur Baseline auf HEAD (per separatem Worktree gegengeprüft) – keine neuen, keine in den geänderten Dateien. ESLint: 5 Bestandsfehler, keiner neu. `build:fast` erfolgreich ohne Merge-Schritt, Container neu gebaut und deployt, ausgelieferte `admin.json`/`common.json` sowie alle 7 Gruppen- und 14 Section-Keys im Bundle geprüft.

**Nicht geprüft:** manueller Klick-Test im Browser (Accordion-Bedienung auf dem Mobilgerät, Sprungliste, Ctrl+K, die aufgeteilten Panels NetworkPanel/UsbImportPanel/MediaPathForm/AdvancedSettingsForm gegen echte Hardware). Dieselbe Einschränkung wie in [Redesign.md Abschnitt 2.2](Redesign.md).
