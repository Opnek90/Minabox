# WebUI-Service – Architecture

## 1. Zweck & Verantwortung

Der WebUI-Service ist das grafische Frontend der Minabox. Er bietet eine benutzerfreundliche Web-Oberfläche zur Steuerung, Verwaltung und Konfiguration aller Minabox-Funktionen.

Ziele:

- Intuitive Bedienung für Endanwender (Eltern, Kinder mit Hilfe)
- Real-Time-Updates via WebSocket (Audio-Status, RFID-Events, Button-Actions)
- Responsive Design (Desktop, Tablet, Smartphone)
- Multi-Language-Support (Deutsch, Englisch, erweiterbar)
- Verwaltung von Tags, Playlists, Tracks und System-Konfiguration

Nicht-Ziele:

- Keine direkte MQTT-Kommunikation (läuft über Backend)
- Keine Hardware-Logik (nur UI-Layer)
- Keine Datenbank-Zugriffe (nur via Backend REST-API)
- Keine User-Authentication in Phase 1 (Single-User-System)

---

## 2. Technologie-Stack

### 2.1 Frontend

- **Framework:** React 18+ mit TypeScript
- **Build-Tool:** Vite (schneller als Create-React-App)
- **UI-Library:** Material-UI (MUI) v5 oder shadcn/ui (Tailwind-basiert)
- **Routing:** React Router v6
- **State-Management:** React Context API + Hooks (Redux/Zustand optional später)
- **HTTP-Client:** Axios
- **WebSocket:** native WebSocket API oder socket.io-client
- **i18n:** i18next + react-i18next

### 2.2 Deployment

- **Web-Server:** Nginx (Alpine-basiert)
- **Container:** Separater Docker-Container
- **Reverse-Proxy:** Nginx leitet API-Calls an Backend weiter

### 2.3 Development

- **Package-Manager:** npm oder pnpm
- **Linting:** ESLint + Prettier
- **Testing:** Vitest + React Testing Library (optional)

---

## 3. Projekt-Struktur

