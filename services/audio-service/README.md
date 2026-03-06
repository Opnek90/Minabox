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

- **VLC-based playback** using libVLC (`python-vlc`)
- **PipeWire/Pulse sink discovery** via `pactl`
- **MQTT control** for playback and volume
- **Multiple audio sources**: local files and HTTP/HTTPS streams
- **Volume management** with configurable max volume
- **State persistence** and resume support
- **REST API** for health and status
- **Hot-reload configuration** without service restart
- **Device filtering and display names** for UI selection

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
