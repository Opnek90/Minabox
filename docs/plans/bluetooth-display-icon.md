# Plan: Bluetooth-Icon auf dem Display („Wechsel möglich“)

**Ziel:** Auf dem OLED-Display ein Bluetooth-Icon anzeigen, **nur** wenn ein Wechsel auf ein anderes Ausgabegerät (inkl. Bluetooth) möglich ist. Kein WebUI nötig – Nutzer sieht das Icon und drückt den Button zum Wechsel.

**Anforderungen (aus User-Feedback):**
1. Gleiche Logik wie alle anderen Display-Funktionen: In der WebUI entscheidbar, **ob** und **wo** (Bereich, Reihenfolge) das Element angezeigt wird.
2. Erstmal ein einfaches Bluetooth-Symbol als Icon.
3. Bestehende Logik/Namenskonvention beibehalten (einheitliches Muster).
4. Status alle paar Sekunden reicht. Bei Unsicherheit (Fehler/Timeout): Icon **nicht** anzeigen; Fehler ins **Log** schreiben (über WebUI auslesbar).
5. Icon nur, wenn mind. 2 Geräte verfügbar **und** mind. 1 Bluetooth-Sink dabei.
6. Scope: nur Display + Audio-Service (kein zusätzliches WebUI-Feature für „Wechsel möglich“).

---

## 1. Audio-Service

**Datei:** `services/audio-service/src/audio_service/service.py`

### 1.1 Status-Payload erweitern

In **`_publish_status()`** (ca. Zeile 220):

- **Vor** dem Bauen des Payloads:
  - `config = self._get_audio_config()`
  - `devices = await self.get_audio_devices(enabled_only=bool(getattr(config, "enabled_output_devices", None) or [])`
  - In einem **try/except**: Bei Exception (z.B. `pactl` fehlgeschlagen, Timeout) → **loggen** (z.B. `logger.warning("audio_status_devices_failed", error=str(exc))`) und `multiple_output_devices = False`, `bluetooth_sink_available = False`.
  - Sonst:
    - `multiple_output_devices = len(devices) >= 2`
    - `bluetooth_sink_available = any((d.get("alsa_device") or "").startswith("bluez_") for d in devices)`

- Zwei neue Felder in den **Payload** (snake_case, wie bestehende Felder):
  - `"multiple_output_devices": bool`
  - `"bluetooth_sink_available": bool`

**Hinweis:** `get_audio_devices()` wird bereits alle ~2 Sekunden pro Status-Publish aufgerufen; ein zusätzlicher Aufruf in `_publish_status()` ist vertretbar. Bei Fehlern: keine neuen Felder weglassen, sondern explizit `false` setzen, damit das Display sicher „kein Icon“ anzeigt.

---

## 2. Display-Service

### 2.1 Config-Schema

**Datei:** `services/display-service/src/display_service/config_schema.py`

- **`DisplayElementType`** (Literal) um `"bluetooth"` erweitern:
  - Von: `Literal["volume", "sleep_timer", "mute", "play_state", "clock", "error_state", "repeat", "shuffle"]`
  - Zu: `... , "bluetooth"]`

### 2.2 StateManager

**Datei:** `services/display-service/src/display_service/state_manager.py`

- In **`update_audio()`** nach dem Parsen von `data` zwei weitere Felder übernehmen (Default `False`):
  - `self._audio["multiple_output_devices"] = data.get("multiple_output_devices", False)`
  - `self._audio["bluetooth_sink_available"] = data.get("bluetooth_sink_available", False)`

- Im **`_audio`-Initialisierungs-Dict** (in `__init__`) die gleichen Keys mit `False` vorbelegen, damit `get_audio()` sie immer liefert.

### 2.3 Anzeige-Logik (_build_areas)

**Datei:** `services/display-service/src/display_service/main.py`

- In **`_build_areas()`** einen weiteren `elif`-Zweig für `el.type == "bluetooth"`:
  - Nur anzeigen, wenn **beide** Bedingungen erfüllt sind:
    - `audio.get("bluetooth_sink_available")`
    - `audio.get("multiple_output_devices")`
  - Dann: `result[area_idx].append({"type": "icon", "value": "bluetooth"})`.

