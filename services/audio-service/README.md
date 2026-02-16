# Audio Service

VLC-based audio playback service for Minabox, controlled via MQTT.

## Overview

The Audio Service is responsible for playing audio files and streams on the Minabox device. It receives playback commands via MQTT, uses VLC as the audio backend, and publishes status updates.

## Features

- **VLC-based playback**: Robust audio playback using libVLC
- **MQTT control**: All commands received via MQTT topics
- **Multiple audio sources**: Supports local files and HTTP/HTTPS streams
- **Volume management**: Child protection with configurable max volume
- **State persistence**: Resume playback after service restart
- **ALSA/PulseAudio support**: Flexible audio output configuration
- **REST API**: Health check and status endpoints

## Architecture

### Components

- **VLC Backend**: Audio playback engine (libVLC via python-vlc)
- **MQTT Client**: Communication with Minabox ecosystem
- **State Manager**: Playback state persistence
- **Config Manager**: Configuration loading and hot-reload
- **FastAPI**: REST endpoints for health/status

### Data Flow

MQTT Command → MQTT Handler → Service → VLC Backend → Audio Output
↓
State Manager → Persistence
↓
MQTT Status → Other Services

text

## MQTT Topics

### Commands (Subscribe)

- `minabox/{device_id}/audio/play` - Start playback
- `minabox/{device_id}/audio/pause` - Pause playback
- `minabox/{device_id}/audio/stop` - Stop playback
- `minabox/{device_id}/audio/next` - Next track (backend controlled)
- `minabox/{device_id}/audio/prev` - Previous track (backend controlled)
- `minabox/{device_id}/audio/set-volume` - Set volume
- `minabox/{device_id}/audio/volume-up` - Increase volume
- `minabox/{device_id}/audio/volume-down` - Decrease volume
- `minabox/{device_id}/audio/config/update` - Update configuration
- `minabox/{device_id}/audio/config/reload` - Reload configuration
- `minabox/{device_id}/audio/config/get` - Get current configuration

### Status (Publish)

- `minabox/{device_id}/audio/status` - Playback status (retained, every 2s)
- `minabox/{device_id}/audio/error` - Error events
- `minabox/{device_id}/audio/config/response` - Config operation response

## Configuration

### Environment Variables (Required)

```bash
MQTT_BROKER=mqtt                    # MQTT broker hostname
MQTT_PORT=1883                      # MQTT broker port
MINABOX_DEVICE_ID=box1              # Device ID for MQTT topics
LOG_LEVEL=INFO                      # Logging level
Environment Variables (Optional)
bash
AUDIO_SERVICE_HOST=0.0.0.0          # FastAPI host
AUDIO_SERVICE_PORT=8003             # FastAPI port
AUDIO_CONFIG_PATH=config/audio.json # Audio config file path
AUDIO_STATE_PATH=state/audio_state.json # State persistence path
Audio Configuration (config/audio.json)
json
{
  "output_device_type": "alsa",
  "output_device_name": "hw:1,0",
  "max_volume": 70,
  "default_volume": 40
}
Fields:

output_device_type: "alsa", "pulseaudio", or "default"

output_device_name: Device name (e.g., "hw:1,0", "default")

max_volume: Maximum volume (0-100) for child protection

default_volume: Initial volume on service start

REST API
Endpoints
GET /api/v1/health - Service health check

GET /api/v1/status - Current audio status

Health Response
json
{
  "status": "healthy",
  "service": "audio",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "timestamp": "2026-02-16T20:45:00Z"
}
Development
Running Locally
bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export MINABOX_DEVICE_ID=box1
export LOG_LEVEL=DEBUG

# Run service
python -m audio_service.main
Running with Docker
bash
# Build image
docker build -t minabox/audio-service .

# Run container
docker run -d \
  --name audio-service \
  --device /dev/snd \
  -e MQTT_BROKER=mqtt \
  -e MINABOX_DEVICE_ID=box1 \
  -e LOG_LEVEL=INFO \
  minabox/audio-service
Dependencies
Python 3.13+

VLC libraries: libvlc5, vlc-plugin-base

ALSA libraries: libasound2 (for ALSA output)

Python packages: See requirements.txt

Troubleshooting
VLC Initialization Fails
Check if VLC libraries are installed:

bash
apt-get install vlc libvlc5 vlc-plugin-base
No Audio Output
Check ALSA devices: aplay -L

Verify device configuration in audio.json

Ensure container has access to /dev/snd

MQTT Connection Issues
Check MQTT_BROKER environment variable

Verify MQTT broker is running

Check network connectivity

License
Part of the Minabox project.

text

***

## ✅ Iteration 4 abgeschlossen (4 Dateien)

**Was wurde erstellt:**
- ✅ `api/routes.py` - FastAPI Health & Status Endpoints
- ✅ `service.py` - **Komplette Service-Orchestrierung** (400+ Zeilen)
- ✅ `main.py` - Entry Point mit Signal Handling & Graceful Shutdown
- ✅ `docs/README.md` - Vollständige Service-Dokumentation

**Service-Features:**
- ✅ MQTT Command Routing zu allen Handlern
- ✅ Periodisches Status-Publishing (2s Intervall, retained)
- ✅ Error-Publishing bei Fehlern
- ✅ Config Hot-Reload via MQTT
- ✅ State-Persistenz bei Pause/Stop
- ✅ Resume-Funktion
- ✅ Graceful Shutdown (SIGTERM/SIGINT)
- ✅ Concurrent FastAPI + MQTT Service

**Wichtige Implementierungen:**
- ✅ Signal Handler für sauberes Shutdown
- ✅ Background Task für Status-Updates
- ✅ Volume Clamping (max_volume enforcement)
- ✅ Next/Prev Delegation (Backend entscheidet Track)
- ✅ Comprehensive Error Handling
- ✅ Uptime Tracking
- ✅ Health Check Logic

**REST API:**
- ✅ `GET /api/v1/health` - Service Health
- ✅ `GET /api/v1/status` - Audio Status

***