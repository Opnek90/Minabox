# Ersteinrichtungs-Assistent (WebUI)

Stand: 2026-08-20 — umgesetzt, auf echter Hardware noch nicht durchgespielt.

## Warum

`install.sh` bringt den Stack ans Laufen, mehr nicht. Nach dem ersten Aufruf
der Oberflaeche steht man auf dem Player und muss sich alles Weitere selbst
zusammensuchen. Es gibt heute keinerlei Ersteinrichtung: kein `first_run`-Flag,
keine Onboarding-Route, keinen Begruessungsschritt.

Ein Punkt daran ist mehr als Bequemlichkeit. In
[`routes_auth.py:59`](../../../services/backend-service/src/backend_service/api/routes_auth.py)
wird `auth_enabled` daraus abgeleitet, ob ueberhaupt ein Passwort-Hash
existiert:

```python
auth_enabled = bool((settings.get("web_password_hash") or "").strip())
```

Auf einer frischen Installation gibt es keinen. **Jede neu aufgesetzte Box ist
im gesamten Heimnetz ungeschuetzt offen**, bis jemand von sich aus ein Passwort
setzt — inklusive Medienverwaltung und Eltern-Dashboard. Genau das soll der
Assistent auffangen.

Der zweite Punkt: `install.sh` kann Hardware nur *einrichten*, nicht
*ausprobieren*. Ein Testton, eine blinkende LED, ein gescannter Tag — das geht
im Browser und im Terminal nicht. CLI- und WebUI-Assistent ergaenzen sich also,
sie ueberschneiden sich nicht.

## Entscheidungen

| Thema | Entscheidung |
|---|---|
| Schritte | Sprache, Zugriffsschutz, Audio mit Testton, Hardware bestaetigen, erste Inhalte |
| Verbindlichkeit | Startet automatisch, jederzeit abbrechbar; danach bleibt ein Hinweis, bis abgeschlossen |
| Wiederholbar | Ja, ueber einen Eintrag in den Einstellungen, mit vorausgefuellten Werten |

## Was bereits existiert

Der groesste Teil der Bausteine ist da. Der Assistent soll sie orchestrieren,
nicht neu bauen.

| Baustein | Wo | Nutzung im Assistenten |
|---|---|---|
| `Stepper`-Muster | [`ButtonConfigPanel.tsx:372`](../../../services/webui-service/src/components/admin/ButtonConfigPanel.tsx), [`LEDConfigPanel.tsx:350`](../../../services/webui-service/src/components/admin/LEDConfigPanel.tsx) | Schrittnavigation |
| Passwort setzen / Bereiche schuetzen | `routes_auth.py` | Schritt 2 |
| Sink-Liste, Ausgang wechseln | `GET /api/v1/audio/devices`, `POST /api/v1/audio/switch-device` | Schritt 3 |
| Lautstaerkegrenzen | `GET/PUT /api/v1/config/audio` | Schritt 3 |
| LED-Test | `POST /api/v1/config/leds/test` | Schritt 4 |
| Tastendruck live | WS-Event `button_raw_event`, via `useWebSocketEvent` | Schritt 4 |
| RFID-Lernmodus | `POST /api/v1/rfid/learning-mode`, WS `rfid_scanned_learning` | Schritt 5 |
| Medien-Upload | `MediaPage` | Schritt 5 |
| Dienstzustand | WS-Event `service_status` | Schritt 4 (welche Hardware laeuft ueberhaupt) |
| Einstellungs-Index | [`settingsIndex.ts`](../../../services/webui-service/src/config/settingsIndex.ts) | Eintrag zum erneuten Start |

Der Hardware-Testmodus ist bereits als Konzept angelegt: `handle_button_raw_event`
im Button-Handler sendet jeden physischen Tastendruck ans Frontend, ausdruecklich
auch fuer Tasten ohne Aktionszuordnung.

## Umgesetzt

**Backend**

- `setup_completed` und `setup_version` in der `allowed`-Menge von
  `update_general_config` ([`routes_config.py`](../../../services/backend-service/src/backend_service/api/routes_config.py)),
  inklusive Typerzwingung wie bei den anderen Feldern.
- `POST /api/v1/audio/test-tone` (Backend-Proxy) →
  `POST /api/v1/test-tone` im Audio-Service. Der Ton wird ueber `paplay`
  abgespielt, **nicht** ueber den VLC-Backend: so laeuft er neben einer
  laufenden Wiedergabe her, statt sie zu stoppen.
