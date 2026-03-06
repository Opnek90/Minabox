# Audio Service

VLC-based audio playback service for Minabox with PipeWire/Pulse sink selection, controlled via MQTT.

## Overview

The Audio Service is responsible for playing audio files and streams on the Minabox device. It receives playback commands via MQTT, uses VLC (libVLC) as the playback backend, and sends audio to the host audio server through the PulseAudio-compatible PipeWire socket. [In practice this means the host manages WM8960, Bluetooth, USB headsets and other physical devices; the container only selects sinks.]

## Architecture

### Target model

- **Host audio stack**: PipeWire + WirePlumber manage all physical outputs such as WM8960, Bluetooth speakers/headsets, USB headsets, HDMI, and onboard audio.
- **Audio container**: Uses VLC with `--aout=pulse` and communicates only with the host Pulse-compatible socket.
- **Device selection**: The service refreshes and exposes available Pulse/PipeWire sinks.
- **Web UI**: Refresh/select should operate on sinks, not raw ALSA devices.

This model is the preferred Minabox runtime because it supports Bluetooth and hot-pluggable devices without tying the service to a single hardware device.

## Features

<<<<<<< HEAD
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
=======
- **VLC-based playback** using libVLC (`python-vlc`)
- **PipeWire/Pulse sink discovery** via `pactl`
- **MQTT control** for playback and volume
- **Multiple audio sources**: local files and HTTP/HTTPS streams
- **Volume management** with configurable max volume
- **State persistence** and resume support
- **REST API** for health and status
- **Hot-reload configuration** without service restart
- **Device filtering and display names** for UI selection
>>>>>>> 4450c0c0e5c84b8af98270b21575183cde8eccba

## Configuration

### Audio configuration (`config/audio.json`)

```json
{
  "output_device_type": "pulseaudio",
  "output_device_name": "",
  "enabled_output_devices": [],
  "device_display_names": {},
  "max_volume": 70,
  "default_volume": 40
}
```

### Fields

- `output_device_type`: must be `"pulseaudio"` in normal runtime.
- `output_device_name`: Pulse/PipeWire sink name; empty string means host default sink.
- `enabled_output_devices`: optional allow-list of sink names shown/usable in the selector.
- `device_display_names`: optional mapping of sink name to friendly UI name.
- `max_volume`: maximum allowed volume.
- `default_volume`: startup volume.

Legacy values such as `alsa`, `auto`, and `default` are migrated to `pulseaudio` on config load.

## Device discovery

The service discovers sinks through the host Pulse-compatible API when `PULSE_SERVER` is available. Sink names from `pactl` are the canonical identifiers used in configuration and UI.

Examples of sinks you may see:

- `alsa_output.platform-soc_sound.stereo-fallback`
- `alsa_output.usb-...`
- `bluez_output...`

## Docker runtime

The container should be run against the host Pulse-compatible socket instead of directly owning hardware-specific playback state.

Example:

```bash
docker run -d \
  --name audio-service \
  -e MQTT_BROKER=mqtt \
  -e MINABOX_DEVICE_ID=box1 \
  -e PULSE_SERVER=unix:/run/user/1000/pulse/native \
  -v /run/user/1000/pulse:/run/user/1000/pulse \
  minabox/audio-service
```

## Compose guidance

When using Docker Compose, prefer mounting the host Pulse socket/path and setting `PULSE_SERVER`. Do not design the runtime around fixed ALSA hardware selection when the product requirement is Bluetooth + USB hot-plug + sink switching.

## Migration notes

- Existing configs using `alsa`, `auto`, or `default` are migrated to `pulseaudio` on load.
- Existing configs using `output_device_name: auto` or `default` are migrated to an empty string, which means “use the host default sink”.
- WM8960 remains supported as a host-managed device through PipeWire/WirePlumber; it no longer needs to be treated as the container’s primary hardware abstraction.

## Troubleshooting

### No audio output

1. Verify the host sink exists:
   ```bash
   pactl list short sinks
   ```
2. Verify the container can see the host Pulse socket:
   ```bash
   echo $PULSE_SERVER
   ls -l /run/user/1000/pulse/native
   ```
3. Test host audio routing first, then container playback.
4. If a device was newly attached, refresh sinks and reselect the desired output.

### Wrong output device

1. List sinks:
   ```bash
   pactl list short sinks
   ```
2. Select the desired sink in config/UI.
3. Reinitialize the audio service so VLC binds to the new default sink.

## License

Part of the Minabox project.