### 2.4 Bluetooth-Icon

**Datei:** `services/display-service/src/display_service/display_controller.py`

- **Pixel-Fallback** (wie bei Mute, Moon, Repeat, Shuffle): Neue Konstante `_ICON_BLUETOOTH` mit einer 16×16-Pixel-Liste für ein einfaches Bluetooth-Symbol (klassisches „B“-Symbol).
- In **`_icon_image_from_pixels()`**: weiteren Fall `icon_name == "bluetooth"` → `_ICON_BLUETOOTH` verwenden.
- Optional: In **`_get_icon_image()`** wird für `icon_bluetooth.png` bereits automatisch gesucht (Namenskonvention `icon_{icon_name}.png`); falls eine PNG später hinzugefügt wird, wird sie geladen, sonst Fallback.

**Hinweis:** Ein einfaches 16×16 Bluetooth-Logo (zwei Dreiecke + Mittelbalken) als Koordinatenliste definieren; Referenz: bestehende Icons (`_ICON_MUTE`, `_ICON_SHUFFLE`).

---

## 3. Backend (Display-Element-Typen)

**Datei:** `services/backend-service/src/backend_service/api/routes_config.py`

- In **`_DISPLAY_ELEMENT_TYPES`** den Eintrag `"bluetooth"` hinzufügen (alphabetisch oder am Ende, konsistent mit bestehender Liste).

---

## 4. WebUI (Übersetzungen)

Damit in der Display-Config das neue Element mit lesbarem Namen und in der richtigen Sprache erscheint:

**Dateien:**
- `services/webui-service/public/locales/de/admin/display.json`
- `services/webui-service/public/locales/en/admin/display.json`

- Unter **`display.element_types`** einen Eintrag hinzufügen:
  - DE: `"bluetooth": "Bluetooth (Wechsel möglich)"` (oder kürzer: „Bluetooth“)
  - EN: `"bluetooth": "Bluetooth (switch available)"` oder `"Bluetooth"`

---

## 5. TypeScript-Typen (WebUI)

**Datei:** `services/webui-service/src/types/api.ts`

- **`DisplayElementType`** um `'bluetooth'` erweitern:
  - Von: `'volume' | 'sleep_timer' | 'mute' | 'play_state' | 'clock' | 'error_state' | 'repeat' | 'shuffle'`
  - Zu: `... | 'bluetooth'`

---

## 6. Reihenfolge der Umsetzung

1. **Audio-Service:** Payload um `multiple_output_devices` und `bluetooth_sink_available` erweitern, inkl. try/except und Logging bei Fehlern.
2. **Display-Service:** Config-Schema (`bluetooth`), StateManager (Felder speichern), _build_areas (Icon-Bedingung), Display-Controller (Bluetooth-Icon Pixel-Fallback).
3. **Backend:** `_DISPLAY_ELEMENT_TYPES` um `"bluetooth"` ergänzen.
4. **WebUI:** Locale-Keys für `display.element_types.bluetooth` (DE/EN) und TypeScript-Typ `DisplayElementType` anpassen.

---

## 7. Abnahmetest (kurz)

- Display-Config in WebUI: Element „Bluetooth“ aktivieren, Bereich (Header/Links/Rechts) und Reihenfolge wählen → speichern.
- Nur 1 Gerät aktiv: Icon erscheint **nicht**.
- Bluetooth-Gerät einschalten/verbinden; wenn 2+ Geräte verfügbar und mind. 1 BT-Sink: Nach wenigen Sekunden (nächstes Status-Update) Icon sichtbar.
- Button (Long-Press) drücken → Ausgabe wechselt auf Bluetooth.
- Bei Fehler (z.B. pactl nicht erreichbar): Icon nicht anzeigen; Log-Eintrag prüfbar (z.B. über WebUI/Logs).

---

## 8. Optionale spätere Erweiterungen

- PNG `icon_bluetooth.png` (16×16) in `display_service/assets/icons/` legen oder über `generate_icon_assets.py` erzeugen.
- Falls gewünscht: gleiche Felder (`multiple_output_devices`, `bluetooth_sink_available`) im REST-Status (GET /audio/status) zurückgeben, damit andere Clients konsistent sind.