```
webui-service/
├── src/
│   ├── api/                    # Backend-API-Client
│   │   ├── client.ts          # Axios-Instance mit Base-URL
│   │   ├── tags.ts            # Tag-API-Calls
│   │   ├── playlists.ts       # Playlist-API-Calls
│   │   ├── tracks.ts          # Track-API-Calls
│   │   ├── audio.ts           # Audio-Control-API-Calls
│   │   ├── config.ts          # Config-API-Calls
│   │   └── system.ts          # System-API-Calls
│   ├── components/            # Wiederverwendbare Komponenten
│   │   ├── common/            # Generische Komponenten
│   │   │   ├── Header.tsx
│   │   │   ├── Navigation.tsx
│   │   │   ├── LoadingSpinner.tsx
│   │   │   └── ErrorBoundary.tsx
│   │   ├── player/            # Player-spezifische Komponenten
│   │   │   ├── PlaybackControls.tsx
│   │   │   ├── VolumeControl.tsx
│   │   │   ├── ProgressBar.tsx
│   │   │   └── TrackInfo.tsx
│   │   ├── rfid/              # RFID-spezifische Komponenten
│   │   │   ├── TagList.tsx
│   │   │   ├── TagCard.tsx
│   │   │   ├── TagEditDialog.tsx
│   │   │   └── LearnModeButton.tsx
│   │   ├── media/             # Media-spezifische Komponenten
│   │   │   ├── PlaylistList.tsx
│   │   │   ├── TrackList.tsx
│   │   │   ├── UploadDialog.tsx
│   │   │   └── StreamDialog.tsx
│   │   └── admin/             # Admin-spezifische Komponenten
│   │       ├── SystemStatus.tsx
│   │       ├── ServiceStatus.tsx
│   │       └── ConfigForm.tsx
│   ├── contexts/              # React Context für globalen State
│   │   ├── AudioContext.tsx   # Audio-Status (WebSocket)
│   │   ├── WebSocketContext.tsx
│   │   └── LanguageContext.tsx
│   ├── hooks/                 # Custom React Hooks
│   │   ├── useWebSocket.ts
│   │   ├── useAudioStatus.ts
│   │   └── useApi.ts
│   ├── locales/               # i18n Übersetzungen
│   │   ├── de/
│   │   │   ├── common.json
│   │   │   ├── player.json
│   │   │   ├── rfid.json
│   │   │   ├── media.json
│   │   │   ├── admin.json
│   │   │   └── errors.json
│   │   └── en/
│   │       ├── common.json
│   │       ├── player.json
│   │       ├── rfid.json
│   │       ├── media.json
│   │       ├── admin.json
│   │       └── errors.json
│   ├── pages/                 # Seiten-Komponenten
│   │   ├── PlayerPage.tsx
│   │   ├── RfidPage.tsx
│   │   ├── MediaPage.tsx
│   │   └── AdminPage.tsx
│   ├── types/                 # TypeScript-Type-Definitionen
│   │   ├── api.ts             # Backend-API-Response-Types
│   │   ├── audio.ts
│   │   ├── rfid.ts
│   │   └── config.ts
│   ├── utils/                 # Utility-Funktionen
│   │   ├── formatTime.ts      # z.B. ms → "03:45"
│   │   └── validators.ts
│   ├── App.tsx                # Haupt-App-Komponente
│   ├── main.tsx               # Entry-Point
│   └── i18n.ts                # i18next-Konfiguration
├── public/
│   └── locales/               # Statische i18n-Dateien (kopiert aus src/locales)
├── nginx/
│   └── nginx.conf             # Nginx-Konfiguration
├── Dockerfile
├── docker-compose.yml         # Optional: lokales Testing
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

---

## 4. Seiten & Features

### 4.1 Player-Seite

**Route:** `/player` (Standard-Route)

**Features:**

- **Aktueller Track:** Titel, Artist, Album, Cover (falls vorhanden)
- **Playback-Controls:**
  - Play/Pause-Button
  - Stop-Button
  - Previous/Next-Buttons
- **Fortschrittsbalken:** Aktuelle Position / Gesamtdauer (z.B. `03:45 / 12:30`)
- **Lautstärkeregler:** Slider (0–100), geclamped auf `max_volume` aus Audio-Config
- **Playlist-Info:** Name der aktuellen Playlist, Track X von Y
- **Real-Time-Updates:** WebSocket-Events vom Backend (Audio-Status)

**Komponenten:**

- `TrackInfo` – Zeigt Metadaten des aktuellen Tracks
- `PlaybackControls` – Play/Pause/Stop/Next/Prev-Buttons
- `ProgressBar` – Fortschrittsbalken mit Zeitanzeige
- `VolumeControl` – Lautstärkeregler

**WebSocket-Events:**

- `audio_status` → Update von Track-Info, Position, Volume, State

**API-Calls:**

- `POST /api/v1/audio/play` – Play/Resume
- `POST /api/v1/audio/pause` – Pause
- `POST /api/v1/audio/stop` – Stop
- `POST /api/v1/audio/next` – Nächster Track
- `POST /api/v1/audio/prev` – Vorheriger Track
- `POST /api/v1/audio/volume` – Lautstärke setzen

### 4.2 RFID-Seite

**Route:** `/rfid`

**Features:**

- **Tag-Liste:**
  - Übersicht aller RFID-Tags (Tag-ID, Name, zugeordneter Content)
  - Suchfunktion (Filter nach Name, Tag-ID)
  - Sortierung (Name, Erstellungsdatum)
- **Tag-Actions:**
  - **Bearbeiten:** Dialog zum Ändern von Name und Content-Zuordnung
  - **Löschen:** Bestätigungsdialog, dann DELETE-Call
- **Learn-Mode:**
  - Button "Neuen Tag scannen"
  - Aktiviert RFID-Learn-Mode via `POST /api/v1/rfid/learning-mode`
  - WebSocket-Event `rfid_scanned_learning` → Dialog zur Content-Zuordnung
  - User wählt Playlist oder Track aus Dropdown
  - Speichert Mapping via `POST /api/v1/tags`

**Komponenten:**

- `TagList` – Liste aller Tags
- `TagCard` – Einzelner Tag mit Actions (Edit, Delete)
- `TagEditDialog` – Modal zum Bearbeiten von Tag-Name und Content-Zuordnung
- `LearnModeButton` – Button mit Status-Indicator (Learn-Mode aktiv/inaktiv)

**WebSocket-Events:**

- `rfid_scanned_learning` → Zeigt Dialog mit gescanntem Tag

**API-Calls:**

- `GET /api/v1/tags` – Liste aller Tags
- `POST /api/v1/tags` – Neuen Tag anlegen
- `PUT /api/v1/tags/{tag_id}` – Tag bearbeiten
- `DELETE /api/v1/tags/{tag_id}` – Tag löschen
- `POST /api/v1/rfid/learning-mode` – Learn-Mode aktivieren/deaktivieren

### 4.3 Media-Verwaltung

**Route:** `/media`

**Tabs/Sections:**

1. **Playlists**
2. **Tracks**
3. **Streams** (optional separater Tab oder in Tracks integriert)

#### 4.3.1 Playlists-Tab

**Features:**

- **Playlist-Liste:**
  - Übersicht aller Playlists (Name, Beschreibung, Anzahl Tracks)
  - Suchfunktion
- **Playlist-Actions:**
  - **Erstellen:** Dialog mit Name, Beschreibung
  - **Bearbeiten:** Name, Beschreibung ändern; Tracks hinzufügen/entfernen/neu sortieren
  - **Löschen:** Bestätigungsdialog
- **Playlist-Details:**
  - Liste der Tracks in Reihenfolge
  - Drag & Drop zum Umsortieren
  - "Track hinzufügen"-Button → öffnet Track-Auswahl-Dialog

**Komponenten:**

- `PlaylistList` – Übersicht aller Playlists
- `PlaylistEditDialog` – Modal zum Bearbeiten (Name, Beschreibung, Tracks)
- `TrackSelector` – Dialog zur Auswahl von Tracks

**API-Calls:**

- `GET /api/v1/playlists` – Liste aller Playlists
- `POST /api/v1/playlists` – Neue Playlist erstellen
- `PUT /api/v1/playlists/{playlist_id}` – Playlist bearbeiten
- `DELETE /api/v1/playlists/{playlist_id}` – Playlist löschen

#### 4.3.2 Tracks-Tab

**Features:**

- **Track-Liste:**
  - Übersicht aller Tracks (Titel, Artist, Album, Dauer)
  - Suchfunktion (Titel, Artist, Album)
  - Filter nach Quelle (File, Stream)
- **Track-Actions:**
  - **Upload:** Button "Track hochladen" → `UploadDialog`
  - **Stream hinzufügen:** Button "Stream hinzufügen" → `StreamDialog`
  - **Bearbeiten:** Metadaten ändern (Titel, Artist, Album)
  - **Löschen:** Bestätigungsdialog, löscht auch Datei
- **Upload-Dialog:**
  - File-Input (MP3, OGG, FLAC, etc.)
  - Formular: Titel, Artist, Album (optional, wird aus ID3-Tags vorausgefüllt)
  - Progress-Bar während Upload
- **Stream-Dialog:**
  - Stream-URL (z.B. `https://stream.example.com/radio.mp3`)
  - Titel (Pflichtfeld)
  - Artist, Album (optional)