- Mitgeliefertes Asset `services/audio-service/assets/test-tone.wav`
  (1,4 s Dreiklang, im Dockerfile nach `/app/assets/` kopiert).
- `POST /api/v1/config/display/test` (Backend-Proxy) → `POST /test` im
  Display-Service, analog zum bestehenden `leds/test`.

**Frontend**

- `pages/SetupWizardPage.tsx` mit Stepper und sechs Schritten.
- `components/setup/{SecurityStep,AudioStep,HardwareStep,ContentStep}.tsx`.
- `hooks/useSetupStatus.ts` mit der Erkennung von Bestandsinstallationen.
- Route `/setup` in `App.tsx`, bewusst **ohne** `ProtectedRoute`.
- Einmalige Weiterleitung beim ersten Aufruf plus wegklickbarer Hinweis.
- `components/admin/SetupWizardRestart.tsx` und Section `setup_wizard` in
  `settingsIndex.ts` zum erneuten Start.
- Namespace `setup` in `i18n.ts`, `public/locales/{de,en}/setup.json`
  (86 Schluessel, deckungsgleich).

### Zwei Dinge, die sich beim Bauen als anders herausgestellt haben

**`paplay` meldet einen unbekannten Sink nicht.** Es faellt still auf den
Standardausgang zurueck und beendet sich mit 0. Fuer den Assistenten waere das
die schlimmste Variante: der Nutzer waehlt Ausgang A, hoert Ton aus B und haelt
A fuer geprueft. Der Sink wird deshalb **vor** dem Abspielen gegen die erkannte
Geraeteliste geprueft und ein unbekannter Name mit 404 abgelehnt.

**Der Display-Render-Loop tickt jede Sekunde.** Ein Testbild waere nach
spaetestens einer Sekunde ueberschrieben und nicht ablesbar gewesen. Der Loop
hat daher eine Sperre (`_test_pattern_until`), waehrend der er den normalen
Frame auslaesst.

Die Aussperr-Gefahr nach dem Passwort-Schritt besteht nicht: `POST /auth/password`
setzt beim Erstsetzen selbst ein Session-Cookie.

## Ursprüngliche Lückenanalyse

**1. Persistenz-Flag.** `update_general_config` in
[`routes_config.py:217`](../../../services/backend-service/src/backend_service/api/routes_config.py)
filtert den Request gegen eine feste `allowed`-Menge:

```python
data = {k: v for k, v in body.items() if k in allowed}
```

Ein neuer Schluessel wird also **stillschweigend verworfen**. Die Menge muss um
`setup_completed` (bool) und `setup_version` (int) erweitert werden.
`setup_version` erlaubt es, den Assistenten nach einem groesseren Update erneut
anzubieten, ohne ihn Bestandsnutzern aufzuzwingen.

**2. Testton.** Es gibt keinen Endpunkt dafuer. Noetig:
`POST /api/v1/audio/test-tone`, im Backend auf den Audio-Service
durchgereicht — analog zu `get_audio_devices`, das schon per `httpx` proxied.
Der Audio-Service braucht dafuer eine kurze, mitgelieferte Audiodatei im Image
(wenige Sekunden, unaufdringlich). Sie darf nicht aus der Mediathek kommen: auf
einer frischen Box ist die leer.

