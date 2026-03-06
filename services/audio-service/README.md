# Audio Service

VLC-based audio playback service for Minabox with automatic hardware detection, controlled via MQTT.

## Overview

The Audio Service is responsible for playing audio files and streams on the Minabox device. It receives playback commands via MQTT, uses VLC (libVLC) as the audio backend, and publishes status updates. The service automatically detects and prioritizes available audio hardware.

## Features

- **VLC-based playback**: Robust audio playback using libVLC (python-vlc)
- **Automatic audio hardware detection**: Detects and prioritizes audio HATs, USB devices, and onboard audio
- **MQTT control**: All commands received via MQTT topics
- **Multiple audio sources**: Supports local files and HTTP/HTTPS streams
- **Volume management**: Child protection with configurable max volume
- **State persistence**: Resume playback after service restart
- **ALSA/PulseAudio support**: Flexible audio output configuration
- **REST API**: Health check and status endpoints
- **Hot-reload configuration**: Update audio settings without service restart

## Architecture

### Components

#### Core Components

- **VLC Backend** (`vlc_backend.py`): Audio playback engine using libVLC
  - Full VLC media player control
  - Event handling for playback state changes
  - ALSA/PulseAudio output configuration
  - Volume control with child protection limits
  
- **Audio Backend Abstraction** (`audio_backend.py`): Abstract interface for audio backends
  - Extensible design for future backend implementations
  - Standardized playback control interface
  - Event callback system

- **Audio Device Detector** (`audio_detector.py`): Automatic hardware detection
  - Detects available ALSA audio devices
  - Priority-based device ranking
  - Support for common Raspberry Pi audio HATs

#### Service Layer

- **Service** (`service.py`): Main orchestration layer (400+ LOC)
  - MQTT command routing
  - Periodic status publishing (2s interval, retained)
  - Error publishing
  - Config hot-reload via MQTT
  - State persistence
  - Graceful shutdown handling

- **MQTT Client** (`mqtt_client.py`): Communication with Minabox ecosystem
  - Async MQTT connection management
  - Topic subscription/publishing
  - Reconnection handling

- **MQTT Handler** (`mqtt_handler.py`): Command processing
  - Play/Pause/Stop control
  - Volume management
  - Track navigation
  - Config updates

#### Support Components

- **State Manager** (`state_manager.py`): Playback state persistence
  - Save/restore playback state
  - Resume functionality after restart
  
- **Config Manager** (`config_manager.py`): Configuration management
  - JSON-based configuration
  - Hot-reload support
  - Validation with Pydantic schemas

- **FastAPI** (`api/routes.py`): REST endpoints for health/status
  - Health check endpoint
  - Status monitoring

### Data Flow

```
MQTT Command → MQTT Handler → Service → VLC Backend → Audio Output
                                ↓
                         State Manager → Persistence
                                ↓
                         MQTT Status → Other Services
```

## Audio Hardware Detection

### Supported Devices (Priority Order)

The service automatically detects and prioritizes audio devices in the following order:

1. **WM8960 Audio HAT** (Waveshare/Seeed) - `wm8960soundcard`
2. **HiFiBerry DAC/AMP** - `hifiberry`
3. **IQaudio DAC/AMP** - `iqaudio`
4. **Blokas Pisound** - `pisound`
5. **Audio Injector HATs** - `audioinjector`
6. **USB Soundcards** - `USB`
7. **Raspberry Pi 3.5mm jack** - `Headphones`
8. **HDMI audio** - `vc4hdmi` (lower priority)

### Auto-Detection Process

1. Service scans ALSA devices using `aplay -L`
2. Identifies `plughw:` devices for best VLC compatibility
3. Ranks devices by priority based on hardware type
4. Selects best available device automatically
5. Falls back to manual configuration if needed

### Manual Device Configuration

If auto-detection doesn't select the desired device, you can manually configure it in `config/audio.json`:

```json
{
  "output_device_type": "alsa",
  "output_device_name": "plughw:CARD=wm8960soundcard,DEV=0",
  "max_volume": 70,
  "default_volume": 40
}
```

To find your device name, run:
```bash
aplay -L
```

### Troubleshooting: No sound on WM8960 / built-in (Lautsprecher)

If Bluetooth works but the WM8960 or Pi built-in sink (`platform-soc_sound`) has no sound:

- The service now **unsuspends** the Pulse/PipeWire sink and **unmutes ALSA** (Master, Speaker, PCM) on card 0 and 1 when you use that sink. Restart the audio service and try again.
- On the host, check ALSA mixer: run `alsamixer`, press F6 to select the correct card (e.g. WM8960), and ensure Master/Speaker are not muted (MM = muted).
- In Pulse/PipeWire (e.g. `pavucontrol`), ensure the sink is not muted and volume is up.

## VLC Backend

### libVLC Integration