**Komponenten:**

- `TrackList` – Übersicht aller Tracks
- `UploadDialog` – Modal für Track-Upload
- `StreamDialog` – Modal für Stream-Hinzufügen
- `TrackEditDialog` – Modal zum Bearbeiten von Track-Metadaten

**API-Calls:**

- `GET /api/v1/tracks` – Liste aller Tracks
- `POST /api/v1/tracks/upload` – Track hochladen (multipart/form-data)
- `POST /api/v1/tracks` – Stream hinzufügen (JSON mit `source_type="stream"`)
- `PUT /api/v1/tracks/{track_id}` – Track bearbeiten
- `DELETE /api/v1/tracks/{track_id}` – Track löschen

### 4.4 Admin-Seite

**Route:** `/admin`

**Tabs/Sections:**

1. **System-Status**
2. **Allgemeine Einstellungen**
3. **Audio-Einstellungen**
4. **LED-Einstellungen**
5. **Button-Einstellungen**
6. **RFID-Einstellungen**

#### 4.4.1 System-Status-Tab

**Features:**

- **Service-Übersicht:**
  - Liste aller Services (RFID, Audio, Button, LED, Backend) mit Status (Online, Offline, Error)
  - Letzte Aktualisierung (Timestamp)
- **System-Informationen:**
  - Raspberry Pi Model, CPU-Auslastung, RAM, Speicherplatz (optional)
  - Uptime
- **Actions:**
  - "Services neu starten"-Button (optional, triggert `POST /api/v1/system/restart`)