**3. Display-Test.** Der Display-Service hat heute nur `/health`
([`routes.py:28`](../../../services/display-service/src/display_service/api/routes.py)).
Fuer eine ehrliche Sichtpruefung fehlt ein Testbild. Vorbild ist `leds/test`:
ein MQTT-Kommando `display/test`, das fuer einige Sekunden ein Testmuster
anzeigt. Wenn das zu viel wird, ist die Rueckfallebene eine schlichte
Ja/Nein-Frage („Siehst du etwas auf dem Display?") kombiniert mit dem
`service_status` — ehrlicher als ein Test, der nichts testet.

**4. Der Assistent selbst.**

- `SetupWizardPage.tsx` plus eine Komponente je Schritt
- Route `/setup` in `MainLayout` ([`App.tsx:187`](../../../services/webui-service/src/App.tsx)) —
  **ohne** `ProtectedRoute`, sonst sperrt sich der Assistent aus, sobald in
  Schritt 2 ein Passwort gesetzt wurde
- Ein Hook, der `setup_completed` liest und beim ersten Aufruf einmalig auf
  `/setup` leitet
- Ein dezenter, wegklickbarer Hinweis in `MainLayout`, solange nicht
  abgeschlossen
- Neuer i18n-Namespace `setup.json` in `public/locales/{de,en}/`
- Eintrag in `settingsIndex.ts` zum erneuten Start

## Schritte im Einzelnen

**1. Sprache.** Deutsch/Englisch. Setzt `localStorage['minabox-language']` wie
bisher. Falls `MINABOX_LANGUAGE` aus der `.env` erreichbar gemacht wird, dient
das als Vorauswahl — der Assistent in `install.sh` hat die Frage schon gestellt,
sie ein zweites Mal zu stellen ist nur dann in Ordnung, wenn sie vorbelegt ist.

**2. Zugriffsschutz.** Passwort setzen, Bereiche waehlen (`admin`, `media`,
`dashboard`). Ueberspringen ist moeglich, aber mit einer klaren Ansage, was das
bedeutet — nicht mit einer Warnfarbe, sondern mit einem Satz.

**3. Audio.** Sinks aus `GET /audio/devices` anbieten, gewaehlten Sink per
`switch-device` aktivieren, **Testton abspielen**, dann „Hast du etwas gehoert?"
Bei Nein: naechsten Sink anbieten statt den Nutzer allein zu lassen. Danach
Lautstaerkegrenzen (min/default/max) aus `config/audio`.

Dieser Schritt rechtfertigt den Assistenten allein. „Kein Ton" ist laut
`.claude/skills/minabox-debug-analyze/references/known-issues.md` das haeufigste
Fehlerbild ueberhaupt.

**4. Hardware bestaetigen.** Nur fuer tatsaechlich laufende Dienste — welche
das sind, sagt `service_status`. Je LED ein Test ueber `leds/test` mit
Rueckfrage; fuer Tasten der Testmodus mit `button_raw_event`, der anzeigt,
welche Taste gerade gedrueckt wurde; fuer das Display das Testbild.

Damit faellt sofort auf, was sonst wochenlang unbemerkt bleibt: vertauschte
Pins, oder derselbe GPIO doppelt in `buttons.json` und `leds.json` — ein
bekanntes Fehlerbild.

**5. Erste Inhalte.** Lernmodus einschalten, erste Karte auflegen, einem Titel
oder Ordner zuordnen. Danach Musik hochladen bzw. Medienpfad waehlen. Dieser
Schritt ist am ehesten verzichtbar und sollte am deutlichsten als
ueberspringbar erkennbar sein.

**Abschluss.** `setup_completed: true` und `setup_version` schreiben, kurze
Zusammenfassung, weiter zum Player.

## Offene Pruefpunkte

Der Assistent ist gebaut und uebersetzt, aber **auf echter Hardware noch nicht
durchgespielt**. Vor dem Ausliefern zu pruefen:

- [ ] Frische Box: Assistent springt beim ersten Aufruf auf. Nach dem Abbrechen
      erscheint der Hinweis, aber **keine** erneute Weiterleitung beim
      Seitenwechsel.
- [ ] Bestandsinstallation mit vorhandenen Karten: der Assistent springt
      **nicht** auf. Das ist die Annahme hinter `useSetupStatus` und der
      einzige Punkt, der ohne Migrationsskript auskommt.
- [ ] Nach Schritt 2 bleibt die Sitzung gueltig — anschliessend `/admin`
      oeffnen, ohne sich neu anmelden zu muessen.
- [ ] Testton: waehrend laufender Wiedergabe ausloesen. Die Musik darf nicht
      stoppen.
- [ ] Testton auf einer Box mit mehreren Ausgaengen: Ausgang wechseln, Ton
      ausloesen, und pruefen, dass er wirklich aus dem gewaehlten Geraet kommt.
- [ ] Hardware-Schritt auf einer Box ohne LED/Button/Display: zeigt den Hinweis
      und laesst sich ueberspringen.
- [ ] Display-Testbild bleibt sichtbar stehen (die Sperre haelt es sechs
      Sekunden), danach kehrt die normale Anzeige zurueck.
- [ ] Lernmodus wird beim Verlassen des Inhalte-Schritts wieder abgeschaltet.
      Sonst bleibt die Box im Lernmodus haengen und spielt nichts ab.
- [ ] Vollstaendig auf dem Telefon bedienbar.
- [ ] Nach Abschluss: `data/general_settings.json` enthaelt
      `"setup_completed": true` und `"setup_version": 1`.
