# Komponenten-Capabilities

**Status:** umgesetzt (2026-08-27), Issue #132.

Der Installer bietet fuenf **optionale** Komponenten an; die Pflichtdienste
(MQTT, Backend, Host-Helper, Audio, WebUI) laufen immer. Backend und WebUI
mussten wissen, was tatsaechlich installiert ist, damit die WebUI keine toten
Menuepunkte, Einstellungen oder Aktionen fuer weggelassene Komponenten zeigt und
das Backend Direktaufrufe dafuer sauber abweist.

| WebUI-Komponente | Compose-Profil | Dienst | Feature-Key |
|---|---|---|---|
| RFID-Leser | `rfid` | `rfid` | `rfid` |
| LEDs | `led` | `led` | `led` |
| Taster / Drehregler | `button` | `button` | `button` |
| OLED-Display | `display` | `display` | `display` |
| Medienimport von URL | `media` | `media-downloader` | `media_downloader` |

## Quelle der Wahrheit: `COMPOSE_PROFILES`

Die Auswahl liegt als `COMPOSE_PROFILES` in `.env` (von `install.sh` gesetzt,
im Wartungsmenue *Komponenten aendern* editierbar). `docker-compose.yml` reicht
den Wert zusaetzlich als Umgebungsvariable in den Backend-Container. Compose ist
das Einzige, das auf den Wert *handelt* - deshalb bleibt er die einzige Quelle,
es gibt bewusst kein zweites Manifest, das synchron gehalten werden muesste.

`backend_service.core.capabilities`:

- `installed_features()` - parst `COMPOSE_PROFILES`.
- `feature_states()` - mergt das mit `container_registry.discover()`
  (`running` / `healthy` aus dem Live-Containerzustand).
- `require_feature(key)` - `409 feature_not_installed`, wenn nicht installiert.
  Angewandt auf `GET/POST /tracks` (URL-Import/-Vorschau) und die mutierenden
  Hardware-Routen in `routes_config.py`.

## Endpoint

`GET /api/v1/system/capabilities`

```json
{
  "rfid":            { "installed": true,  "running": true,  "healthy": true  },
  "led":             { "installed": false, "running": false, "healthy": false },
  "button":          { "installed": true,  "running": false, "healthy": false },
  "display":         { "installed": false, "running": false, "healthy": false },
  "media_downloader":{ "installed": false, "running": false, "healthy": false }
}
```

- `installed` - bei der Installation gewaehlt. Bleibt `true` fuer einen nur
  gestoppten oder ungesunden Container.
- `running` / `healthy` - aktueller Containerzustand. Ohne Docker-Socket
  spiegeln sie `installed`.

## Fail-open an drei Stellen

1. **Backend, `COMPOSE_PROFILES` fehlt/leer** → alle Features gelten als
   installiert (`logger.warning("compose_profiles_unset_fail_open")`). Das ist
   das Verhalten von vor diesem Feature - es verschwindet nichts.
2. **WebUI, Abruf schlaegt fehl** → letzter Cache-Wert bzw. „alles installiert".
   Ein Feature darf nie wegen eines Netzwerk-Schluckaufs verschwinden.
3. **WebUI, noch nichts geladen** → `localStorage['minabox.capabilities']` wird
   synchron eingelesen. Wiederkehrende Nutzer sehen sofort das richtige Menue;
   nur der allererste Aufruf auf einer abgespeckten Box kann ein Feature einmal
   ausblenden.

## WebUI-Verdrahtung

`CapabilitiesProvider` (um `MainLayout`) → `useCapabilities()` /
`useFeatureInstalled(key)`.

| Ort | Verhalten ohne die Komponente |
|---|---|
| `Navigation` / `MobileBottomNav` | `/rfid`-Eintrag weg (ohne Leser) |
| `App.tsx` Route `/rfid` | Deep-Link leitet auf `/player` |
| `AdminPage` (`settingsIndex.ts` `requiresFeature`) | Abschnitte `rfid`/`buttons`/`leds`/`display` und `media_import_domains` raus, leer gewordene Gruppen ganz raus - Navigation, Formulare und Suche aus einer Quelle |
| `MediaFab` / `MediaPage` | Aktion „Von URL importieren" und der Import-Dialog weg (ohne `media_downloader`); „Remote-Track" (Stream-URL, kein Downloader) bleibt |

Eine **installierte, aber ungesunde** Komponente bleibt sichtbar - die
bestehende Fehler-/Offline-Darstellung der jeweiligen Panels greift.

### Bekannte Einschraenkung

Der Abschnitt *Lichter* buendelt `LEDConfigPanel` (LED-Dienst) und
`BoardLedsToggle` (Stealth-Modus der Pi-Onboard-LEDs, laeuft ueber den
Host-Helper, nicht ueber den LED-Dienst). Ohne die Komponente `led` verschwindet
der ganze Abschnitt - der Stealth-Modus damit auch. Vertretbar: Wer `led`
abgewaehlt hat, hat „keine Lichter auf dieser Box" signalisiert. Zurueck ueber
das Installer-Wartungsmenue.

## Migration Bestandsboxen

Kein Schritt noetig. Jede `.env` hat `COMPOSE_PROFILES` seit dem ersten
Installer-Release; beim Update zieht `docker-compose.yml` den Wert automatisch
in den Backend-Container. Fehlt er wider Erwarten, greift Fail-open (1).

## Kein Komponenten-Management in der WebUI

Bewusste Produktentscheidung (Issue #132): nicht installierte Funktionen werden
nur **versteckt**. Aktivieren/Deaktivieren bleibt dem Installer-Wartungsmenue
vorbehalten (`install.sh` → *Komponenten aendern*, macht bereits
`docker compose down --remove-orphans` vor dem Re-Up). Falls das spaeter in die
WebUI soll: Schreibpfad WebUI → Backend → Host-Helper editiert die
`COMPOSE_PROFILES`-Zeile und recompose - `GET /system/capabilities` bekaeme ein
schreibendes Geschwister, das Profil→Feature-Mapping liegt zentral in
`capabilities.py`.