**Komponenten:**

- `SystemStatus` – Übersicht System-Info
- `ServiceStatus` – Status-Karte pro Service

**API-Calls:**

- `GET /api/v1/system/status` – Gesamtsystem-Status
- `POST /api/v1/system/restart` – Service-Neustart (optional)

#### 4.4.2 Allgemeine Einstellungen

**Features:**

- **Sprache:** Dropdown (Deutsch, Englisch)
- **Device-ID:** Anzeige der `MINABOX_DEVICE_ID` (read-only oder editierbar?)
- **Theme:** Light/Dark-Mode (optional)

**State:**

- Sprach-Wahl wird in `localStorage` gespeichert und via i18next angewendet

#### 4.4.3 Audio-Einstellungen

**Features:**

- **Formular:**
  - `output_device_type`: Dropdown (z.B. "ALSA")
  - `output_device_name`: Text-Input (z.B. "hw:1,0")
  - `max_volume`: Slider (0–100, Kinderschutz)
  - `default_volume`: Slider (0–100)
- **Save-Button:** Sendet `PUT /api/v1/config/audio`
- **Validation:** Frontend validiert Werte, Backend validiert ebenfalls

**Komponenten:**

- `ConfigForm` – Generisches Formular-Komponente

**API-Calls:**

- `GET /api/v1/config/audio` – Aktuelle Config laden
- `PUT /api/v1/config/audio` – Config aktualisieren

#### 4.4.4 LED-Einstellungen

**Features:**

- **LED-Liste:**
  - Übersicht aller konfigurierten LEDs (ID, Name, GPIO, Bindings)
- **LED-Actions:**
  - **Hinzufügen:** Dialog mit Name, GPIO, Bindings (Logical-State → Pattern)
  - **Bearbeiten:** Bindings anpassen
  - **Löschen:** LED entfernen
- **Binding-Editor:**
  - Dropdown für Logical-State (z.B. `audio_playing`, `system_error`)
  - Pattern-Auswahl: `solid`, `blink`, `pulse`
  - Parameter: `interval_ms`, `duration_ms`, `repeat`

**Komponenten:**

- `LEDList` – Übersicht aller LEDs
- `LEDEditDialog` – Modal zum Bearbeiten von LED-Config
- `BindingEditor` – Komponente zum Bearbeiten von State→Pattern-Mappings

**API-Calls:**

- `GET /api/v1/config/leds` – LED-Config laden
- `PUT /api/v1/config/leds` – LED-Config aktualisieren

#### 4.4.5 Button-Einstellungen

**Features:**

- **Button-Liste:**
  - Übersicht aller konfigurierten Buttons (ID, Name, Typ, GPIO, Actions)
- **Button-Actions:**
  - **Hinzufügen:** Dialog mit Name, Typ (Push, Rotary), GPIO(s), Mode (Basic/Advanced), Actions
  - **Bearbeiten:** Actions anpassen
  - **Löschen:** Button entfernen
- **Action-Editor:**
  - Basic-Mode: Ein Action für alle Events
  - Advanced-Mode: Event→Action-Mapping (short_press → play_pause, long_press → power_off)

**Komponenten:**

- `ButtonList` – Übersicht aller Buttons
- `ButtonEditDialog` – Modal zum Bearbeiten von Button-Config
- `ActionEditor` – Komponente zum Bearbeiten von Event→Action-Mappings

**API-Calls:**

- `GET /api/v1/config/buttons` – Button-Config laden
- `PUT /api/v1/config/buttons` – Button-Config aktualisieren

#### 4.4.6 RFID-Einstellungen

**Features:**

- **Formular:**
  - `reader_type`: Dropdown (z.B. "PN532", "Mock")
  - `interface`: Dropdown (z.B. "I2C", "SPI", "UART")
  - `scan_interval_ms`: Number-Input
  - `duplicate_suppression_ms`: Number-Input
- **Save-Button:** Sendet `PUT /api/v1/config/rfid`

**Komponenten:**

- `ConfigForm` (wiederverwendbar)

**API-Calls:**

- `GET /api/v1/config/rfid` – RFID-Config laden
- `PUT /api/v1/config/rfid` – RFID-Config aktualisieren

---

## 5. WebSocket-Integration

### 5.1 WebSocket-Context

