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

## Optional components

Five of these services are optional: `rfid`, `led`, `button`, `display` and
`media-downloader`. They are Compose profiles (`COMPOSE_PROFILES` in `.env`),
chosen during the install and changeable afterwards in the web interface under
*Maintenance → Components*. Each one keeps its own version number and follows
the box's update channel, exactly like the services that always run.

The web interface shows them as a catalogue: the components this box does not
have are listed too, with what they are for, what hardware they need and
whether they need the internet — otherwise the only way to find out is this
documentation, and a component nobody finds might as well not exist. The
descriptions live in
[`services/backend-service/src/backend_service/resources/components.json`](../../services/backend-service/src/backend_service/resources/components.json),
in German and English. The backend ships that file inside its image, so the
catalogue also works on a box that has never reached the internet, and
publishes a copy in `release/release-manifest.json` so a description can be
corrected without a new backend image.

Switching a component on pulls its image straight away and starts it; there is
no waiting for the next update run. The card reader and the display need I2C,
which only appears as `/dev/i2c-1` after a reboot — the run says so and starts
the rest.

### What earns a container of its own

A separate container is worth it when something brings a **heavy or risky
dependency** that should not sit in the backend image for everyone. The media
downloader is the model: `yt-dlp` and `ffmpeg` are large, change often and
touch the open internet, and a box whose owner never imports media should not
carry them at all. Hardware is the second reason: `rfid`, `led`, `button` and
`display` each own one piece of hardware and are useless — and permanently
restarting — without it.

Pure logic plus a settings form is **not** a component. It belongs in the core,
behind a switch in the web interface: a container costs memory on a Raspberry
Pi, a place in the update matrix, its own version number and an MQTT
conversation, and none of that is paid for by a feature that is only a few
hundred lines of Python.

Third-party add-ons are out of scope. Accepting somebody else's container would
need a stable public API with token scopes, MQTT ACLs — the broker currently
runs with `allow_anonymous true` and no topic restrictions — and a way for an
add-on to bring its own interface without shipping React. None of that pays off
while every component comes from this repository.
