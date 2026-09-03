# Installing Minabox

This guide is for end users. It walks through the installer to a running stack.

## What you need

| | |
|---|---|
| Raspberry Pi | 4 or 5 (3B+ works, but is noticeably slower) |
| Memory card | 16 GB or more |
| Power supply | 5V/3A (Pi 4) or 5V/5A (Pi 5) |
| Operating system | Raspberry Pi OS **64-bit** |
| Network | wired or Wi-Fi with internet access |

An underpowered supply is the most common cause of random crashes and audio
dropouts. If something is inexplicably wrong, check the power supply first.

## 1. Write the operating system

Using the [Raspberry Pi Imager](https://www.raspberrypi.com/software/):

1. Choose **Raspberry Pi OS (64-bit)** — the 32-bit variant does not work.
2. Before writing, open the settings (the gear icon) and set:
   - hostname, e.g. `minabox`
   - username and password
   - Wi-Fi credentials
   - enable SSH
3. Write the card, put it in the Pi, power on.

## 2. Connect

From your computer:

```bash
ssh <username>@minabox.local
```

## 3. Start the installer

```bash
curl -fsSL https://raw.githubusercontent.com/Opnek90/Minabox/main/install.sh -o minabox-install.sh
```

```bash
bash minabox-install.sh
```

The two steps are deliberate: `curl ... | bash` would make the dialogs
unusable, because they need a real terminal.

## 4. Through the installer

The installer walks through these steps:

**Language** — German or English. Applies to the installer and is saved as the
default for the web interface.

**Components** — select and deselect with the space bar, TAB to *OK*.

| Component | For | Hardware |
|---|---|---|
| RFID reader | recognise cards and figures | PN532 on I2C |
| LEDs | status display | GPIO |
| Buttons / rotary encoder | on-device controls | GPIO |
| OLED display | title, clock, volume | SSD1306 on I2C |
| Media import | pull media from a URL into the library | none |
| Announcements | say short things out loud instead of only blinking | none |

MQTT, backend, host-helper, audio and the web UI always run and are not
optional. Only select what you have actually connected — a selected component
without its hardware restarts forever.

None of this is final. Components can be added or removed later in the web
interface under *Maintenance → Components*, without a terminal; the installer's
maintenance menu still does the same job. That page lists the components this
box does not have too, with what each one is for and what it needs — so nothing
has to be decided here for good.

**Basics** — device name, web interface port (default 80), time zone, log
level.

**Audio** — detected sound cards are marked with `(*)`. The choices are the
headphone jack, HDMI, USB sound cards, and HiFiBerry, IQaudio and WM8960 HATs.
For a HAT the installer adds the matching `dtoverlay`; that takes effect only
after a reboot.

The existing `config.txt` is backed up first as `config.txt.minabox-backup`,
and the installer only changes its own marked section.

**Autostart** — optional. The containers restart on their own anyway; the
system service additionally helps when Minabox was stopped by hand beforehand.

The installer then pulls the containers and starts them.

## 5. Set up

At the end the installer names the address, for example:

```
http://192.168.1.42
```

Open it in a browser — that is where you create cards, upload music and
configure everything else.

If you chose a HAT for audio, reboot now and run the installer once more to set
the output under *Reconfigure audio*.

## Running it again: the maintenance menu

```bash
bash minabox-install.sh
```

On an existing installation this opens instead of a fresh install:

| Item | Effect |
|---|---|
| Change components | add or remove LED, display etc. |
| Apply update | load the latest version and restart |
| Reconfigure audio | switch the output, or set it after a reboot |
| Status and diagnostics | state of all containers |
| Change language | German / English |
| Remove Minabox | remove containers and the service; data only if asked |

## When something goes wrong

The installer writes everything to `~/minabox-install.log`. That is the first
place to look when there are questions.

**No sound.** Usually the wrong output is set. Start the installer →
*Reconfigure audio*. After changing a HAT a reboot is required.

**Sound only after logging in over SSH.** The audio service needs the user
session. The installer enables this permanently with `loginctl enable-linger`;
check with `loginctl show-user $USER | grep Linger`.

**A container keeps restarting.** Usually a component is selected whose hardware
is not connected. Switch it off under *Maintenance → Components* in the web
interface, or in the installer's maintenance menu.

**Web interface not reachable.** The first start takes a moment. Check the state
with:

```bash
cd ~/minabox && docker compose ps
```

**Box disappeared from the network** (router off, Wi-Fi password changed, box
moved). After about a minute without a connection the box opens a Wi-Fi network
of its own called `Minabox-Setup`. Connect to it and open `http://10.42.0.1`;
the password is shown on the display. Under *Maintenance → Network* enter the
new Wi-Fi — as soon as the box is back online the hotspot disappears on its
own. Details in [Troubleshooting.md](Troubleshooting.md).

**More help.** [Troubleshooting.md](Troubleshooting.md), and for a support
request include the diagnostics package from the interface
(*Settings → Diagnostics*) — see [DebugExport.md](DebugExport.md).