Ein globaler `WebSocketContext` verwaltet die WebSocket-Verbindung zum Backend.

**Datei:** `src/contexts/WebSocketContext.tsx`

```typescript
import React, { createContext, useContext, useEffect, useState } from 'react';

interface WebSocketContextType {
  socket: WebSocket | null;
  isConnected: boolean;
  lastMessage: any;
}

const WebSocketContext = createContext<WebSocketContextType>({
  socket: null,
  isConnected: false,
  lastMessage: null,
});

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/ws');

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      setLastMessage(message);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    setSocket(ws);

    return () => {
      ws.close();
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ socket, isConnected, lastMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => useContext(WebSocketContext);
```

### 5.2 Audio-Status-Hook

Ein Custom Hook zum Abonnieren von Audio-Status-Updates.

**Datei:** `src/hooks/useAudioStatus.ts`

```typescript
import { useEffect, useState } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import { AudioStatus } from '../types/audio';

export const useAudioStatus = () => {
  const { lastMessage } = useWebSocket();
  const [audioStatus, setAudioStatus] = useState<AudioStatus | null>(null);

  useEffect(() => {
    if (lastMessage?.type === 'audio_status') {
      setAudioStatus(lastMessage.data);
    }
  }, [lastMessage]);

  return audioStatus;
};
```

### 5.3 Verwendung in Komponenten

**Beispiel: Player-Seite**

```typescript
import React from 'react';
import { useAudioStatus } from '../hooks/useAudioStatus';
import { PlaybackControls } from '../components/player/PlaybackControls';
import { TrackInfo } from '../components/player/TrackInfo';
import { ProgressBar } from '../components/player/ProgressBar';

export const PlayerPage: React.FC = () => {
  const audioStatus = useAudioStatus();

  if (!audioStatus) {
    return <div>Lade Audio-Status...</div>;
  }

  return (
    <div>
      <TrackInfo 
        title={audioStatus.track_id} 
        artist="..." 
        album="..." 
      />
      <ProgressBar 
        current={audioStatus.position_ms} 
        total={audioStatus.duration_ms} 
      />
      <PlaybackControls state={audioStatus.state} />
    </div>
  );
};
```

---

## 6. i18n (Multi-Language)

### 6.1 Ordner-Struktur

```
src/locales/
  de/
    common.json          # Header, Navigation, allgemeine Begriffe
    player.json          # Player-Seite
    rfid.json            # RFID-Seite
    media.json           # Media-Verwaltung
    admin.json           # Admin-Bereich
    errors.json          # Fehlermeldungen
  en/
    common.json
    player.json
    rfid.json
    media.json
    admin.json
    errors.json
```

### 6.2 Beispiel-Inhalte

**de/common.json:**

```json
{
  "app_name": "Minabox",
  "navigation": {
    "player": "Wiedergabe",
    "rfid": "RFID-Tags",
    "media": "Mediathek",
    "admin": "Einstellungen"
  },
  "actions": {
    "save": "Speichern",
    "cancel": "Abbrechen",
    "delete": "Löschen",
    "edit": "Bearbeiten",
    "add": "Hinzufügen"
  }
}
```

**de/player.json:**

```json
{
  "title": "Wiedergabe",
  "now_playing": "Aktuelle Wiedergabe",
  "controls": {
    "play": "Abspielen",
    "pause": "Pausieren",
    "stop": "Stoppen",
    "next": "Nächster",
    "previous": "Vorheriger"
  },
  "volume": "Lautstärke",
  "playlist_info": "Track {{current}} von {{total}}"
}
```

**de/rfid.json:**

```json
{
  "title": "RFID-Tags",
  "tag_list": "Tag-Übersicht",
  "learn_mode": "Neuen Tag scannen",
  "learn_mode_active": "Lern-Modus aktiv - Bitte Tag auflegen",
  "edit_tag": "Tag bearbeiten",
  "delete_tag": "Tag löschen",
  "delete_confirm": "Möchten Sie diesen Tag wirklich löschen?",
  "fields": {
    "tag_id": "Tag-ID",
    "name": "Name",
    "content": "Zugeordneter Inhalt"
  }
}
```

**de/media.json:**