The service uses [python-vlc](https://github.com/oaubert/python-vlc) bindings to control the VLC media player engine. This provides:

- **Robust playback**: Battle-tested media player with wide format support
- **Low resource usage**: Optimized for embedded systems
- **Hardware acceleration**: Support for Raspberry Pi GPU acceleration
- **Network streaming**: HTTP/HTTPS stream support

### VLC Configuration

The VLC backend is configured with:

- **Audio output**: ALSA or PulseAudio
- **Device selection**: Automatic or manual via ALSA device string
- **Volume range**: 0-100 with configurable max limit
- **Buffering**: Optimized for local and network playback

### Event Handling

VLC events are monitored to track:
- Playback state changes (Playing, Paused, Stopped)
- Track completion (for playlist navigation)
- Errors (file not found, codec issues)

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
LOG_LEVEL=INFO                      # Logging level (DEBUG/INFO/WARNING/ERROR)
```

### Environment Variables (Optional)

```bash
AUDIO_SERVICE_HOST=0.0.0.0          # FastAPI host
AUDIO_SERVICE_PORT=8003             # FastAPI port
AUDIO_CONFIG_PATH=config/audio.json # Audio config file path
AUDIO_STATE_PATH=state/audio_state.json # State persistence path
```

### Audio Configuration (config/audio.json)

```json
{
  "output_device_type": "alsa",
  "output_device_name": "auto",
  "max_volume": 70,
  "default_volume": 40
}
```

**Fields:**

- `output_device_type`: Audio output type
  - `"alsa"` - ALSA direct output (recommended for Raspberry Pi)
  - `"pulseaudio"` - PulseAudio output
  - `"default"` - System default
  
- `output_device_name`: Device identifier
  - `"auto"` - Automatic detection (recommended)
  - `"plughw:CARD=xxx,DEV=0"` - Specific ALSA device
  - `"default"` - System default device
  
- `max_volume`: Maximum volume (0-100) for child protection
  
- `default_volume`: Initial volume on service start

## REST API

### Endpoints

- **GET /api/v1/health** - Service health check
- **GET /api/v1/status** - Current audio status

### Health Response

```json
{
  "status": "healthy",
  "service": "audio",
  "uptime_seconds": 123.45,
  "mqtt_connected": true,
  "vlc_initialized": true,
  "timestamp": "2026-02-16T20:45:00Z"
}
```

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Install VLC libraries (Ubuntu/Debian)
sudo apt-get install vlc libvlc5 vlc-plugin-base libasound2

# Set environment variables
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export MINABOX_DEVICE_ID=box1
export LOG_LEVEL=DEBUG

# Run service
python -m audio_service.main
```

### Running with Docker

```bash
# Build image
docker build -t minabox/audio-service .

# Run container (with audio device access)
docker run -d \
  --name audio-service \
  --device /dev/snd \
  -e MQTT_BROKER=mqtt \
  -e MINABOX_DEVICE_ID=box1 \
  -e LOG_LEVEL=INFO \
  minabox/audio-service
```

## Dependencies

### System Packages

- **VLC libraries**: `libvlc5`, `vlc-plugin-base`
- **ALSA libraries**: `libasound2` (for ALSA output)
- **Python**: 3.13+

### Python Packages

See `requirements.txt` for complete list:
- `python-vlc==3.0.21216` - libVLC bindings
- `fastapi==0.115.6` - REST API framework
- `aiomqtt==2.3.0` - Async MQTT client
- `structlog==24.4.0` - Structured logging
- `pydantic==2.10.5` - Configuration validation

## Troubleshooting

### VLC Initialization Fails

**Problem**: `vlc_initialized: false` in health check

**Solutions**:
1. Check if VLC libraries are installed:
   ```bash
   sudo apt-get install vlc libvlc5 vlc-plugin-base
   ```

2. Verify libVLC is accessible:
   ```bash
   python3 -c "import vlc; print(vlc.Instance())"
   ```

### No Audio Output

**Problem**: VLC plays but no sound

**Solutions**:
1. Check detected audio devices:
   ```bash
   aplay -L
   ```

2. Test device directly:
   ```bash
   aplay -D plughw:CARD=xxx,DEV=0 /usr/share/sounds/alsa/Front_Center.wav
   ```

3. Verify Docker container has audio access:
   ```bash
   docker run --device /dev/snd ...
   ```

4. Check volume level:
   ```bash
   amixer -c 0 scontrols
   amixer -c 0 set 'Speaker' 80%
   ```

### Auto-Detection Not Working

**Problem**: Service doesn't find audio device automatically

**Solutions**:
1. Check if `aplay` works:
   ```bash
   aplay -L
   ```

2. Enable DEBUG logging to see detection process:
   ```bash
   export LOG_LEVEL=DEBUG
   ```

3. Manually configure device in `config/audio.json`

### MQTT Connection Issues

**Problem**: `mqtt_connected: false` in health check

**Solutions**:
1. Check MQTT_BROKER environment variable
2. Verify MQTT broker is running:
   ```bash
   docker logs minabox-mqtt
   ```
3. Check network connectivity:
   ```bash
   ping mqtt
   ```

## Implementation Statistics

- **Total files**: 15 Python modules
- **Lines of code**: ~2800 LOC
- **Test coverage**: Production ready
- **Components tested**:
  - ✅ VLC backend initialization
  - ✅ Audio device detection
  - ✅ MQTT integration
  - ✅ REST API endpoints
  - ✅ State persistence
  - ✅ Docker container

## Next Steps

- Integration with Backend Service for playlist management
- Integration with RFID Service for tag-triggered playback
- Web UI for audio control

## License

Part of the Minabox project.

---

**Version**: 1.0.0  
**Last Updated**: 2026-02-16  
**Status**: Production Ready ✅
