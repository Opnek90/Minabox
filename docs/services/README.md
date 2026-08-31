# Services

Minabox is made of several small services that work together over MQTT and a
REST API. Each service has its own version number and its own image
(`ghcr.io/opnek90/minabox-<service>`).

| Service | Purpose |
|---|---|
| [backend](backend/README.md) | Central orchestration and data. The only service with a database; translates between the web UI, MQTT and the other services. |
| [webui](webui/README.md) | Browser interface. A static React SPA, served by Nginx. |
| [audio](audio/README.md) | Produces the sound. Takes playback commands over MQTT and plays locally. |
| [rfid](rfid/README.md) | Talks to the RFID reader and turns card changes into MQTT events. |
| [button](button/README.md) | Reads buttons and rotary encoders, turns them into logical actions and sends them over MQTT. |
| [led](led/README.md) | Output stage for the single-colour status LEDs. |
| [display](display/README.md) | Output stage for the small I2C OLED (SSD1306, 128x64). |
| [media-downloader](media-downloader/README.md) | Standalone service for local media import (audio track of a URL to MP3). |
| [host-helper](host-helper/README.md) | The only service allowed to act on the host itself (move files, system actions). Called only internally by the backend. |
| [shared-lib](shared-lib/README.md) | Shared Python building blocks (config, MQTT base, logging, health schemas). Not a service of its own, but a package. |

Also: [webui/Setup-Wizard.md](webui/Setup-Wizard.md) – concept for the
first-run wizard.

Every service document follows the same outline — purpose, file structure,
runtime flow, interfaces, configuration, dependencies, errors, development,
and a section on where to make changes. It is defined in
[_TEMPLATE.md](_TEMPLATE.md); [rfid](rfid/README.md) is the reference
implementation.