```json
{
  "title": "Mediathek",
  "tabs": {
    "playlists": "Playlists",
    "tracks": "Tracks",
    "streams": "Streams"
  },
  "playlists": {
    "create": "Neue Playlist",
    "edit": "Playlist bearbeiten",
    "delete": "Playlist löschen",
    "add_tracks": "Tracks hinzufügen"
  },
  "tracks": {
    "upload": "Track hochladen",
    "add_stream": "Stream hinzufügen",
    "edit": "Track bearbeiten",
    "delete": "Track löschen"
  },
  "upload": {
    "title": "Track hochladen",
    "select_file": "Datei auswählen",
    "uploading": "Wird hochgeladen..."
  },
  "stream": {
    "title": "Stream hinzufügen",
    "url": "Stream-URL",
    "url_placeholder": "https://stream.example.com/radio.mp3"
  }
}
```

**de/admin.json:**

```json
{
  "title": "Einstellungen",
  "tabs": {
    "system": "System-Status",
    "general": "Allgemein",
    "audio": "Audio",
    "leds": "LEDs",
    "buttons": "Buttons",
    "rfid": "RFID"
  },
  "system": {
    "services": "Services",
    "status_online": "Online",
    "status_offline": "Offline",
    "status_error": "Fehler",
    "restart": "Services neu starten"
  },
  "general": {
    "language": "Sprache",
    "device_id": "Geräte-ID"
  },
  "audio": {
    "output_device": "Ausgabegerät",
    "max_volume": "Maximale Lautstärke",
    "default_volume": "Standard-Lautstärke"
  }
}
```

**de/errors.json:**

```json
{
  "network_error": "Netzwerkfehler - Bitte prüfen Sie die Verbindung",
  "tag_not_found": "Tag nicht gefunden",
  "upload_failed": "Upload fehlgeschlagen",
  "config_invalid": "Ungültige Konfiguration",
  "generic_error": "Ein Fehler ist aufgetreten"
}
```

### 6.3 i18next-Konfiguration

**Datei:** `src/i18n.ts`

```typescript
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import Backend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'de',
    supportedLngs: ['de', 'en'],
    ns: ['common', 'player', 'rfid', 'media', 'admin', 'errors'],
    defaultNS: 'common',
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
```

### 6.4 Verwendung in Komponenten

```typescript
import { useTranslation } from 'react-i18next';

export const PlayerPage: React.FC = () => {
  const { t } = useTranslation('player');

  return (
    <div>
      <h1>{t('title')}</h1>
      <button>{t('controls.play')}</button>
      <button>{t('controls.pause')}</button>
    </div>
  );
};
```

### 6.5 Sprachwechsel

```typescript
import { useTranslation } from 'react-i18next';

export const LanguageSelector: React.FC = () => {
  const { i18n } = useTranslation();

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem('language', lng);
  };

  return (
    <select 
      value={i18n.language} 
      onChange={(e) => changeLanguage(e.target.value)}
    >
      <option value="de">Deutsch</option>
      <option value="en">English</option>
    </select>
  );
};
```

---

## 7. Deployment & Nginx-Konfiguration

### 7.1 Dockerfile

**Multi-Stage Build:**

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Nginx
FROM nginx:alpine

# Kopiere Build-Artefakte
COPY --from=builder /app/dist /usr/share/nginx/html

# Kopiere Nginx-Config
COPY nginx/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 7.2 Nginx-Konfiguration

