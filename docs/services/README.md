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
| [tts](tts/README.md) | Standalone service for the spoken announcements: turns a sentence into a cached WAV file, locally with Piper. |
| [host-helper](host-helper/README.md) | The only service allowed to act on the host itself (move files, system actions). Called only internally by the backend. |
| [shared-lib](shared-lib/README.md) | Shared Python building blocks (config, MQTT base, logging, health schemas). Not a service of its own, but a package. |

Also: [webui/Setup-Wizard.md](webui/Setup-Wizard.md) – concept for the
first-run wizard.

Every service document follows the same outline — purpose, file structure,
runtime flow, interfaces, configuration, dependencies, errors, development,
and a section on where to make changes. It is defined in
[_TEMPLATE.md](_TEMPLATE.md); [rfid](rfid/README.md) is the reference
implementation.

## Addons

**Addon** is the word on screen, **component** the word in the code. They mean
the same thing — something the box can be given or have taken away — and the
split is only which audience is reading: the API route is `/system/components`
and the Compose profiles keep the names they have always had, while the web
interface says *Settings → Addons* throughout. Two words for one thing in one
sentence is what we are avoiding, not two words in two places.

Six services are optional: `rfid`, `led`, `button`, `display`,
`media-downloader` and `tts`. They are Compose profiles (`COMPOSE_PROFILES` in
`.env`), chosen during the install and changeable afterwards. Each one keeps
its own version number and follows the box's update channel, exactly like the
services that always run.

The web interface shows them as a catalogue: the addons this box does not have
are listed too, with what they are for, what hardware they need and whether
they need the internet — otherwise the only way to find out is this
documentation, and an addon nobody finds might as well not exist. The
descriptions live in
[`services/backend-service/src/backend_service/resources/components.json`](../../services/backend-service/src/backend_service/resources/components.json),
in German and English. The backend ships that file inside its image, so the
catalogue also works on a box that has never reached the internet, and
publishes a copy in `release/release-manifest.json` so a description can be
corrected without a new backend image.

Adding an addon to the catalogue does not need a web-interface release: the
name and the description travel with the API answer, so an addon the browser
build has never heard of still appears under its own name. What it does need is
a backend that knows the profile (`core/capabilities.py`, plus its entry in
`components.json`), a host-helper that knows the service
(`routes/components.py`) and the Compose file on the box — which arrives with
the `git pull` at the start of every update run. A web-interface release is
only needed when the addon brings a settings panel of its own; `settings_section`
in the catalogue names the panel it wants, and an addon whose panel this build
does not have shows its description instead of nothing.

Switching an addon on pulls its image straight away and starts it; there is
no waiting for the next update run. The card reader and the display need I2C,
which only appears as `/dev/i2c-1` after a reboot — the run says so and starts
the rest.

### Two ways to switch one on

The catalogue carries *how* an addon is installed as a field (`install`), not
as a boundary:

| `install` | what happens | example |
| --- | --- | --- |
| `{"type": "profile"}` | `COMPOSE_PROFILES` is rewritten, containers are recreated, services restart | card reader, announcements |
| `{"type": "setting", "field": ...}` | one field of `general_settings.json` is written; effective at once | online metadata |

That is deliberate. Whether something needs a container of its own is a
decision about how *we* build (see below), and for whoever runs the box it is
not a difference at all: "online metadata" and "media import" are both optional
functions that talk to the internet, and which of the two happens to need
`yt-dlp` is nothing anyone should have to know. So the rows look the same, and
only the confirmation differs — a compose addon collects several switches into
one run with a restart, a setting addon is written the moment it is flipped,
because there is no run to collect it into.

A setting addon is only offered when its field is in `WRITABLE_KEYS`
(`core/general_settings.py`). A switch that can be flipped but never saved is
worse than an addon that is not there.

The other half of a catalogue entry is `category`: `hardware` when the user has
to get hold of an accessory, `software` when they do not. That — not the
container — is what the addons page sorts by, because it is the one property of
an addon that costs money and a screwdriver.

### What earns a container of its own

A separate container is worth it when something brings a **heavy or risky
dependency** that should not sit in the backend image for everyone. The media
downloader is the model: `yt-dlp` and `ffmpeg` are large, change often and
touch the open internet, and a box whose owner never imports media should not
carry them at all. The `tts` service is the same case without the internet: a
Piper binary with a bundled ONNX runtime and a voice model per language is
about a hundred megabytes that a box which never switches announcements on has
no reason to carry. Hardware is the second reason: `rfid`, `led`, `button` and
`display` each own one piece of hardware and are useless — and permanently
restarting — without it.

Pure logic plus a settings form earns **no** container. It belongs in the core,
behind a field in `general_settings.json`: a container costs memory on a
Raspberry Pi, a place in the update matrix, its own version number and an MQTT
conversation, and none of that is paid for by a feature that is only a few
hundred lines of Python.

It can still be an addon, though — that is what `install: {"type": "setting"}`
is for. The two questions are separate: *does this earn a container* is decided
here, *is this an addon* is decided by whether a whole function is missing
without it and whether it needs explaining (an accessory, the internet, or data
leaving the box). Online metadata answers yes to both and has no container.
Sleep timer, stealth mode and the update check answer no to the first — they
change how something existing behaves — and stay ordinary settings, or the
addons page turns into a second settings page.

Third-party addons are out of scope. Accepting somebody else's container would
need a stable public API with token scopes, MQTT ACLs — the broker currently
runs with `allow_anonymous true` and no topic restrictions — and a way for an
addon to bring its own interface without shipping React. None of that pays off
while every addon comes from this repository.
