# Minabox - Deployment Guide

Diese Anleitung beschreibt, wie du die Minabox auf einem Raspberry Pi aufsetzt und startest.

---

## Voraussetzungen

### Hardware

- **Raspberry Pi 4** (empfohlen) oder Raspberry Pi 3B+
- **SD-Karte** (mind. 16 GB, empfohlen 32 GB)
- **RFID-Reader** (z.B. PN532 via I2C oder SPI)
- **Audio-Ausgabe** (z.B. WM8960 Audio HAT, USB-Lautsprecher oder 3,5mm Klinke)
- **Buttons/Encoder** (optional, für physische Steuerung)
- **LEDs** (optional, für Status-Anzeige)

### Software

- **Raspberry Pi OS** (Bullseye oder neuer)
- **Docker** (Version 20.10+)
- **Docker Compose** (Version 2.0+)
- **Git**

---

## Installation

### 1. Raspberry Pi einrichten

#### OS installieren

1. Lade den [Raspberry Pi Imager](https://www.raspberrypi.com/software/) herunter
2. Installiere **Raspberry Pi OS (64-bit)** auf die SD-Karte
3. Aktiviere SSH (im Imager: Zahnrad-Icon → SSH aktivieren)
4. Setze Hostname, Username und Passwort

#### System aktualisieren

```bash
sudo apt update && sudo apt upgrade -y
```

#### Docker installieren

```bash
# Docker installieren
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# User zu docker-Gruppe hinzufügen
sudo usermod -aG docker $USER

# Neu einloggen, damit Gruppenänderung wirksam wird
newgrp docker

# Docker Compose installieren (falls nicht bereits enthalten)
sudo apt install docker-compose-plugin -y

# Installation prüfen
docker --version
docker compose version
```

### 2. Hardware konfigurieren

#### I2C aktivieren (für RFID-Reader)

```bash
sudo raspi-config
# Interface Options → I2C → Enable
```

Oder direkt:

```bash
sudo sed -i 's/#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/config.txt
sudo reboot
```

Nach Reboot prüfen:

```bash
ls /dev/i2c*
# Sollte /dev/i2c-1 anzeigen
```

#### SPI aktivieren (optional, falls RFID-Reader via SPI)

```bash
sudo raspi-config
# Interface Options → SPI → Enable
```

#### Audio konfigurieren

Für WM8960 HAT:

```bash
# Treiber installieren
git clone https://github.com/waveshare/WM8960-Audio-HAT
cd WM8960-Audio-HAT
sudo ./install.sh
sudo reboot
```

Für 3,5mm Klinke oder USB-Audio:

```bash
# Audio-Devices prüfen
aplay -l

# Standard-Device setzen (optional)
sudo nano /etc/asound.conf
# Trage dort dein Device ein
```

### 3. Minabox-Repository klonen

```bash
cd ~
git clone https://github.com/Opnek90/Minabox.git
cd Minabox
```

### 4. Konfiguration

#### .env-Datei erstellen

```bash
cp .env.example .env
nano .env
```

Passe die Werte an:

```env
MINABOX_DEVICE_ID=box1          # Eindeutige ID deiner Box
MQTT_PORT=1883                   # Standard MQTT-Port
BACKEND_PORT=8080                # Backend-API-Port
WEBUI_PORT=80                    # WebUI-Port (evtl. 8081, falls 80 belegt)
LOG_LEVEL=INFO                   # DEBUG für Entwicklung
```

#### Ordnerstruktur erstellen

```bash
# Daten-Ordner
mkdir -p data
mkdir -p audio/tracks

# Mosquitto-Config
mkdir -p infrastructure/mosquitto/config
```

#### Mosquitto-Konfiguration

Erstelle `infrastructure/mosquitto/config/mosquitto.conf`:

```bash
cat > infrastructure/mosquitto/config/mosquitto.conf <<EOF
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_dest stdout
EOF
```

**Hinweis:** `allow_anonymous true` ist für Entwicklung OK, für Produktion sollte Authentication aktiviert werden.

---

## Services starten

### Alle Services starten

```bash
docker compose up -d
```

- `-d` startet die Container im Hintergrund (detached mode)

### Status prüfen

```bash
docker compose ps
```

Alle Services sollten `running` und `healthy` sein.

### Logs anschauen

```bash
# Alle Services
docker compose logs -f

# Nur ein spezifischer Service
docker compose logs -f backend
docker compose logs -f rfid
docker compose logs -f audio

# Letzte 100 Zeilen
docker compose logs --tail=100 backend
```

### Services neu starten

```bash
# Alle Services
docker compose restart

# Einzelner Service
docker compose restart backend
```

### Services stoppen

```bash
docker compose down
```

Daten (Datenbank, Audio-Files) bleiben erhalten.

### Services stoppen und Volumes löschen

```bash
docker compose down -v
```

**Achtung:** Löscht auch die Datenbank!

---

## WebUI öffnen

1. Finde die IP-Adresse deines Raspberry Pi:

```bash
hostname -I
```

2. Öffne im Browser:

```
http://<raspberry-pi-ip>
```

Beispiel: `http://192.168.1.100`

Falls WebUI-Port geändert (z.B. 8081):

```
http://192.168.1.100:8081
```

---

## Troubleshooting

### Service startet nicht (Exit-Code 1)

```bash
# Logs prüfen
docker compose logs <service-name>

# Container-Status prüfen
docker compose ps
```

### Hardware-Zugriff funktioniert nicht (GPIO, I2C, Audio)

**Lösung 1:** Privileged Mode aktivieren

Bearbeite `docker-compose.yml` und kommentiere für den betroffenen Service die Zeile ein:

```yaml
privileged: true
```

Dann:

```bash
docker compose down
docker compose up -d
```

**Lösung 2:** User-Gruppen prüfen

```bash
# Prüfen, ob User in den richtigen Gruppen ist
groups $USER
# Sollte enthalten: docker, gpio, i2c, spi, audio

# Gruppen hinzufügen
sudo usermod -aG gpio,i2c,spi,audio $USER

# Neu einloggen
newgrp docker
```

### Backend-API nicht erreichbar

```bash
# Health-Check
curl http://localhost:8080/api/v1/health

# Falls Fehler, Logs prüfen
docker compose logs backend
```

### MQTT-Verbindung fehlgeschlagen

```bash
# Mosquitto-Status prüfen
docker compose logs mosquitto

# MQTT-Test mit mosquitto_pub/sub (aus einem anderen Terminal)
docker exec -it minabox-mosquitto mosquitto_sub -t "#" -v

# In einem anderen Terminal
docker exec -it minabox-mosquitto mosquitto_pub -t "test" -m "Hello"
```

Falls `mosquitto_sub` oder `mosquitto_pub` nicht gefunden:

```bash
sudo apt install mosquitto-clients
mosquitto_sub -h localhost -t "#" -v
```

### Datenbank-Fehler

```bash
# Datenbank neu initialisieren (Vorsicht: Löscht alle Daten!)
rm -rf data/minabox.db*
docker compose restart backend

# Backend sollte nun neue DB erstellen
docker compose logs backend
```

### Services bauen neu (nach Code-Änderungen)

```bash
docker compose build
docker compose up -d

# Oder in einem Schritt
docker compose up -d --build
```

---

## Entwicklung

### Einzelnen Service entwickeln

```bash
# Service stoppen
docker compose stop rfid

# Lokal entwickeln
cd services/rfid-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m rfid_service.main

# Nach Änderungen: Service neu bauen und starten
docker compose build rfid
docker compose up -d rfid
```

### Hot-Reload für WebUI

```bash
cd services/webui-service
npm install
npm run dev

# WebUI ist nun unter http://localhost:5173 erreichbar
# Änderungen werden automatisch neu geladen
```

---

## Backup

### Datenbank sichern

```bash
cp data/minabox.db data/minabox.db.backup-$(date +%Y%m%d)
```

### Audio-Dateien sichern

```bash
tar -czf audio-backup-$(date +%Y%m%d).tar.gz audio/
```

### Komplettes Backup

```bash
tar -czf minabox-backup-$(date +%Y%m%d).tar.gz \
  data/ \
  audio/ \
  services/*/config/ \
  .env
```

---

## Updates

### Minabox-Code aktualisieren

```bash
cd ~/Minabox
git pull

# Services neu bauen
docker compose build
docker compose up -d
```

### Docker-Images aktualisieren

```bash
# Mosquitto-Image aktualisieren
docker compose pull mosquitto
docker compose up -d mosquitto
```

---

## Autostart beim Booten

### Docker Compose als systemd-Service

Erstelle `/etc/systemd/system/minabox.service`:

```bash
sudo nano /etc/systemd/system/minabox.service
```

Inhalt:

```ini
[Unit]
Description=Minabox Services
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/Minabox
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable minabox.service
sudo systemctl start minabox.service

# Status prüfen
sudo systemctl status minabox.service
```

---

## Nächste Schritte

1. **Tags anlernen:** WebUI → RFID → "Neuen Tag scannen"
2. **Playlists erstellen:** WebUI → Media → Playlists
3. **Tracks hochladen:** WebUI → Media → Tracks → "Track hochladen"
4. **Buttons konfigurieren:** WebUI → Admin → Button-Einstellungen
5. **LEDs konfigurieren:** WebUI → Admin → LED-Einstellungen

---

## Support

Bei Problemen:

1. Logs prüfen: `docker compose logs -f`
2. GitHub Issues: https://github.com/Opnek90/Minabox/issues
3. Framework-Dokumentation: `docs/Framework.md`
4. Service-Dokumentation: `docs/services/<service>/Architecture.md`

---

**Viel Spaß mit deiner Minabox! 🎵**