**Datei:** `nginx/nginx.conf`

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;

    server {
        listen 80;
        server_name localhost;

        # Root für statische Files
        root /usr/share/nginx/html;
        index index.html;

        # SPA-Routing: Alle Requests zu index.html
        location / {
            try_files $uri $uri/ /index.html;
        }

        # API-Reverse-Proxy zum Backend
        location /api/ {
            proxy_pass http://backend:8080;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket-Reverse-Proxy zum Backend
        location /ws {
            proxy_pass http://backend:8080/ws;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # Cache für statische Assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### 7.3 Docker-Compose

**Datei:** `docker-compose.yml` (Root-Repository)

```yaml
version: '3.8'

services:
  backend:
    build: ./services/backend-service
    container_name: minabox-backend
    ports:
      - "8080:8080"
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
      - DATABASE_PATH=/data/minabox.db
    volumes:
      - ./data:/data
      - ./audio:/mnt/audio
    networks:
      - minabox-network

  webui:
    build: ./services/webui-service
    container_name: minabox-webui
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - minabox-network

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: minabox-mqtt
    ports:
      - "1883:1883"
    volumes:
      - ./infrastructure/mosquitto/config:/mosquitto/config
    networks:
      - minabox-network

networks:
  minabox-network:
    driver: bridge
```

---

## 8. TypeScript-Types

### 8.1 API-Response-Types

**Datei:** `src/types/api.ts`

```typescript
export interface Tag {
  id: number;
  tag_id: string;
  name: string | null;
  content_type: 'playlist' | 'track';
  content_id: number;
  created_at: string;
  updated_at: string;
}

export interface Playlist {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  tracks?: PlaylistTrack[];
}

export interface Track {
  id: number;
  title: string;
  artist: string | null;
  album: string | null;
  duration_ms: number | null;
  source_type: 'file' | 'stream';
  source_uri: string;
  created_at: string;
}

export interface PlaylistTrack {
  id: number;
  playlist_id: number;
  track_id: number;
  position: number;
  track: Track;
}

export interface AudioStatus {
  state: 'playing' | 'paused' | 'stopped' | 'error';
  track_id: string | null;
  source_type: 'file' | 'stream' | null;
  source_uri: string | null;
  position_ms: number;
  duration_ms: number | null;
  volume: number;
  timestamp: string;
}

export interface ServiceStatus {
  service: string;
  state: 'online' | 'offline' | 'error';
  timestamp: string;
}

export interface ButtonConfig {
  buttons: Button[];
}

export interface Button {
  id: string;
  name: string;
  mode: 'basic' | 'advanced';
  type: 'push' | 'rotary';
  gpio?: number;
  clk?: number;
  dt?: number;
  sw?: number;
  action?: string;
  actions?: Record<string, string>;
}

export interface LEDConfig {
  leds: LED[];
}

export interface LED {
  id: string;
  name: string;
  gpio: number;
  bindings: Record<string, LEDPattern>;
}

export interface LEDPattern {
  pattern_type: 'solid' | 'blink' | 'pulse';
  duration_ms?: number;
  interval_ms?: number;
  repeat?: number;
}

export interface AudioConfig {
  output_device_type: string;
  output_device_name: string;
  max_volume: number;
  default_volume: number;
}

export interface RFIDConfig {
  reader_type: string;
  interface: string;
  scan_interval_ms: number;
  duplicate_suppression_ms: number;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, any>;
  };
}
```

---

## 9. Abhängigkeiten

**Services:**

- Backend-Service (REST-API & WebSocket)

**Infrastruktur:**

- Nginx (Web-Server)
- Docker (Container)

**NPM-Packages (Auszug):**

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "@mui/material": "^5.14.0",
    "@emotion/react": "^11.11.0",
    "@emotion/styled": "^11.11.0",
    "axios": "^1.6.0",
    "i18next": "^23.7.0",
    "react-i18next": "^13.5.0",
    "i18next-http-backend": "^2.4.0",
    "i18next-browser-languagedetector": "^7.2.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "eslint": "^8.55.0",
    "prettier": "^3.1.0"
  }
}
```

---

## 10. Fehler & Status

### 10.1 Error-Handling

Alle API-Calls verwenden einen zentralen Error-Handler:

```typescript
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Backend hat mit Fehler geantwortet
      const errorData = error.response.data as ErrorResponse;
      console.error('API Error:', errorData.error);
      // Zeige User-Notification (z.B. via Toast/Snackbar)
    } else if (error.request) {
      // Request wurde gesendet, aber keine Antwort
      console.error('Network Error:', error.message);
    } else {
      // Fehler beim Setup des Requests
      console.error('Request Error:', error.message);
    }
    return Promise.reject(error);
  }
);
```

### 10.2 Logging

Console-Logging für Entwicklung, kann später durch Sentry o.ä. erweitert werden:

```typescript
console.log('[WebUI] WebSocket connected');
console.error('[WebUI] API call failed:', error);
```

---

## 11. Nicht-Ziele / Abgrenzung

- Keine direkte MQTT-Kommunikation (nur über Backend)
- Keine Hardware-Logik oder GPIO-Zugriffe
- Keine Datenbank-Zugriffe (nur via Backend REST-API)
- Keine User-Authentication in Phase 1 (Single-User-System)
- Keine Offline-Funktionalität (WebUI benötigt Backend-Verbindung)
- Keine Mobile-App (nur Web-basiert, aber responsive)
